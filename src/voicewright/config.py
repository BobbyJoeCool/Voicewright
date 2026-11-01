"""The local config file: lives outside git and holds the user's settings."""

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

# Written into a new config file. The Output cache (step 4.3) and the Freesound client (step 3.2)
# read these settings once they exist.
DEFAULT_OUTPUT_CACHE_SIZE = 5
DEFAULT_FREESOUND_API_KEY = ""


@dataclass(frozen=True)
class Config:
    data_folder: Path


def default_config_path() -> Path:
    return Path.home() / ".config" / "voicewright" / "config.toml"


def default_data_folder() -> Path:
    return Path.home() / "Voicewright"


def load_config(path: Path) -> Config:
    """Read the config file, writing one with default settings on first run."""
    if not path.is_file():
        write_default_config(path)
    values = tomllib.loads(path.read_text())
    return Config(data_folder=Path(values["data_folder"]).expanduser())


def write_default_config(path: Path) -> None:
    # json.dumps gives a quoted, escaped string that is also a valid TOML basic string.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Voicewright settings. Keep this file out of git: it can hold your Freesound API key.\n"
        f"data_folder = {json.dumps(str(default_data_folder()))}\n"
        "# How many recent Outputs to keep before the oldest is removed (5 to 10).\n"
        f"output_cache_size = {DEFAULT_OUTPUT_CACHE_SIZE}\n"
        f"freesound_api_key = {json.dumps(DEFAULT_FREESOUND_API_KEY)}\n"
    )
