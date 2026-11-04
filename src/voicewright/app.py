import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.background import BackgroundTask

from voicewright.audio_converter import SUPPORTED, FfmpegMissing, UnsupportedAudio, convert
from voicewright.config import ConfigError, load_config
from voicewright.data_folder import DataFolder, MissingLinkTarget
from voicewright.default_emotions import DEFAULT_EMOTIONS_FILE, load_default_emotions
from voicewright.drafts import Draft, DraftStore
from voicewright.engines import Engines, default_engines
from voicewright.jobs import Job, JobAlreadyRunning, JobRunner, JobState
from voicewright.model_manager import ModelManager
from voicewright.voice_design import design_draft_voice

# Long enough for a detailed description; Qwen is told the whole thing for every clip.
MAX_DESCRIPTION = 500

STATIC_FOLDER = Path(__file__).parent / "static"
HOME_PAGE = STATIC_FOLDER / "index.html"


def page_title() -> bytes:
    """The home page's <title> element, as served: how a running Voicewright is recognized."""
    title = re.search(rb"<title>.*?</title>", HOME_PAGE.read_bytes(), re.DOTALL)
    if not title:
        raise RuntimeError(f"{HOME_PAGE} needs a <title>")
    return title.group()


class DefaultEmotionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    sample: str
    exaggeration: float
    cfg: float


class DesignRequest(BaseModel):
    description: str = Field(max_length=MAX_DESCRIPTION)

    @field_validator("description")
    @classmethod
    def not_blank(cls, description: str) -> str:
        description = " ".join(description.split())
        if not description:
            raise ValueError("describe the voice, e.g. a gravelly older man, slow and calm")
        return description


class JobStarted(BaseModel):
    job_id: str


class PresetOut(BaseModel):
    exaggeration: float
    cfg: float
    clip_url: str


class DraftOut(BaseModel):
    id: str
    description: str
    created: str
    emotions: list[str]
    presets: dict[str, PresetOut]
    # Emotions not designed yet: designing is still running, or stopped part way.
    missing: list[str]

    @classmethod
    def of(cls, draft: Draft) -> "DraftOut":
        return cls(
            id=draft.id,
            description=draft.description,
            created=draft.created,
            emotions=list(draft.emotions),
            presets={
                name: PresetOut(
                    exaggeration=preset.exaggeration,
                    cfg=preset.cfg,
                    clip_url=f"/voices/drafts/{draft.id}/clips/{name}",
                )
                for name, preset in draft.presets.items()
            },
            missing=list(draft.missing),
        )


class ProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step: int
    total: int | None
    message: str


