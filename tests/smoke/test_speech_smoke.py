"""Smoke test of the real speech model on the M2. Slow, and run by hand:

    .venv/bin/pytest -m smoke -s

Needs the speech extra (pip install -e '.[speech]'), and loads Chatterbox: about 15 GB, so close
other heavy apps first. Excluded from the default `pytest` run, which never loads a real model.
"""

import io
import shutil
import subprocess
import sys
import time
import wave

import pytest

from voicewright.audio_converter import convert
from voicewright.engines import NO_MODELS, default_engines
from voicewright.model_manager import ModelManager

pytestmark = pytest.mark.smoke

SHORT_LINE = "Hello there. This is a quick test of the speech engine."
# 120 words: well over the 50-word line where the long-text path takes over.
PASSAGE = (
    "The road out of town runs past the old grain elevator and down along the river. "
    "Most mornings it is quiet, just the wind in the cottonwoods and a few trucks heading "
    "for the highway. I have driven it so many times that I could do it with my eyes closed, "
    "but I never do, because there is always something new to see. A heron stood "
    "in the shallows like a statue, and a fox crossed in front of me without even looking up. "
    "In the fall the fields turn gold and the light comes in low and slow. It is the kind of "
    "road that makes you want to keep driving long after you should have turned back home."
)


@pytest.fixture(scope="module")
def speech():
    """The real speech model, loaded once for these tests, through the model manager."""
    if sys.platform != "darwin":
        pytest.skip("the speech model runs on Apple Silicon only")
    pytest.importorskip("chatterbox.tts_mlx", reason="needs pip install -e '.[speech]'")
    with pytest.MonkeyPatch.context() as env:
        env.delenv(NO_MODELS, raising=False)
        models = ModelManager(default_engines())
    started = time.perf_counter()
    models.preload_speech()
    print(f"\n  loaded the speech model in {time.perf_counter() - started:.0f}s")
    with models.speech() as engine:
        yield engine


@pytest.fixture(scope="module")
def reference_clip(tmp_path_factory):
    """A neutral Reference clip of real speech, recorded offline with macOS `say`."""
    if shutil.which("say") is None:
        pytest.skip("needs macOS `say` to record a Reference clip")
    folder = tmp_path_factory.mktemp("smoke")
    spoken = folder / "reference.aiff"
    subprocess.run(
        ["say", "-o", str(spoken), "This is my normal speaking voice, calm and clear. " * 3],
        check=True,
    )
    clip = folder / "reference.wav"
    convert(spoken, clip)
    return clip


def render(speech, reference_clip, text: str, name: str) -> float:
    """Render `text`, save it next to the Reference clip to listen to; return its length."""
    started = time.perf_counter()
    clip = speech.speak(text, reference_clip, exaggeration=0.5, cfg=0.5)
    took = time.perf_counter() - started
    with wave.open(io.BytesIO(clip)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth()) == (1, 2), "standard WAV"
        seconds = wav.getnframes() / wav.getframerate()
    out = reference_clip.parent / name
    out.write_bytes(clip)
    print(f"  {name}: {seconds:.1f}s of audio in {took:.0f}s (RTF {took / seconds:.2f}) -> {out}")
    return seconds


def test_a_short_line_renders(speech, reference_clip):
    seconds = render(speech, reference_clip, SHORT_LINE, "short.wav")

    assert 1.5 < seconds < 15


def test_a_120_word_passage_renders_without_cutting_off(speech, reference_clip):
    assert len(PASSAGE.split()) == 120

    seconds = render(speech, reference_clip, PASSAGE, "passage.wav")

    # Chatterbox reads this passage at about 4.4 words a second (measured on the M2, 1.0.6 and
    # 1.3.1, 26 to 29 s). Under 20 s means at least one of its five chunks went missing. A chunk
    # that ends a few words early only shows when you listen: play passage.wav.
    assert seconds > 120 / 6, "the passage was cut off"
    assert seconds < 120
