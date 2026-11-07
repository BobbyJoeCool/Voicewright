"""The generator: turns a checked Script into one Output (spec stories 36, 45, 46, 48).

Generating has two halves. `prepare` runs in the request, right after the check passes: it
copies what the Script uses (each emotion's Reference clip and values, each sound and its
credit) into a work folder, so a preset retuned or a sound replaced while the job runs can't
change this Output half way through. The job then renders each Segment in order (speech through
the speech engine, Sound effects from the copied sounds; Vocal effects are skipped, as the
check warned) and hands the pieces to the assembler. The finished Output goes into the Output
cache with a record of what made it.
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from voicewright.assembler import assemble
from voicewright.model_manager import ModelManager
from voicewright.output_store import OutputCache
from voicewright.script import SOUND_EFFECT, SPEECH, ScriptCheck, Segment
from voicewright.sound_library import SoundLibrary
from voicewright.voice_library import Voice, VoiceLibrary

# How much of a line the progress message quotes.
EXCERPT_WORDS = 6


class ScriptChanged(Exception):
    """Something the Script uses went away between the check and the copy."""


@dataclass
class Prepared:
    """A checked Script with copies of everything it uses, in its own work folder."""

    work: Path
    script: str
    voice: Voice
    segments: list[Segment]
    warnings: list[str]
    clips: dict[str, Path] = field(default_factory=dict)  # emotion → Reference clip copy
    sound_files: dict[str, Path] = field(default_factory=dict)  # name → sound copy
    credits: list[dict] = field(default_factory=list)  # one per sound used, in order

    def discard(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)

    @property
    def renderable(self) -> list[Segment]:
        """The Segments that make sound: speech and Sound effects (Vocal effects are skipped)."""
        return [s for s in self.segments if s.kind in (SPEECH, SOUND_EFFECT)]

    def record(self) -> dict:
        """What made the Output: kept with it, and in a Saved output's sidecar (story 53)."""
        used = dict.fromkeys(s.emotion for s in self.segments if s.kind == SPEECH)
        return {
            "script": self.script,
            "voice": {
                "id": self.voice.id,
                "name": self.voice.name,
                "description": self.voice.description,
            },
            "presets": {
                emotion: {
                    "exaggeration": self.voice.presets[emotion].exaggeration,
                    "cfg": self.voice.presets[emotion].cfg,
                }
                for emotion in used
            },
            "sounds": self.credits,
            "warnings": self.warnings,
            "segments": len(self.renderable),
        }


def prepare(
    checked: ScriptCheck, voice: Voice, library: VoiceLibrary, sounds: SoundLibrary
) -> Prepared:
    """Copy what a ready Script uses into a new work folder. Raises ScriptChanged."""
    work = Path(tempfile.mkdtemp(prefix="voicewright-script-"))
    prepared = Prepared(
        work=work,
        script=checked.parsed.text,
        voice=voice,
        segments=checked.segments,
        warnings=[w.message for w in checked.warnings],
    )
    try:
        for segment in checked.segments:
            if segment.kind == SPEECH and segment.emotion not in prepared.clips:
                clip = library.clip_path(voice.id, segment.emotion)
                prepared.clips[segment.emotion] = _copy(clip, work / f"clip-{segment.emotion}.wav")
            elif segment.kind == SOUND_EFFECT and segment.name not in prepared.sound_files:
                sound = sounds.get(segment.name)
                if sound is None:
                    raise ScriptChanged(f"{{{segment.name}}} was removed from the Sound library")
                copy = _copy(sounds.audio_path(segment.name), work / f"sound-{segment.name}.wav")
                prepared.sound_files[segment.name] = copy
                prepared.credits.append({"name": sound.name, **asdict(sound.credit)})
    except BaseException:
        prepared.discard()
        raise
    return prepared


def _copy(source: Path | None, destination: Path) -> Path:
    if source is None:
        raise ScriptChanged("the Voice or a sound changed while the Script was being checked")
    try:
        shutil.copyfile(source, destination)
    except FileNotFoundError:
        raise ScriptChanged(
            f"{source.name} was removed while the Script was being checked"
        ) from None
    return destination


def excerpt(text: str) -> str:
    words = text.split()
    shown = " ".join(words[:EXCERPT_WORDS])
    return f"“{shown}…”" if len(words) > EXCERPT_WORDS else f"“{shown}”"


def generate_output(prepared: Prepared, models: ModelManager, cache: OutputCache):
    """Job: render a prepared Script into one Output → {"output_id", "duration", "audio_url"}.

    Progress counts the Segments that make sound: "Segment 3 of 7" (story 48).
    """

    def work(report):
        try:
            pieces = []
            renderable = prepared.renderable
            total = len(renderable)
            has_speech = any(s.kind == SPEECH for s in renderable)
            with models.speech() if has_speech else contextlib.nullcontext() as speech:
                for index, segment in enumerate(renderable):
                    if segment.kind == SPEECH:
                        report(
                            index, total, f"Speaking {excerpt(segment.text)} ({segment.emotion})"
                        )
                        preset = prepared.voice.presets[segment.emotion]
                        wav = speech.speak(
                            segment.text,
                            prepared.clips[segment.emotion],
                            preset.exaggeration,
                            preset.cfg,
                        )
                        piece = prepared.work / f"segment-{index:04}.wav"
                        piece.write_bytes(wav)
                    else:
                        report(index, total, f"Adding {{{segment.name}}}")
                        piece = prepared.sound_files[segment.name]
                    pieces.append(piece)
            report(total, total, "Putting the Output together")
            assembled = prepared.work / "output.wav"
            duration = assemble(pieces, assembled)
            output = cache.add(assembled, duration, prepared.record())
            return {
                "output_id": output.id,
                "duration": output.duration,
                "audio_url": f"/outputs/{output.id}/audio",
            }
        finally:
            prepared.discard()

    return work
