"""The engine interfaces: the narrow seams between the app and its models.

Each engine takes plain inputs and returns standard WAV bytes. Real engines load a large
model; tests swap every engine for a fake (tests/fakes.py). The speech and voice design
engines are large models, so they are only ever reached through the ModelManager.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ModelLoadError(Exception):
    """A model couldn't be loaded. The message is shown to the user as written."""

    def __init__(self, model: str, reason: str):
        super().__init__(f"couldn't load the {model}: {reason}")
        self.model = model


class OutOfMemory(Exception):
    """A model ran out of memory. Real engines raise this for their library's own OOM error."""


class UnsupportedVocalEffect(Exception):
    """The vocal-effect engine can't render this effect; the Script checker warns before this."""


class LargeModel(Protocol):
    def close(self) -> None:
        """Release the model's memory. The engine isn't used again after this."""


class SpeechEngine(LargeModel, Protocol):
    def speak(self, text: str, reference_clip: Path, exaggeration: float, cfg: float) -> bytes:
        """Say `text` in the voice of `reference_clip`, with these Emotion preset values."""


class VoiceDesignEngine(LargeModel, Protocol):
    def design(self, description: str, text: str, emotion: str | None = None) -> bytes:
        """Say `text` in a voice designed from `description`, in `emotion` if one is given."""


class VocalEffectEngine(Protocol):
    supported_effects: frozenset[str]

    def render(self, effect: str, reference_clip: Path) -> bytes:
        """The effect (e.g. "laugh") in the voice of `reference_clip`."""


class NoVocalEffects:
    """The v1 vocal-effect engine: supports no effects, so every Vocal effect is a warning."""

    supported_effects: frozenset[str] = frozenset()

    def render(self, effect: str, reference_clip: Path) -> bytes:
        raise UnsupportedVocalEffect(f"Vocal effects aren't supported, so ({effect}) is skipped")


@dataclass(frozen=True)
class Engines:
    """What the app runs on. Loaders load a large model each time they are called."""

    load_speech: Callable[[], SpeechEngine]
    load_voice_design: Callable[[], VoiceDesignEngine]
    vocal_effects: VocalEffectEngine


def not_available(model: str) -> Callable[[], LargeModel]:
    def load() -> LargeModel:
        raise ModelLoadError(model, "it isn't part of this version of Voicewright yet")

    return load


def default_engines() -> Engines:
    """The engines a plain `voicewright` runs on."""
    # The real speech engine (Chatterbox) arrives in step 1.4, voice design (Qwen3-TTS) in 2.2.
    return Engines(
        load_speech=not_available("speech model"),
        load_voice_design=not_available("voice design model"),
        vocal_effects=NoVocalEffects(),
    )
