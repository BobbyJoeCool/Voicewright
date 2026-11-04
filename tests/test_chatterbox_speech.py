"""The Chatterbox engine's own logic, against a stand-in for the model: nothing loads here.

Whether the real model sounds right is the smoke test's job (tests/smoke/).
"""

import io
import sys
import wave
from pathlib import Path

import pytest

np = pytest.importorskip("numpy", reason="numpy comes with the speech extra")

from voicewright import chatterbox_speech  # noqa: E402
from voicewright.engines import ModelLoadError, OutOfMemory  # noqa: E402


class Audio:
    """What Chatterbox returns: a tensor shaped (1, samples)."""

    def __init__(self, samples):
        self.samples = np.asarray(samples, dtype=np.float32)

    def squeeze(self):
        return self

    def float(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.samples


class StandInModel:
    sr = 24_000

    def __init__(self, fail_with: Exception | None = None):
        self.calls = []
        self.fail_with = fail_with

    def generate(self, text, **options):
        return self._answer("generate", text, options)

    def generate_long(self, text, **options):
        return self._answer("generate_long", text, options)

    def _answer(self, method, text, options):
        if self.fail_with:
            raise self.fail_with
        self.calls.append((method, text, options))
        return Audio([0.0, 0.5, -0.5, 2.0, -2.0])


def words(count: int) -> str:
    return " ".join(["word"] * count)


@pytest.mark.parametrize(
    "text, method",
    [
        pytest.param(words(50), "generate", id="50-words"),
        pytest.param(words(51), "generate_long", id="51-words"),
    ],
)
def test_text_over_50_words_takes_the_long_text_path(text, method):
    model = StandInModel()

    chatterbox_speech.ChatterboxSpeech(model).speak(text, Path("angry.wav"), 0.7, 0.3)

    assert model.calls[0][0] == method


def test_the_preset_values_and_clip_reach_chatterbox():
    model = StandInModel()

    chatterbox_speech.ChatterboxSpeech(model).speak("Hello.", Path("angry.wav"), 0.7, 0.3)

    _, text, options = model.calls[0]
    assert text == "Hello."
    assert options == {
        "audio_prompt_path": "angry.wav",
        "exaggeration": 0.7,
        "cfg_weight": 0.3,
        "show_progress": False,
    }


def test_speech_comes_back_as_standard_wav_at_the_models_rate():
    clip = chatterbox_speech.ChatterboxSpeech(StandInModel()).speak(
        "Hello.", Path("neutral.wav"), 0.5, 0.5
    )

    with wave.open(io.BytesIO(clip)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 24_000)
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    assert samples.tolist() == [0, 16383, -16383, 32767, -32767], "loud samples are clipped"


@pytest.mark.parametrize(
    "message",
    [
        "[METAL] Command buffer execution failed: Insufficient Memory",
        "MPS backend out of memory (MPS allocated: 17.9 GB)",
    ],
)
def test_running_out_of_memory_is_reported_as_such(message):
    speech = chatterbox_speech.ChatterboxSpeech(StandInModel(fail_with=RuntimeError(message)))

    with pytest.raises(OutOfMemory):
        speech.speak("Hello.", Path("neutral.wav"), 0.5, 0.5)


def test_other_runtime_errors_pass_through():
    speech = chatterbox_speech.ChatterboxSpeech(
        StandInModel(fail_with=RuntimeError("shape mismatch"))
    )

    with pytest.raises(RuntimeError, match="shape mismatch"):
        speech.speak("Hello.", Path("neutral.wav"), 0.5, 0.5)


def test_without_chatterbox_installed_loading_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "chatterbox.tts_mlx", None)  # makes the import fail

    with pytest.raises(ModelLoadError, match=r"pip install -e '\.\[speech\]'"):
        chatterbox_speech.load()
