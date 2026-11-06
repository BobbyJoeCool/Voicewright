import json
import os

import pytest
from fakes import FakeEngines, FakeFreesound
from fastapi.testclient import TestClient

from voicewright.app import create_app
from voicewright.engines import NO_MODELS

# No test loads a real model, even with the speech extra installed: this reaches every app the
# tests start, in-process or as the installed `voicewright` command. The smoke tests opt back in.
os.environ[NO_MODELS] = "1"


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


def run_app(config_path, fakes: FakeEngines | None = None, freesound=None):
    """The FastAPI app built from this config, run in-process (no server, no port).

    Always on fake engines: no test loads a real model. Freesound is the fake too unless a test
    passes a real client (pointed at a local stand-in server, never the internet).
    """
    engines = (fakes or FakeEngines()).engines()
    return TestClient(create_app(config_path, engines, freesound=freesound or FakeFreesound()))


@pytest.fixture
def fakes():
    """The fake engines the `client` app runs on: what they were asked, and how to fail them."""
    return FakeEngines()


@pytest.fixture
def freesound():
    """The fake Freesound the `client` app uses: canned results, and how to make it fail."""
    return FakeFreesound()


@pytest.fixture
def client(write_config, fakes, freesound):
    """The app running in-process against a fresh temp data folder, on fake engines."""
    with run_app(write_config(), fakes, freesound) as client:
        yield client


@pytest.fixture
def start():
    """Start the app once with the given config and check it serves the page."""

    def start(config_path):
        with run_app(config_path) as client:
            assert client.get("/").status_code == 200

    return start
