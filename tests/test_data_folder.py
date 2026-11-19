"""The data folder: created with its subfolders, and a clear error when a link in its path is
broken (an unplugged drive)."""

import pytest

from voicewright.app import create_app
from voicewright.config import ConfigError
from voicewright.data_folder import SUBFOLDERS, DataFolder, MissingLinkTarget


def test_create_makes_every_subfolder_and_is_safe_to_repeat(tmp_path):
    folder = DataFolder(tmp_path / "data")

    folder.create()
    folder.create()

    assert {p.name for p in (tmp_path / "data").iterdir()} == set(SUBFOLDERS)


def test_a_link_to_a_missing_drive_is_reported_with_its_target(tmp_path):
    drive = tmp_path / "Volumes" / "Unplugged"
    link = tmp_path / "drive"
    link.symlink_to(drive)

    with pytest.raises(MissingLinkTarget) as raised:
        DataFolder(link / "Voicewright").create()

    assert raised.value.link == link
    assert raised.value.target == drive.resolve()
    assert not drive.exists(), "nothing was created on the missing drive's path"


def test_a_link_that_works_is_followed(tmp_path):
    drive = tmp_path / "Volumes" / "Plugged"
    drive.mkdir(parents=True)
    link = tmp_path / "drive"
    link.symlink_to(drive)

    DataFolder(link / "Voicewright").create()

    assert (drive / "Voicewright" / "voices").is_dir()


def test_the_app_refuses_to_start_on_a_broken_link_and_says_how_to_fix_it(tmp_path, write_config):
    link = tmp_path / "drive"
    link.symlink_to(tmp_path / "gone")
    config = write_config(data_folder=str(link / "Voicewright"))

    with pytest.raises(ConfigError, match="connect the drive it is on or change data_folder"):
        create_app(config)


def test_the_app_refuses_a_data_folder_it_cannot_create(tmp_path, write_config):
    blocker = tmp_path / "a-file"
    blocker.write_text("not a folder")
    config = write_config(data_folder=str(blocker / "Voicewright"))

    with pytest.raises(ConfigError, match="can't create the data folder"):
        create_app(config)
