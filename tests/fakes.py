"""Fake engines: stand-ins for the large models, so no test ever loads a real one.

Every call returns a short tone with its own pitch, so a test can tell which call made
which clip. The fakes also log each load and close, to check the one-model-at-a-time rule.
"""

import io
import math
import struct
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from voicewright.engines import Engines, ModelLoadError, NoVocalEffects

RATE = 24_000


def tone_wav(frequency: float, seconds: float = 0.1) -> bytes:
    """A standard WAV (16-bit PCM, mono) of a sine tone."""
    frames = int(RATE * seconds)
    samples = (int(12_000 * math.sin(2 * math.pi * frequency * n / RATE)) for n in range(frames))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(b"".join(struct.pack("<h", s) for s in samples))
    return buffer.getvalue()


@dataclass
class Call:
    """One engine call: which model, what it was asked, and the clip it returned."""

    model: str
    inputs: dict
    wav: bytes


@dataclass
class FakeEngines:
    """The fakes for one app, with what they've been asked to do and how to make them fail."""

    events: list[str] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    # Set to an exception to make that model fail when it loads, or when it is used.
    fail_to_load: dict[str, BaseException] = field(default_factory=dict)
    fail_to_run: dict[str, BaseException] = field(default_factory=dict)
    # Called with the call's number (0, 1, …) before each engine call: to pause a job part way,
    # or make one call fail.
    before_call: Callable[[int], None] | None = None
    loaded: set[str] = field(default_factory=set)
    most_loaded_at_once: int = 0

    def engines(self) -> Engines:
        return Engines(
            load_speech=lambda: FakeSpeech(self),
            load_voice_design=lambda: FakeVoiceDesign(self),
            vocal_effects=NoVocalEffects(),
        )

    def clip(self, model: str, **inputs) -> bytes:
        if model not in self.loaded:
            raise AssertionError(f"the {model} was used while not loaded")
        if model in self.fail_to_run:
            raise self.fail_to_run[model]
        if self.before_call is not None:
            self.before_call(len(self.calls))
        wav = tone_wav(220 + 20 * len(self.calls))
        self.calls.append(Call(model, inputs, wav))
        return wav

    def load(self, model: str) -> None:
        if model in self.fail_to_load:
            raise self.fail_to_load[model]
        self.events.append(f"load {model}")
        self.loaded.add(model)
        self.most_loaded_at_once = max(self.most_loaded_at_once, len(self.loaded))

    def close(self, model: str) -> None:
        self.events.append(f"close {model}")
        self.loaded.discard(model)


class FakeSpeech:
    def __init__(self, fakes: FakeEngines):
        self.fakes = fakes
        fakes.load("speech")

    def speak(self, text: str, reference_clip: Path, exaggeration: float, cfg: float) -> bytes:
        return self.fakes.clip(
            "speech", text=text, reference_clip=reference_clip, exaggeration=exaggeration, cfg=cfg
        )

    def close(self) -> None:
        self.fakes.close("speech")


class FakeVoiceDesign:
    def __init__(self, fakes: FakeEngines):
        self.fakes = fakes
        fakes.load("voice design")

    def design(self, description: str, text: str, emotion: str | None = None) -> bytes:
        return self.fakes.clip("voice design", description=description, text=text, emotion=emotion)

    def close(self) -> None:
        self.fakes.close("voice design")


def load_error(model: str, reason: str = "the weights are missing") -> ModelLoadError:
    return ModelLoadError(model, reason)
