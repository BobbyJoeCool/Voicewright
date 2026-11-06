import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.background import BackgroundTask

from voicewright.audio_converter import SUPPORTED, FfmpegMissing, UnsupportedAudio, convert
from voicewright.config import FREESOUND_KEY_ENV, ConfigError, freesound_api_key, load_config
from voicewright.data_folder import DataFolder, MissingLinkTarget
from voicewright.default_emotions import (
    CFG_RANGE,
    DEFAULT_EMOTIONS_FILE,
    EXAGGERATION_RANGE,
    load_default_emotions,
)
from voicewright.default_emotions import NAME as EMOTION_NAME
from voicewright.drafts import Draft, DraftProblem, DraftStore
from voicewright.engines import Engines, default_engines
from voicewright.freesound import (
    Freesound,
    FreesoundClient,
    FreesoundSound,
    FreesoundSoundMissing,
    FreesoundUnavailable,
)
from voicewright.jobs import Job, JobAlreadyRunning, JobRunner, JobState
from voicewright.model_manager import ModelManager
from voicewright.sound_library import (
    Credit,
    Sound,
    SoundExists,
    SoundLibrary,
    SoundMissing,
    sound_name,
)
from voicewright.voice_design import (
    design_draft_voice,
    redesign_draft_voice,
    regenerate_preset,
    retune_preset,
)
from voicewright.voice_editing import GENERIC_SAMPLE, design_pending_take, retune_saved_preset
from voicewright.voice_library import (
    NEUTRAL,
    DraftIncomplete,
    NameTaken,
    Voice,
    VoiceLibrary,
    VoiceProblem,
)

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
    # The current Reference clip: a design take.
    take: str
    clip_url: str


class TakeOut(BaseModel):
    id: str
    emotion: str
    kind: str  # "design" (a Reference clip) or "preview" (a retune, spoken by the speech model)
    created: str
    url: str
    description: str | None = None
    exaggeration: float | None = None
    cfg: float | None = None
    clip: str | None = None


class DraftOut(BaseModel):
    id: str
    description: str
    created: str
    emotions: list[str]
    presets: dict[str, PresetOut]
    # Emotions not designed yet: designing is still running, or stopped part way.
    missing: list[str]
    # Every clip made for this draft, oldest first; none is deleted while the draft is open.
    takes: list[TakeOut]

    @classmethod
    def of(cls, draft: Draft) -> "DraftOut":
        def url(take_id: str) -> str:
            return f"/voices/drafts/{draft.id}/takes/{take_id}"

        return cls(
            id=draft.id,
            description=draft.description,
            created=draft.created,
            emotions=[emotion.name for emotion in draft.emotions],
            presets={
                name: PresetOut(
                    exaggeration=preset.exaggeration,
                    cfg=preset.cfg,
                    take=preset.take,
                    clip_url=url(preset.take),
                )
                for name, preset in draft.presets.items()
            },
            missing=list(draft.missing),
            takes=[TakeOut(**take.__dict__, url=url(take.id)) for take in draft.takes],
        )


class AcceptRequest(BaseModel):
    draft_id: str
    name: str = Field(max_length=60)

    @field_validator("name")
    @classmethod
    def tidy(cls, name: str) -> str:
        name = " ".join(name.split())
        if not name:
            raise ValueError("give the Voice a name, e.g. Old Narrator")
        if any(not ch.isprintable() for ch in name):
            raise ValueError("a Voice name can't hold control characters")
        return name


class SavedPresetOut(BaseModel):
    exaggeration: float
    cfg: float
    sample: str
    clip_url: str


class PendingTakeOut(BaseModel):
    id: str
    emotion: str
    kind: str  # "design" (a new Reference clip) or "preview" (a retune at new values)
    created: str
    exaggeration: float
    cfg: float
    sample: str
    url: str


