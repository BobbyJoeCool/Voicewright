import json

import pytest
from fastapi.testclient import TestClient

from voicewright.app import create_app


@pytest.fixture(autouse=True)
def work_in_temp_folder(tmp_path, monkeypatch):
    """Run every test from a temp folder, so a relative path can never land in the repo."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def config_path(tmp_path):
    """A config path inside a fresh temp folder; the file does not exist yet."""
    return tmp_path / "config" / "config.toml"


@pytest.fixture
def data_folder(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def write_config(config_path, data_folder):
    """Write a config file pointing at the temp data folder, as a returning user would have."""

    def write(**overrides):
        values = {"data_folder": str(data_folder), "output_cache_size": 5, "freesound_api_key": ""}
        values.update(overrides)
        # json.dumps quotes and escapes strings the way TOML basic strings expect.
        lines = [f"{key} = {json.dumps(value)}" for key, value in values.items()]
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("\n".join(lines) + "\n")
        return config_path

    return write


def run_app(config_path):
    """Run the app in-process with the given config, as the `voicewright` command would."""
    return TestClient(create_app(config_path))


@pytest.fixture
def client(write_config):
    """The app running in-process against a fresh temp data folder."""
    with run_app(write_config()) as client:
        yield client


@pytest.fixture
def start():
    """Start the app once with the given config and check it serves the page."""

    def start(config_path):
        with run_app(config_path) as client:
            assert client.get("/").status_code == 200

    return start
