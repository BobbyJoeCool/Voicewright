from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from voicewright.config import load_config
from voicewright.data_folder import DataFolder

STATIC_FOLDER = Path(__file__).parent / "static"


def create_app(config_path: Path) -> FastAPI:
    config = load_config(config_path)
    DataFolder(config.data_folder).create()

    app = FastAPI(title="Voicewright")

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(STATIC_FOLDER / "index.html")

    return app