class VoiceOut(BaseModel):
    id: str
    name: str
    description: str
    created: str
    presets: dict[str, SavedPresetOut]
    # Takes waiting to be accepted or rejected, oldest first.
    pending: list[PendingTakeOut]

    @classmethod
    def of(cls, voice: Voice, pending=()) -> "VoiceOut":
        return cls(
            id=voice.id,
            name=voice.name,
            description=voice.description,
            created=voice.created,
            pending=[
                PendingTakeOut(**take.__dict__, url=f"/voices/{voice.id}/takes/{take.id}")
                for take in pending
            ],
            presets={
                name: SavedPresetOut(
                    exaggeration=p.exaggeration,
                    cfg=p.cfg,
                    sample=p.sample,
                    clip_url=f"/voices/{voice.id}/clips/{name}",
                )
                for name, p in voice.presets.items()
            },
        )


class AddPresetRequest(BaseModel):
    name: str
    sample: str | None = Field(default=None, max_length=500)
    exaggeration: float | None = Field(
        default=None, ge=EXAGGERATION_RANGE[0], le=EXAGGERATION_RANGE[1]
    )
    cfg: float | None = Field(default=None, ge=CFG_RANGE[0], le=CFG_RANGE[1])

    @field_validator("name")
    @classmethod
    def emotion_name(cls, name: str) -> str:
        name = name.strip().lower()
        if not EMOTION_NAME.fullmatch(name):
            raise ValueError(
                "an emotion name is lowercase letters, digits, - and _, starting with a letter"
            )
        return name

    @field_validator("sample")
    @classmethod
    def tidy_sample(cls, sample: str | None) -> str | None:
        sample = " ".join(sample.split()) if sample else ""
        return sample or None


class RetuneRequest(BaseModel):
    exaggeration: float = Field(ge=EXAGGERATION_RANGE[0], le=EXAGGERATION_RANGE[1])
    cfg: float = Field(ge=CFG_RANGE[0], le=CFG_RANGE[1])


class ChooseTake(BaseModel):
    take: str


class CreditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    author: str
    license: str
    source: str
    attribution: str
    freesound_id: int | None = None


class SoundOut(BaseModel):
    name: str
    added: str
    duration: float
    credit: CreditOut
    audio_url: str

    @classmethod
    def of(cls, sound: Sound) -> "SoundOut":
        return cls(
            name=sound.name,
            added=sound.added,
            duration=sound.duration,
            credit=CreditOut.model_validate(sound.credit),
            audio_url=f"/sounds/{sound.name}/audio",
        )


class FreesoundSoundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    author: str
    license: str
    url: str
    duration: float
    preview_url: str


class SearchOut(BaseModel):
    results: list[FreesoundSoundOut]
    count: int
    page: int
    has_next: bool


class AddSoundRequest(BaseModel):
    freesound_id: int = Field(gt=0)
    name: str

    @field_validator("name")
    @classmethod
    def a_sound_name(cls, name: str) -> str:
        return sound_name(name)


