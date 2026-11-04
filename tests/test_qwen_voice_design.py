"""The Qwen engine's own logic, against a stand-in for the model: nothing loads here.

Whether the real model sounds right is the smoke test's job (tests/smoke/).
"""

import io
import sys
import wave
from types import SimpleNamespace

import pytest

mx = pytest.importorskip("mlx.core", reason="mlx comes with the voice-design extra")

from voicewright import qwen_voice_design  # noqa: E402
from voicewright.engines import ModelLoadError, OutOfMemory  # noqa: E402


class StandInModel:
    sample_rate = 24_000

    def __init__(self, fail_with: Exception | None = None):
        self.calls = []
        self.fail_with = fail_with

    def generate_voice_design(self, **request):
        if self.fail_with:
            raise self.fail_with
        self.calls.append(request)
        # Long text comes back in pieces.
        yield SimpleNamespace(audio=mx.array([0.0, 0.5]))
        yield SimpleNamespace(audio=mx.array([-0.5, 2.0]))


def test_the_neutral_clip_is_told_only_the_description():
    model = StandInModel()

    qwen_voice_design.QwenVoiceDesign(model).design("A gravelly older man. ", "Hello.")

    assert model.calls == [
        {"text": "Hello.", "language": "English", "instruct": "A gravelly older man."}
    ]


@pytest.mark.parametrize(
    "emotion, instruct",
    [
        ("angry", "A gravelly older man. Speaking in an angry tone."),
        ("sad", "A gravelly older man. Speaking in a sad tone."),
    ],
)
def test_a_preset_is_told_the_description_plus_the_emotion(emotion, instruct):
    model = StandInModel()

    qwen_voice_design.QwenVoiceDesign(model).design("A gravelly older man.", "No!", emotion=emotion)

    assert model.calls[0]["instruct"] == instruct


def test_the_pieces_come_back_as_one_standard_wav_at_the_models_rate():
    clip = qwen_voice_design.QwenVoiceDesign(StandInModel()).design("A man.", "Hello.")

    with wave.open(io.BytesIO(clip)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 24_000)
        assert wav.getnframes() == 4, "both pieces, in order"


def test_running_out_of_memory_is_reported_as_such():
    failing = StandInModel(fail_with=RuntimeError("[METAL] Insufficient Memory"))

    with pytest.raises(OutOfMemory):
        qwen_voice_design.QwenVoiceDesign(failing).design("A man.", "Hello.")


def test_without_mlx_audio_installed_loading_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "mlx_audio.tts.utils", None)  # makes the import fail

    with pytest.raises(ModelLoadError, match=r"pip install -e '\.\[voice-design\]'"):
        qwen_voice_design.load()
