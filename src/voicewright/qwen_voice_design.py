"""The real voice design engine: Qwen3-TTS VoiceDesign on MLX, via mlx-audio (ADR 0003).

Optional: needs `pip install -e '.[voice-design]'` on Apple Silicon. Imported only when the model
loads, so the app and its tests run without it.
"""

import gc

from voicewright.engines import ModelLoadError, raise_if_out_of_memory
from voicewright.wav import standard_wav

MODEL = "voice design model"
WEIGHTS = "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16"


def load() -> "QwenVoiceDesign":
    """Load Qwen3-TTS VoiceDesign: about 6 GB, so only through the ModelManager."""
    try:
        from mlx_audio.tts.utils import load_model
    except ImportError:
        raise ModelLoadError(
            MODEL, "mlx-audio isn't installed; run .venv/bin/pip install -e '.[voice-design]'"
        ) from None
    try:
        return QwenVoiceDesign(load_model(WEIGHTS))
    except RuntimeError as error:
        raise_if_out_of_memory(error)
        raise


def instruction(description: str, emotion: str | None) -> str:
    """What Qwen is told about the voice: the description, plus the emotion for a preset."""
    description = description.strip()
    if emotion is None:
        return description
    # The wording the step 0.2 spike used (spikes/test_qwen_design.py), with "an" where it's due.
    article = "an" if emotion[:1] in "aeiou" else "a"
    return f"{description} Speaking in {article} {emotion} tone."


class QwenVoiceDesign:
    def __init__(self, model):
        self._model = model

    def design(self, description: str, text: str, emotion: str | None = None) -> bytes:
        import mlx.core as mx
        import numpy as np

        try:
            pieces = list(
                self._model.generate_voice_design(
                    text=text, language="English", instruct=instruction(description, emotion)
                )
            )
            audio = mx.concatenate([piece.audio for piece in pieces], axis=0)
        except RuntimeError as error:
            raise_if_out_of_memory(error)
            raise
        return standard_wav(np.array(audio), self._model.sample_rate)

    def close(self) -> None:
        self._model = None
        gc.collect()
        import mlx.core as mx

        mx.clear_cache()
