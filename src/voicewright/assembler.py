"""The assembler: stitches a Script's Segment audio into one Output (docs/design.md section 7).

Pieces play in order, one after another (Sound effects never overlay speech in v1), with a short
silence between them. Each piece is brought to the same loudness, so a quiet sound and a loud
line sit together, and gets a few milliseconds of fade at each end so no piece starts or stops
with a click. Speech and sounds come at different sample rates; everything is resampled to the
highest one, so no piece loses detail.

The lengths and levels here are starting points to tune by ear.
"""

from pathlib import Path

from pydub import AudioSegment

# Silence between two pieces: long enough to read as a pause, short enough to keep the pace.
GAP_MS = 350
# Fade at each end of a piece, against clicks where audio starts or stops mid-wave.
FADE_MS = 10
# The loudness every piece is brought to (RMS, in dB below full scale), and the highest peak
# that raising a quiet piece may reach.
TARGET_DBFS = -20.0
PEAK_CEILING_DBFS = -1.0


def assemble(pieces: list[Path], destination: Path) -> float:
    """Write `pieces` (standard WAVs, in order) to `destination` as one standard WAV, and return
    its length in seconds. Raises ValueError if there are no pieces."""
    if not pieces:
        raise ValueError("nothing to assemble")
    sounds = [AudioSegment.from_wav(path) for path in pieces]
    rate = max(sound.frame_rate for sound in sounds)
    gap = AudioSegment.silent(duration=GAP_MS, frame_rate=rate)
    output = AudioSegment.empty().set_frame_rate(rate)
    for index, sound in enumerate(sounds):
        if index:
            output += gap
        output += _prepared(sound, rate)
    output = output.set_channels(1).set_sample_width(2).set_frame_rate(rate)
    output.export(destination, format="wav")
    return len(output) / 1000


def _prepared(sound: AudioSegment, rate: int) -> AudioSegment:
    sound = sound.set_channels(1).set_sample_width(2).set_frame_rate(rate)
    sound = _levelled(sound)
    fade = min(FADE_MS, len(sound) // 4)
    return sound.fade_in(fade).fade_out(fade) if fade else sound


def _levelled(sound: AudioSegment) -> AudioSegment:
    """`sound` at the target loudness, without letting its peak pass the ceiling."""
    if sound.dBFS == float("-inf"):  # silence: nothing to level
        return sound
    gain = TARGET_DBFS - sound.dBFS
    gain = min(gain, PEAK_CEILING_DBFS - sound.max_dBFS)
    return sound.apply_gain(gain)
