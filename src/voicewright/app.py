import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

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

    return app
