from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from voicewright.config import ConfigError, load_config
from voicewright.data_folder import DataFolder, MissingLinkTarget

STATIC_FOLDER = Path(__file__).parent / "static"


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
        return FileResponse(STATIC_FOLDER / "index.html")

    return app
