import re
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from voicewright.audio_converter import SUPPORTED, FfmpegMissing, UnsupportedAudio, convert
from voicewright.config import ConfigError, load_config
from voicewright.data_folder import DataFolder, MissingLinkTarget

STATIC_FOLDER = Path(__file__).parent / "static"
HOME_PAGE = STATIC_FOLDER / "index.html"


def page_title() -> bytes:
    """The home page's <title> element, as served: how a running Voicewright is recognized."""
    title = re.search(rb"<title>.*?</title>", HOME_PAGE.read_bytes(), re.DOTALL)
    if not title:
        raise RuntimeError(f"{HOME_PAGE} needs a <title>")
    return title.group()


def create_app(config_path: Path) -> FastAPI:
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
