import io
import wave
from pathlib import Path

import pytest

# Each fixture is half a second of a stereo tone at 44.1 kHz, made with ffmpeg.
FIXTURES = Path(__file__).parent / "fixtures"


def upload(client, name: str, content: bytes | None = None):
    """POST a file to the convert endpoint, by default the fixture with this name."""
    data = (FIXTURES / name).read_bytes() if content is None else content
    return client.post("/convert", files={"file": (name, data)})


@pytest.mark.parametrize(
    "name",
    [
        "tone.mp3",
        "tone.m4a",
        "tone.flac",
        "tone.ogg",
        "tone.aac",
        pytest.param("tone.mp4", id="video"),
        pytest.param("tone-stereo-24bit.wav", id="wav-not-yet-standard"),
    ],
)
def test_a_file_converts_to_standard_wav(client, name):
    response = upload(client, name)

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(response.content)) as wav:
        assert wav.getnchannels() == 1, "standard WAV is mono"
        assert wav.getsampwidth() == 2, "standard WAV is 16-bit"
        assert wav.getcomptype() == "NONE", "standard WAV is PCM"
        assert wav.getnframes() / wav.getframerate() == pytest.approx(0.5, abs=0.1)


def test_the_converted_file_is_named_after_the_upload(client):
    response = upload(client, "tone.mp3")

    assert 'filename="tone.wav"' in response.headers["content-disposition"]


@pytest.mark.parametrize(
    "name, content",
    [
        pytest.param("not-audio.txt", None, id="not-audio"),
        pytest.param("silent.mp4", None, id="video-without-sound"),
        pytest.param("broken.mp3", b"ID3 but nothing after it", id="disguised-as-mp3"),
        pytest.param("empty.mp3", b"", id="empty"),
    ],
)
def test_an_unsupported_file_gets_a_clear_error(client, name, content):
    response = upload(client, name, content)

    assert response.status_code == 415
    detail = response.json()["detail"]
    assert name in detail, "the error names the file"
    assert "MP3" in detail, "the error says what does work"


def test_a_missing_ffmpeg_is_reported(client, monkeypatch):
    monkeypatch.setenv("PATH", "")

    response = upload(client, "tone.mp3")

    assert response.status_code == 503
    assert "ffmpeg" in response.json()["detail"]
