import threading

import pytest
from conftest import run_app
from fakes import tone_wav

from voicewright.sound_library import (
    BadSoundName,
    Credit,
    SoundExists,
    SoundLibrary,
    SoundMissing,
)

BOOM = Credit(
    title="Big Boom",
    author="soundmaker",
    license="Creative Commons 0",
    source="https://freesound.org/s/101/",
    attribution='"Big Boom" by soundmaker (https://freesound.org/s/101/), Creative Commons 0',
    freesound_id=101,
)
BETTER_BOOM = Credit(
    title="Better Boom",
    author="otherartist",
    license="Attribution 4.0",
    source="https://freesound.org/s/202/",
    attribution='"Better Boom" by otherartist (https://freesound.org/s/202/), Attribution 4.0',
    freesound_id=202,
)


@pytest.fixture
def library(data_folder, client):
    """The Sound library on the same data folder the `client` app uses."""
    return SoundLibrary(data_folder / "sounds")


@pytest.fixture
def wav_file(tmp_path):
    """Write a standard WAV tone to a file; each pitch is a different sound."""

    def write(frequency: float = 440, seconds: float = 0.5):
        path = tmp_path / f"tone-{frequency}-{seconds}.wav"
        path.write_bytes(tone_wav(frequency, seconds))
        return path

    return write


def test_a_stored_sound_is_listed_with_its_credit_and_plays(client, library, wav_file):
    library.add("explosion", wav_file(440), BOOM)

    [sound] = client.get("/sounds").json()

    assert sound["name"] == "explosion"
    assert sound["credit"] == {
        "title": "Big Boom",
        "author": "soundmaker",
        "license": "Creative Commons 0",
        "source": "https://freesound.org/s/101/",
        "attribution": BOOM.attribution,
        "freesound_id": 101,
    }
    assert sound["duration"] == pytest.approx(0.5)
    audio = client.get(sound["audio_url"])
    assert audio.headers["content-type"] == "audio/wav"
    assert audio.content == wav_file(440).read_bytes()


def test_names_differing_only_by_case_are_the_same_sound(client, library, wav_file):
    stored = library.add("Explosion", wav_file(440), BOOM)

    assert stored.name == "explosion"
    assert library.get("EXPLOSION") == library.get("explosion") == stored
    with pytest.raises(SoundExists):
        library.add("explosion", wav_file(550), BETTER_BOOM)
    assert client.get("/sounds/EXPLOSION/audio").content == wav_file(440).read_bytes()
    assert [s["name"] for s in client.get("/sounds").json()] == ["explosion"]


def test_replace_keeps_the_name_and_updates_the_sound_and_its_credit(client, library, wav_file):
    first = library.add("explosion", wav_file(440, 0.5), BOOM)

    replaced = library.replace("Explosion", wav_file(550, 0.25), BETTER_BOOM)

    assert replaced.name == "explosion"
    assert replaced.credit == BETTER_BOOM
    assert replaced.added >= first.added
    [sound] = client.get("/sounds").json()
    assert sound["credit"]["title"] == "Better Boom"
    assert sound["credit"]["freesound_id"] == 202
    assert sound["duration"] == pytest.approx(0.25)
    assert client.get(sound["audio_url"]).content == wav_file(550, 0.25).read_bytes()


def test_replacing_a_sound_that_isnt_there_is_refused(library, wav_file):
    with pytest.raises(SoundMissing):
        library.replace("explosion", wav_file(), BOOM)
    assert library.list() == []


def test_a_removed_sound_is_gone(client, library, wav_file, data_folder):
    library.add("explosion", wav_file(), BOOM)
    library.add("thunder", wav_file(330), BOOM)

    assert client.delete("/sounds/Explosion").status_code == 204

    assert [s["name"] for s in client.get("/sounds").json()] == ["thunder"]
    assert client.get("/sounds/explosion/audio").status_code == 404
    assert not (data_folder / "sounds" / "explosion").exists()
    assert sorted(p.name for p in (data_folder / "sounds").iterdir()) == ["thunder"]


@pytest.mark.parametrize("name", ["explosion", "no such sound", "..%2Fvoices"])
def test_removing_a_sound_that_isnt_there_is_404(client, name):
    response = client.delete(f"/sounds/{name}")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "name",
    ["door slam", "-boom", "_boom", "", "   ", "a" * 61, "../escape", "boom/", "bôom", "{boom}"],
)
def test_a_name_that_cant_go_in_a_script_is_refused(library, wav_file, name):
    with pytest.raises(BadSoundName, match="can't be a sound name"):
        library.add(name, wav_file(), BOOM)
    assert library.list() == []


def test_names_are_trimmed_and_digits_hyphens_and_underscores_are_allowed(library, wav_file):
    for name in ["  door-slam  ", "glass_break", "1up", "a" * 60]:
        library.add(name, wav_file(), BOOM)

    assert [s.name for s in library.list()] == ["1up", "a" * 60, "door-slam", "glass_break"]


def test_sounds_survive_a_restart(write_config, data_folder, wav_file):
    config = write_config()
    with run_app(config):
        SoundLibrary(data_folder / "sounds").add("explosion", wav_file(), BOOM)

    with run_app(config) as client:
        [sound] = client.get("/sounds").json()

    assert sound["name"] == "explosion"
    assert sound["credit"]["author"] == "soundmaker"


def test_a_broken_record_doesnt_hide_the_other_sounds(client, library, wav_file, data_folder):
    library.add("explosion", wav_file(), BOOM)
    library.add("thunder", wav_file(330), BOOM)
    (data_folder / "sounds" / "explosion" / "sound.json").write_text("{not json")
    # Leftovers from an add that was cut off, and a stray file: neither is a sound.
    (data_folder / "sounds" / ".new-0123").mkdir()
    (data_folder / "sounds" / "notes.txt").write_text("hi")

    assert [s["name"] for s in client.get("/sounds").json()] == ["thunder"]


def test_two_adds_under_one_name_at_once_store_one(library, wav_file):
    files = [wav_file(440), wav_file(550)]
    outcomes = []

    def add(path):
        try:
            library.add("explosion", path, BOOM)
            outcomes.append("added")
        except SoundExists:
            outcomes.append("taken")

    threads = [threading.Thread(target=add, args=(path,)) for path in files]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["added", "taken"]
    assert len(library.list()) == 1


def test_an_empty_library_lists_nothing(client):
    assert client.get("/sounds").json() == []
