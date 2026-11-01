from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from voicewright.config import ConfigError, load_config
from voicewright.data_folder import DataFolder

STATIC_FOLDER = Path(__file__).parent / "static"


def create_app(config_path: Path) -> FastAPI:
    config = load_config(config_path)
    try:
        DataFolder(config.data_folder).create()
    except OSError as error:
        raise ConfigError(
            f"can't create the data folder {config.data_folder} set in {config_path}: "
            f"{error.strerror}"
        ) from None

    app = FastAPI(title="Voicewright")

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(STATIC_FOLDER / "index.html")

    return app