class JobOut(BaseModel):
    """A job as the page sees it: read from a Job."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    state: JobState
    progress: ProgressOut
    result: Any = None
    error: str | None = None


def create_app(
    config_path: Path,
    engines: Engines | None = None,
    default_emotions_file: Path = DEFAULT_EMOTIONS_FILE,
) -> FastAPI:
    """The app, on the given engines (the real ones unless a test passes fakes).

    Raises ConfigError, or DefaultEmotionsError for a broken Default emotion set file.
    """
    default_emotions = load_default_emotions(default_emotions_file)
    config = load_config(config_path)
    folder = config.data_folder
    try:
        DataFolder(folder).create()
    except MissingLinkTarget as missing:
        raise ConfigError(
            f"the data folder {folder} set in {config_path} goes through the link {missing.link}, "
            f"which links to {missing.target}, which doesn't exist; "
            "connect the drive it is on or change data_folder"
        ) from None
    except OSError as error:
        raise ConfigError(
            f"can't create the data folder {folder} set in {config_path}: {error.strerror}"
        ) from None

    app = FastAPI(title="Voicewright")
    jobs = JobRunner()
    models = ModelManager(engines or default_engines())
    drafts = DraftStore(folder / "drafts")
    app.state.jobs = jobs
    app.state.models = models

    @app.exception_handler(JobAlreadyRunning)
    def job_already_running(request: Request, error: JobAlreadyRunning) -> JSONResponse:
        running = error.running
        return JSONResponse(
            status_code=409,
            content={
                "detail": f"A {running.kind} job is already running; wait for it to finish",
                "running_job_id": running.id,
            },
        )

    def find_job(job_id: str) -> Job:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, f"no job {job_id}; it may have finished long ago")
        return job

    @app.get("/emotions/defaults")
    def list_default_emotions() -> list[DefaultEmotionOut]:
        """The Default emotion set: each emotion's sample sentence and starting values."""
        return [DefaultEmotionOut.model_validate(emotion) for emotion in default_emotions]

    @app.post("/voices/design", status_code=202)
    def design_voice(request: DesignRequest) -> JobStarted:
        """Start designing a Draft voice: the neutral clip, then every default Emotion preset."""
        work = design_draft_voice(drafts, models, default_emotions, request.description)
        return JobStarted(job_id=jobs.start("voice design", work).id)

    def find_draft(draft_id: str) -> Draft:
        draft = drafts.get(draft_id)
        if draft is None:
            raise HTTPException(404, f"no Draft voice {draft_id}")
        return draft

    @app.get("/voices/drafts/{draft_id}")
    def get_draft(draft_id: str) -> DraftOut:
        """A Draft voice: its description and the presets designed so far, with clip URLs."""
        return DraftOut.of(find_draft(draft_id))

    @app.get("/voices/drafts/{draft_id}/clips/{emotion}")
    def get_draft_clip(draft_id: str, emotion: str) -> FileResponse:
        """One preset's Reference clip, as standard WAV."""
        find_draft(draft_id)
        clip = drafts.clip_path(draft_id, emotion)
        if clip is None:
            raise HTTPException(404, f"Draft voice {draft_id} has no {emotion} clip")
        return FileResponse(clip, media_type="audio/wav")

    @app.get("/jobs/current")
    def current_job() -> JobOut | None:
        """The job running now (e.g. loading the speech model at startup), or null."""
        running = jobs.running
        return None if running is None else JobOut.model_validate(running)

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str) -> JobOut:
        """A job's state and progress, and its result or error once it has finished."""
        return JobOut.model_validate(find_job(job_id))

    @app.get("/jobs/{job_id}/result")
    def job_result(job_id: str) -> Any:
        """A finished job's result."""
        job = find_job(job_id)
        if job.state is JobState.RUNNING:
            raise HTTPException(409, f"the {job.kind} job is still running")
        if job.state is JobState.FAILED:
            raise HTTPException(409, f"the {job.kind} job has no result: {job.error}")
        return job.result

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(HOME_PAGE)

    @app.post("/convert")
    def convert_file(file: UploadFile) -> FileResponse:
        """Convert an uploaded audio or video file to standard WAV and send it back."""
        name = Path(file.filename or "audio").name
        work = Path(tempfile.mkdtemp(prefix="voicewright-convert-"))
        sent = False
        try:
            # Saved under a fixed name: ffmpeg reads the format from the contents, not the name.
            source, converted = work / "upload", work / "converted.wav"
            with source.open("wb") as saved:
                shutil.copyfileobj(file.file, saved)
            convert(source, converted)
            sent = True
        except UnsupportedAudio:
            raise HTTPException(
                415, f"{name} has no audio Voicewright can read; use {SUPPORTED}"
            ) from None
        except FfmpegMissing:
            raise HTTPException(
                503, "ffmpeg isn't installed, so files can't be converted; brew install ffmpeg"
            ) from None
        finally:
            # On success the folder goes once the WAV has been sent; on any failure, now.
            if not sent:
                shutil.rmtree(work, ignore_errors=True)
        return FileResponse(
            converted,
            media_type="audio/wav",
            filename=f"{Path(name).stem}.wav",
            background=BackgroundTask(shutil.rmtree, work),
        )

    return app
