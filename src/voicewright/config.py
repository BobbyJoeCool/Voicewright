"""The local config file: lives outside git and holds the user's settings."""

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

# Written into a new config file. The Output cache (step 4.3) and the Freesound client (step 3.2)
# read these settings once they exist.
DEFAULT_OUTPUT_CACHE_SIZE = 5
DEFAULT_FREESOUND_API_KEY = ""

DATA_FOLDER_EXAMPLE = 'e.g. data_folder = "~/Voicewright"'


class ConfigError(Exception):
    """The config file can't be used; the message names the file and what to fix."""


@dataclass(frozen=True)
class Config:
    data_folder: Path


def default_config_path() -> Path:
    return Path.home() / ".config" / "voicewright" / "config.toml"


def default_data_folder() -> Path:
    return Path.home() / "Voicewright"


def load_config(path: Path) -> Config:
    """Read the config file, writing one with default settings on first run."""
    try:
        if not path.is_file():
            write_default_config(path)
        values = tomllib.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raise ConfigError(f"{path} is not saved as UTF-8; save it as UTF-8 and try again") from None
    except OSError as error:
        raise ConfigError(f"can't use the config file {path}: {error.strerror}") from None
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path} is not valid TOML: {error}") from None
    data_folder = values.get("data_folder")
    if not isinstance(data_folder, str):
        raise ConfigError(
            f"{path} needs data_folder set to a folder path in quotes, {DATA_FOLDER_EXAMPLE}"
        )
    if "\0" in data_folder:
        raise ConfigError(f"{path} has a null character in data_folder; remove it")
    try:
        folder = Path(data_folder).expanduser()
    except RuntimeError:
        raise ConfigError(
            f"{path} sets data_folder under an unknown home folder: {data_folder}"
        ) from None
    if not folder.is_absolute():
        raise ConfigError(
            f"{path} needs data_folder to be a full path or start with ~, {DATA_FOLDER_EXAMPLE}"
        )
    return Config(data_folder=folder)


def write_default_config(path: Path) -> None:
    # json.dumps gives a quoted, escaped string that is also a valid TOML basic string.
    path.parent.mkdir(parents=True, exist_ok=True)
    # Owner-only from the start: the file will hold the Freesound API key.
    path.touch(mode=0o600)
    path.write_text(
        "# Voicewright settings. Keep this file out of git: it can hold your Freesound API key.\n"
        f"data_folder = {json.dumps(str(default_data_folder()))}\n"
        "# How many recent Outputs to keep before the oldest is removed (5 to 10).\n"
        f"output_cache_size = {DEFAULT_OUTPUT_CACHE_SIZE}\n"
        f"freesound_api_key = {json.dumps(DEFAULT_FREESOUND_API_KEY)}\n",
        encoding="utf-8",
    )
