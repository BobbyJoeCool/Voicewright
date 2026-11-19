"""The assembler's edge cases not reached through Script generation (test_generate.py)."""

import wave

import pytest
from fakes import tone_wav
from pydub import AudioSegment

from voicewright.assembler import GAP_MS, assemble


def write(path, data: bytes):
    path.write_bytes(data)
    return path


def silent_wav(path, ms: int):
    AudioSegment.silent(duration=ms, frame_rate=24_000).export(path, format="wav")
    return path


def test_nothing_to_assemble_is_refused(tmp_path):
    with pytest.raises(ValueError, match="nothing to assemble"):
        assemble([], tmp_path / "out.wav")


def test_a_silent_piece_is_kept_silent_rather_than_levelled(tmp_path):
    out = tmp_path / "out.wav"

    duration = assemble([silent_wav(tmp_path / "quiet.wav", 200)], out)

    assert duration == pytest.approx(0.2, abs=0.01)
    assert AudioSegment.from_wav(out).dBFS == float("-inf")


def test_silence_between_tones_keeps_every_piece_and_both_gaps(tmp_path):
    pieces = [
        write(tmp_path / "a.wav", tone_wav(220, 0.1)),
        silent_wav(tmp_path / "b.wav", 100),
        write(tmp_path / "c.wav", tone_wav(440, 0.1)),
    ]
    out = tmp_path / "out.wav"

    duration = assemble(pieces, out)

    assert duration == pytest.approx(0.3 + 2 * GAP_MS / 1000, abs=0.01)
    with wave.open(str(out)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth()) == (1, 2)


def test_a_very_short_piece_gets_no_fade_and_still_assembles(tmp_path):
    # 1 ms: a quarter of it rounds down to no fade at all.
    out = tmp_path / "out.wav"

    duration = assemble([write(tmp_path / "blip.wav", tone_wav(300, 0.001))], out)

    assert duration == pytest.approx(0.001, abs=0.002)
