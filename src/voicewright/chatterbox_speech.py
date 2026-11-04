"""The real speech engine: Chatterbox on MLX (chatterbox-mlx, the hybrid backend).

Optional: needs `pip install -e '.[speech]'` on Apple Silicon. It is imported only when the
model loads, so the app and its tests run without it.
"""

import gc
from pathlib import Path

from voicewright.engines import ModelLoadError, raise_if_out_of_memory
from voicewright.wav import standard_wav

MODEL = "speech model"
# Above this many words, Chatterbox's long-text path keeps narration from cutting off.
LONG_TEXT_WORDS = 50


def load() -> "ChatterboxSpeech":
    """Load Chatterbox into memory: about 14 to 16 GB, so only through the ModelManager."""
    try:
        from chatterbox.tts_mlx import ChatterboxTTSMLX
    except ImportError:
        raise ModelLoadError(
            MODEL, "chatterbox-mlx isn't installed; run .venv/bin/pip install -e '.[speech]'"
        ) from None
    try:
        # "mps" is where the PyTorch half (the vocoder) runs; the hybrid class runs the rest on
        # MLX. device="hybrid-mlx" is rejected (docs/design.md, library notes).
        model = ChatterboxTTSMLX.from_pretrained(device="mps")
    except RuntimeError as error:
        raise_if_out_of_memory(error)
        raise
    return ChatterboxSpeech(model)


class ChatterboxSpeech:
    def __init__(self, model):
        self._model = model

    def speak(self, text: str, reference_clip: Path, exaggeration: float, cfg: float) -> bytes:
        generate = (
            self._model.generate_long
            if len(text.split()) > LONG_TEXT_WORDS
            else self._model.generate
        )
        try:
            audio = generate(
                text,
                audio_prompt_path=str(reference_clip),
                exaggeration=exaggeration,
                cfg_weight=cfg,
                show_progress=False,
            )
        except RuntimeError as error:
            raise_if_out_of_memory(error)
            raise
        return standard_wav(audio.squeeze().float().cpu().numpy(), self._model.sr)

    def close(self) -> None:
        self._model = None
        gc.collect()
        # Hand the freed memory back now, before the next model asks for it.
        import mlx.core as mx
        import torch

        mx.clear_cache()
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