class ReplaceSoundRequest(BaseModel):
    freesound_id: int = Field(gt=0)


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
    freesound: Freesound | None = None,
) -> FastAPI:
    """The app, on the given engines and Freesound client (the real ones unless a test passes
    fakes).

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
    library = VoiceLibrary(folder / "voices", drafts)
    sounds = SoundLibrary(folder / "sounds")
    if freesound is None:
        freesound = FreesoundClient(
            lambda: freesound_api_key(config_path),
            key_hint=f"{config_path} as freesound_api_key (or the {FREESOUND_KEY_ENV} "
            "environment variable)",
        )
    app.state.jobs = jobs
    app.state.models = models

    @app.exception_handler(FreesoundUnavailable)
    def freesound_unavailable(request: Request, error: FreesoundUnavailable) -> JSONResponse:
        # The rest of the app keeps working: only Freesound search and adding fail (story 35).
        return JSONResponse(status_code=503, content={"detail": str(error), "reason": error.reason})

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

    @app.get("/voices/drafts")
    def list_drafts() -> list[DraftOut]:
        """Every Draft voice still open, oldest first, so the page can offer resume or discard."""
        return [DraftOut.of(draft) for draft in drafts.list()]

    @app.delete("/voices/drafts/{draft_id}", status_code=204)
    def discard_draft(draft_id: str) -> None:
        """Discard a Draft voice and every take."""
        if not drafts.discard(draft_id):
            raise HTTPException(404, f"no Draft voice {draft_id}")

    @app.post("/voices", status_code=201)
    def accept_draft(request: AcceptRequest) -> VoiceOut:
        """Save a Draft voice to the library under a name; the draft and its takes go."""
        draft = find_draft(request.draft_id)
        try:
            return voice_out(library.accept(draft, request.name))
        except (NameTaken, DraftIncomplete) as problem:
            raise HTTPException(409, str(problem)) from None

    def voice_out(voice: Voice) -> VoiceOut:
        return VoiceOut.of(voice, library.pending(voice.id))

    def find_voice(voice_id: str) -> Voice:
        voice = library.get(voice_id)
        if voice is None:
            raise HTTPException(404, f"no Voice {voice_id}")
        return voice

    def find_preset(voice: Voice, emotion: str) -> None:
        if emotion not in voice.presets:
            raise HTTPException(404, f"{voice.name} has no {emotion} preset")

    def wav(path: Path) -> FileResponse:
        # A saved preset's clip can be replaced: make the browser ask again each time.
        return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "no-cache"})

    @app.get("/voices")
    def list_voices() -> list[VoiceOut]:
        """Every saved Voice, by name, with its Emotion presets and pending takes."""
        return [voice_out(voice) for voice in library.list()]

    @app.get("/voices/{voice_id}")
    def get_voice(voice_id: str) -> VoiceOut:
        return voice_out(find_voice(voice_id))

    @app.delete("/voices/{voice_id}", status_code=204)
    def delete_voice(voice_id: str) -> None:
        """Delete a saved Voice, its clips, and its pending takes."""
        if not library.delete(voice_id):
            raise HTTPException(404, f"no Voice {voice_id}")

    @app.get("/voices/{voice_id}/clips/{emotion}")
    def get_voice_clip(voice_id: str, emotion: str) -> FileResponse:
        """A saved Emotion preset's Reference clip, as standard WAV."""
        clip = library.clip_path(voice_id, emotion)
        if clip is None:
            raise HTTPException(404, f"no {emotion} preset on Voice {voice_id}")
        return wav(clip)

    @app.post("/voices/{voice_id}/presets", status_code=202)
    def add_preset(voice_id: str, request: AddPresetRequest) -> JobStarted:
        """Design a custom Emotion preset as a pending take. Values start from neutral's."""
        voice = find_voice(voice_id)
        if request.name in voice.presets:
            raise HTTPException(409, f"{voice.name} already has a {request.name} preset")
        neutral = voice.presets[NEUTRAL]
        work = design_pending_take(
            library,
            models,
            voice_id,
            request.name,
            request.sample or GENERIC_SAMPLE,
            neutral.exaggeration if request.exaggeration is None else request.exaggeration,
            neutral.cfg if request.cfg is None else request.cfg,
        )
        return JobStarted(job_id=jobs.start("voice design", work).id)

    @app.post("/voices/{voice_id}/presets/{emotion}/regenerate", status_code=202)
    def regenerate_saved(voice_id: str, emotion: str) -> JobStarted:
        """Design a new clip for a preset, as a pending take. The neutral clip is locked."""
        voice = find_voice(voice_id)
        find_preset(voice, emotion)
        if emotion == NEUTRAL:
            raise HTTPException(409, "the neutral Reference clip is locked once the Voice is saved")
        preset = voice.presets[emotion]
        work = design_pending_take(
            library, models, voice_id, emotion, preset.sample, preset.exaggeration, preset.cfg
        )
        return JobStarted(job_id=jobs.start("voice design", work).id)

    @app.post("/voices/{voice_id}/presets/{emotion}/retune", status_code=202)
    def retune_saved(voice_id: str, emotion: str, request: RetuneRequest) -> JobStarted:
        """Hear a preset at new values, as a pending take; accepting it keeps the values."""
        find_preset(find_voice(voice_id), emotion)
        work = retune_saved_preset(
            library, models, voice_id, emotion, request.exaggeration, request.cfg
        )
        return JobStarted(job_id=jobs.start("retune", work).id)

    @app.delete("/voices/{voice_id}/presets/{emotion}")
    def remove_preset(voice_id: str, emotion: str) -> VoiceOut:
        """Remove any preset but neutral."""
        find_preset(find_voice(voice_id), emotion)
        try:
            return voice_out(library.remove_preset(voice_id, emotion))
        except VoiceProblem as problem:
            raise HTTPException(409, str(problem)) from None

    @app.get("/voices/{voice_id}/takes/{take_id}")
    def get_pending_take(voice_id: str, take_id: str) -> FileResponse:
        path = library.pending_take_path(voice_id, take_id)
        if path is None:
            raise HTTPException(404, f"no pending take {take_id} on Voice {voice_id}")
        return wav(path)

    @app.post("/voices/{voice_id}/takes/{take_id}/accept")
    def accept_take(voice_id: str, take_id: str) -> VoiceOut:
        """Let a pending take replace (or add) its preset."""
        find_voice(voice_id)
        try:
            return voice_out(library.accept_take(voice_id, take_id))
        except LookupError:
            raise HTTPException(404, f"no pending take {take_id}") from None
        except VoiceProblem as problem:
            raise HTTPException(409, str(problem)) from None

    @app.delete("/voices/{voice_id}/takes/{take_id}", status_code=204)
    def reject_take(voice_id: str, take_id: str) -> None:
        """Reject a pending take; the preset stays as it was."""
        find_voice(voice_id)
        try:
            library.reject_take(voice_id, take_id)
        except LookupError:
            raise HTTPException(404, f"no pending take {take_id}") from None

    @app.get("/voices/drafts/{draft_id}")
    def get_draft(draft_id: str) -> DraftOut:
        """A Draft voice: its description and the presets designed so far, with clip URLs."""
        return DraftOut.of(find_draft(draft_id))

    def find_emotion(draft: Draft, emotion: str) -> None:
        if draft.emotion(emotion) is None:
            raise HTTPException(404, f"the Draft voice has no {emotion} emotion")

    @app.get("/voices/drafts/{draft_id}/takes/{take_id}")
    def get_draft_take(draft_id: str, take_id: str) -> FileResponse:
        """One take, as standard WAV."""
        find_draft(draft_id)
        path = drafts.take_path(draft_id, take_id)
        if path is None:
            raise HTTPException(404, f"the Draft voice has no take {take_id}")
        return FileResponse(path, media_type="audio/wav")

    @app.post("/voices/drafts/{draft_id}/presets/{emotion}/regenerate", status_code=202)
    def regenerate(draft_id: str, emotion: str) -> JobStarted:
        """Design a new take of one preset, or of the neutral clip; the others stay as they are."""
        find_emotion(find_draft(draft_id), emotion)
        work = regenerate_preset(drafts, models, draft_id, emotion)
        return JobStarted(job_id=jobs.start("voice design", work).id)

    @app.post("/voices/drafts/{draft_id}/presets/{emotion}/retune", status_code=202)
    def retune(draft_id: str, emotion: str, request: RetuneRequest) -> JobStarted:
        """Hear a preset at new exaggeration and cfg values, which become its values."""
        draft = find_draft(draft_id)
        find_emotion(draft, emotion)
        if emotion not in draft.presets:
            raise HTTPException(409, f"the {emotion} preset has no clip yet; regenerate it first")
        work = retune_preset(drafts, models, draft_id, emotion, request.exaggeration, request.cfg)
        return JobStarted(job_id=jobs.start("retune", work).id)

    @app.post("/voices/drafts/{draft_id}/redesign", status_code=202)
    def redesign(draft_id: str, request: DesignRequest) -> JobStarted:
        """Change the description, then design a new take of every preset from it."""
        find_draft(draft_id)
        work = redesign_draft_voice(drafts, models, draft_id, request.description)
        return JobStarted(job_id=jobs.start("voice design", work).id)

    @app.put("/voices/drafts/{draft_id}/presets/{emotion}")
    def choose_take(draft_id: str, emotion: str, request: ChooseTake) -> DraftOut:
        """Go back to an earlier designed take as this preset's Reference clip."""
        find_emotion(find_draft(draft_id), emotion)
        try:
            return DraftOut.of(drafts.choose_take(draft_id, emotion, request.take))
        except DraftProblem as problem:
            raise HTTPException(409, str(problem)) from None

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

    @app.get("/sounds")
    def list_sounds() -> list[SoundOut]:
        """The Sound library, by name, with each sound's credit."""
        return [SoundOut.of(sound) for sound in sounds.list()]

    @app.get("/sounds/search")
    def search_freesound(
        q: str = Query(min_length=1, max_length=200), page: int = Query(1, ge=1, le=1000)
    ) -> SearchOut:
        """One page of Freesound results, each with its preview and license (stories 26-28)."""
        query = " ".join(q.split())
        if not query:
            raise HTTPException(422, "type what to search Freesound for")
        found = freesound.search(query, page)
        return SearchOut(
            results=[FreesoundSoundOut.model_validate(s) for s in found.results],
            count=found.count,
            page=found.page,
            has_next=found.has_next,
        )

    def fetched_from_freesound(freesound_id: int, work: Path) -> tuple[Path, Credit]:
        """Download a Freesound sound into `work` as standard WAV, with its credit."""
        try:
            found: FreesoundSound = freesound.sound(freesound_id)
            audio = freesound.download(found)
        except FreesoundSoundMissing as missing:
            raise HTTPException(404, str(missing)) from None
        source, converted = work / "download", work / "sound.wav"
        source.write_bytes(audio)
        try:
            convert(source, converted)
        except UnsupportedAudio:
            raise HTTPException(
                502, f"Freesound's file for {found.title!r} has no audio Voicewright can read"
            ) from None
        except FfmpegMissing:
            raise HTTPException(
                503, "ffmpeg isn't installed, so sounds can't be converted; brew install ffmpeg"
            ) from None
        credit = Credit(
            title=found.title,
            author=found.author,
            license=found.license,
            source=found.url,
            attribution=found.attribution,
            freesound_id=found.id,
        )
        return converted, credit

    @app.post("/sounds", status_code=201)
    def add_sound(request: AddSoundRequest) -> SoundOut:
        """Download a Freesound result, convert it, and keep it under a name (stories 29-31)."""
        if sounds.get(request.name) is not None:
            raise HTTPException(409, str(SoundExists(request.name)))
        with tempfile.TemporaryDirectory(prefix="voicewright-sound-") as work:
            wav_path, credit = fetched_from_freesound(request.freesound_id, Path(work))
            try:
                return SoundOut.of(sounds.add(request.name, wav_path, credit))
            except SoundExists as taken:
                raise HTTPException(409, str(taken)) from None

    @app.put("/sounds/{name}")
    def replace_sound(name: str, request: ReplaceSoundRequest) -> SoundOut:
        """Swap the sound behind a name for another Freesound result, keeping the name."""
        if sounds.get(name) is None:
            raise HTTPException(404, f"the Sound library has no {{{name.strip().lower()}}}")
        with tempfile.TemporaryDirectory(prefix="voicewright-sound-") as work:
            wav_path, credit = fetched_from_freesound(request.freesound_id, Path(work))
            try:
                return SoundOut.of(sounds.replace(name, wav_path, credit))
            except SoundMissing as missing:
                raise HTTPException(404, str(missing)) from None

    @app.get("/sounds/{name}/audio")
    def get_sound_audio(name: str) -> FileResponse:
        """A sound's audio, as standard WAV. The name is matched ignoring case."""
        path = sounds.audio_path(name)
        if path is None:
            raise HTTPException(404, f"the Sound library has no {{{name.lower()}}}")
        return wav(path)

    @app.delete("/sounds/{name}", status_code=204)
    def remove_sound(name: str) -> None:
        """Remove a sound from the library."""
        try:
            sounds.remove(name)
        except SoundMissing as missing:
            raise HTTPException(404, str(missing)) from None

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(HOME_PAGE)

    app.mount("/static", StaticFiles(directory=STATIC_FOLDER), name="static")

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
