import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from voicewright.config import ConfigError, load_config
from voicewright.data_folder import DataFolder

STATIC_FOLDER = Path(__file__).parent / "static"


def create_app(config_path: Path) -> FastAPI:
    config = load_config(config_path)
    folder = config.data_folder
    broken_link = next(
        (p for p in (folder, *folder.parents) if p.is_symlink() and not p.exists()), None
    )
    if broken_link:
        raise ConfigError(
            f"the data folder {folder} set in {config_path} goes through the link {broken_link}, "
            # realpath, unlike Path.resolve, follows a chain of links without raising on a loop.
            f"which links to {os.path.realpath(broken_link)}, which doesn't exist; "
            "connect the drive it is on or change data_folder"
        )
    try:
        DataFolder(folder).create()
    except OSError as error:
        raise ConfigError(
            f"can't create the data folder {folder} set in {config_path}: {error.strerror}"
        ) from None

    app = FastAPI(title="Voicewright")

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(STATIC_FOLDER / "index.html")

    return app
