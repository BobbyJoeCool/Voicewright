"""Convert in the browser: choose or drop a file, get a standard WAV to play and download
(spec story 56)."""

import wave

import pytest
from fakes import FIXTURES
from playwright.sync_api import Page, expect

from e2e.helpers import area, played


@pytest.mark.parametrize("name", ["tone.mp3", "tone.m4a", "tone.mp4"])
def test_a_file_converts_to_a_wav_to_play_and_download(vw: Page, tmp_path, name):
    area(vw, "convert")
    vw.locator("#convert-file").set_input_files(FIXTURES / name)

    vw.get_by_role("button", name="Convert").click()

    expect(vw.locator("#convert-status")).to_have_text(f"Converted {name}.")
    expect(vw.locator("#convert-result")).to_be_visible()
    assert played(vw, vw.locator("#convert-player"))
    with vw.expect_download() as info:
        vw.get_by_role("link", name="Download WAV").click()
    assert info.value.suggested_filename == f"{name.rsplit('.', 1)[0]}.wav"
    path = tmp_path / "converted.wav"
    info.value.save_as(path)
    with wave.open(str(path)) as converted:
        assert (converted.getnchannels(), converted.getsampwidth()) == (1, 2)


def test_a_dropped_file_converts_like_a_chosen_one(vw: Page):
    area(vw, "convert")
    data = list((FIXTURES / "tone.flac").read_bytes())
    transfer = vw.evaluate_handle(
        """(bytes) => {
            const transfer = new DataTransfer();
            transfer.items.add(new File([new Uint8Array(bytes)], "dropped.flac"));
            return transfer;
        }""",
        data,
    )
    vw.locator("#convert-drop").dispatch_event("drop", {"dataTransfer": transfer})

    vw.get_by_role("button", name="Convert").click()

    expect(vw.locator("#convert-status")).to_have_text("Converted dropped.flac.")


def test_a_file_with_no_audio_gets_a_plain_error(vw: Page):
    area(vw, "convert")
    vw.locator("#convert-file").set_input_files(FIXTURES / "not-audio.txt")

    vw.get_by_role("button", name="Convert").click()

    expect(vw.locator("#convert-error")).to_contain_text(
        "not-audio.txt has no audio Voicewright can read"
    )
    expect(vw.locator("#convert-result")).to_be_hidden()
    expect(vw.get_by_role("button", name="Convert")).to_be_enabled()
