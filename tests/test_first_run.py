import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

from voicewright.app import create_app

DATA_SUBFOLDERS = {"voices", "drafts", "sounds", "cache", "saved"}


def subfolders(folder: Path) -> set[str]:
    return {p.name for p in folder.iterdir() if p.is_dir()} if folder.exists() else set()


def start(config_path):
    with TestClient(create_app(config_path)) as client:
        assert client.get("/").status_code == 200


def test_first_run_writes_a_config_with_every_setting(config_path, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    start(config_path)

    assert config_path.is_file()
    config = tomllib.loads(config_path.read_text())
    assert set(config) == {"data_folder", "output_cache_size", "freesound_api_key"}
    assert 5 <= config["output_cache_size"] <= 10
    assert config["freesound_api_key"] == ""


def test_first_run_creates_the_configured_data_folder(write_config, data_folder):
    start(write_config())

    assert subfolders(data_folder) == DATA_SUBFOLDERS


def test_first_run_creates_the_default_data_folder(config_path, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    start(config_path)

    default_folder = Path(tomllib.loads(config_path.read_text())["data_folder"])
    assert default_folder.is_relative_to(tmp_path / "home")
    assert subfolders(default_folder) == DATA_SUBFOLDERS


def test_data_folder_under_home_can_be_written_with_a_tilde(write_config, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    start(write_config(data_folder="~/Audio/Voicewright"))

    assert subfolders(tmp_path / "home" / "Audio" / "Voicewright") == DATA_SUBFOLDERS
