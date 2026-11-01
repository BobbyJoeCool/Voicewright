import tomllib
from pathlib import Path

DATA_SUBFOLDERS = {"voices", "drafts", "sounds", "cache", "saved"}


def subfolders(folder: Path) -> set[str]:
    return {p.name for p in folder.iterdir() if p.is_dir()} if folder.exists() else set()


def test_first_run_writes_a_config_with_every_setting(start, config_path, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    start(config_path)

    assert config_path.is_file()
    config = tomllib.loads(config_path.read_text())
    assert set(config) == {"data_folder", "output_cache_size", "freesound_api_key"}
    assert 5 <= config["output_cache_size"] <= 10
    assert config["freesound_api_key"] == ""


def test_first_run_creates_the_configured_data_folder(start, write_config, data_folder):
    start(write_config())

    assert subfolders(data_folder) == DATA_SUBFOLDERS


def test_first_run_creates_the_default_data_folder(start, config_path, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    start(config_path)

    default_folder = Path(tomllib.loads(config_path.read_text())["data_folder"])
    assert default_folder.is_relative_to(tmp_path / "home")
    assert subfolders(default_folder) == DATA_SUBFOLDERS


def test_data_folder_under_home_can_be_written_with_a_tilde(
    start, write_config, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    start(write_config(data_folder="~/Audio/Voicewright"))

    assert subfolders(tmp_path / "home" / "Audio" / "Voicewright") == DATA_SUBFOLDERS


def test_first_run_config_is_private_to_the_user(start, config_path, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    start(config_path)

    assert config_path.stat().st_mode & 0o077 == 0, "only the owner may read the API key"


def test_an_empty_config_left_by_an_interrupted_first_run_is_rewritten(
    start, config_path, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    config_path.parent.mkdir(parents=True)
    config_path.write_text("\n")

    start(config_path)

    assert set(tomllib.loads(config_path.read_text())) == {
        "data_folder",
        "output_cache_size",
        "freesound_api_key",
    }


def test_a_config_saved_with_a_byte_order_mark_is_read(start, write_config, data_folder):
    config_path = write_config()
    config_path.write_bytes(b"\xef\xbb\xbf" + config_path.read_bytes())

    start(config_path)

    assert subfolders(data_folder) == DATA_SUBFOLDERS


def test_a_data_folder_can_be_a_link_to_another_drive(start, write_config, tmp_path):
    drive = tmp_path / "external-drive"
    drive.mkdir()
    link = tmp_path / "data-link"
    link.symlink_to(drive)

    start(write_config(data_folder=str(link)))

    assert subfolders(drive) == DATA_SUBFOLDERS


def test_a_rewritten_empty_config_is_private_to_the_user(start, config_path, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    config_path.parent.mkdir(parents=True)
    config_path.write_text("")
    config_path.chmod(0o644)

    start(config_path)

    assert config_path.stat().st_mode & 0o077 == 0, "only the owner may read the API key"
