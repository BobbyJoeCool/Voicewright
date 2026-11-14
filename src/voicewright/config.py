"""The local config file: lives outside git and holds the user's settings."""

import json
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

# How many recent Outputs the Output cache keeps (spec story 50).
DEFAULT_OUTPUT_CACHE_SIZE = 5
OUTPUT_CACHE_RANGE = (5, 10)
DEFAULT_FREESOUND_API_KEY = ""
# The Freesound API key can also come from the environment, which wins over the config file.
FREESOUND_KEY_ENV = "FREESOUND_API_KEY"

DATA_FOLDER_EXAMPLE = 'e.g. data_folder = "~/Voicewright"'


class ConfigError(Exception):
    """The config file can't be used; the message names the file and what to fix."""


@dataclass(frozen=True)
class Config:
    data_folder: Path
    freesound_api_key: str = ""
    output_cache_size: int = DEFAULT_OUTPUT_CACHE_SIZE


def expand_home(text: str) -> Path:
    """This path as typed, with a leading ~ meaning a home folder. Raises RuntimeError if unknown.

    Decided from the text: pathlib turns "./~/x" into "~/x", which would lose the difference
    between a folder named ~ and the home folder.
    """
    return Path(text).expanduser() if text.startswith("~") else Path(text)


def default_config_path() -> Path:
    return Path.home() / ".config" / "voicewright" / "config.toml"


def default_data_folder() -> Path:
    return Path.home() / "Voicewright"


def load_config(path: Path) -> Config:
    """Read the config file, writing one with default settings on first run."""
    try:
        # Follow the folder to where it really is before creating anything: "missing/../x.toml"
        # names an existing x.toml, which must not be overwritten as if it were new, and needs
        # no "missing" folder. Only the folder: a config that is a link stays a link.
        real = Path(os.path.realpath(path.parent)) / path.name
        real.parent.mkdir(parents=True, exist_ok=True)
        # An empty file is what an interrupted first run leaves behind: start it over.
        if not real.is_file() or not real.read_text(encoding="utf-8-sig").strip():
            write_default_config(real)
        values = tomllib.loads(real.read_text(encoding="utf-8-sig"))
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
        folder = expand_home(data_folder)
    except RuntimeError:
        raise ConfigError(
            f"{path} sets data_folder under an unknown home folder: {data_folder}"
        ) from None
    if not folder.is_absolute():
        raise ConfigError(
            f"{path} needs data_folder to be a full path or start with ~, {DATA_FOLDER_EXAMPLE}"
        )
    key = values.get("freesound_api_key", "")
    if not isinstance(key, str):
        raise ConfigError(
            f'{path} needs freesound_api_key in quotes, e.g. freesound_api_key = "abc123"'
        )
    size = values.get("output_cache_size", DEFAULT_OUTPUT_CACHE_SIZE)
    low, high = OUTPUT_CACHE_RANGE
    # bool is an int in Python; output_cache_size = true is a mistake, not 1.
    if isinstance(size, bool) or not isinstance(size, int) or not low <= size <= high:
        raise ConfigError(
            f"{path} needs output_cache_size to be a whole number from {low} to {high}, "
            f"e.g. output_cache_size = {DEFAULT_OUTPUT_CACHE_SIZE}"
        )
    return Config(data_folder=folder, freesound_api_key=key.strip(), output_cache_size=size)


_CACHE_SIZE_LINE = re.compile(
    r"^([ \t]*output_cache_size[ \t]*=[ \t]*)[^\n#]*?([ \t]*(#.*)?)$", re.M
)


def save_output_cache_size(path: Path, size: int) -> None:
    """Change output_cache_size in the config file, leaving everything else as written.

    Raises OSError if the file can't be written.
    """
    # Through any link to the real file, so a linked config stays a link.
    real = Path(os.path.realpath(path))
    text = real.read_text(encoding="utf-8-sig")
    if _CACHE_SIZE_LINE.search(text):
        text = _CACHE_SIZE_LINE.sub(lambda m: f"{m.group(1)}{size}{m.group(2)}", text, count=1)
    else:
        text = text.rstrip("\n") + f"\noutput_cache_size = {size}\n"
    # Written whole and swapped in, owner-only (mkstemp's mode): the file holds the API key.
    from voicewright.drafts import atomic_write

    atomic_write(real, text.encode("utf-8"))


def freesound_api_key(path: Path) -> str:
    """The Freesound API key: from the environment if set, else from the config file now.

    Read each time it's needed, so a key added to the config file works without a restart.
    """
    from_env = os.environ.get(FREESOUND_KEY_ENV, "").strip()
    if from_env:
        return from_env
    try:
        return load_config(path).freesound_api_key
    except ConfigError:
        return ""


def write_default_config(path: Path) -> None:
    """Write the default settings to this file; its folder must already exist."""
    # json.dumps gives a quoted, escaped string that is also a valid TOML basic string.
    # Owner-only before anything is written, new file or not: it will hold the Freesound API key.
    # Opening first means a folder at this path fails here, before its mode could be changed.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w", encoding="utf-8") as file:
        os.fchmod(fd, 0o600)
        file.write(
            "# Voicewright settings. Keep this file out of git: "
            "it can hold your Freesound API key.\n"
            f"data_folder = {json.dumps(str(default_data_folder()))}\n"
            "# How many recent Outputs to keep before the oldest is removed (5 to 10).\n"
            f"output_cache_size = {DEFAULT_OUTPUT_CACHE_SIZE}\n"
            f"freesound_api_key = {json.dumps(DEFAULT_FREESOUND_API_KEY)}\n"
        )
