"""Scripts: parsing tagged text into Segments, and checking them before anything is generated.

A Script is text with three kinds of marker (docs/design.md section 4):

- `[angry]` is an Emotion tag: the speech after it is spoken with that Emotion preset, until the
  next Emotion tag. Speech before any tag is neutral.
- `(laugh)` is a Vocal effect. v1 renders none, so each one is a warning and is skipped.
- `{explosion}` is a Sound effect: the sound saved under that name in the Sound library.

Names are matched ignoring case. A marker that is unclosed, empty, or holds something that
can't be a name is a parse error, reported with where it is, and parsing carries on so that one
check reports every problem at once (spec stories 41 to 44).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from voicewright.default_emotions import NAME as EMOTION_NAME
from voicewright.sound_library import MAX_NAME as MAX_SOUND_NAME
from voicewright.sound_library import SOUND_NAME

NEUTRAL = "neutral"
# A Vocal effect is one word, like an emotion: (laugh), (sigh), (deep-breath).
VOCAL_EFFECT_NAME = re.compile(r"[a-z][a-z0-9_-]*")

SPEECH = "speech"
VOCAL_EFFECT = "vocal_effect"
SOUND_EFFECT = "sound_effect"

_MARKERS = {"[": ("]", "Emotion tag"), "(": (")", "Vocal effect"), "{": ("}", "Sound effect")}
_CLOSERS = {close: opener for opener, (close, _) in _MARKERS.items()}
_EXAMPLES = {"[": "[angry]", "(": "(laugh)", "{": "{door-slam}"}


@dataclass(frozen=True)
class Segment:
    """One ordered piece of a Script: speech (with its emotion), a Vocal effect, or a Sound
    effect. `position` is where it starts in the Script, counting from 0."""

    kind: str
    position: int
    text: str | None = None  # speech only
    emotion: str | None = None  # speech only
    name: str | None = None  # the effect's name, for Vocal and Sound effects


@dataclass(frozen=True)
class Problem:
    """Something to fix or know about, and where: `position` counts characters from 0; `line`
    and `column` count from 1, the way an editor shows them."""

    position: int
    line: int
    column: int
    message: str


@dataclass(frozen=True)
class Tag:
    """An Emotion tag and where it is."""

    emotion: str
    position: int


@dataclass(frozen=True)
class ParsedScript:
    text: str
    segments: list[Segment]
    tags: list[Tag]
    errors: list[Problem]


def locate(text: str, position: int) -> tuple[int, int]:
    """The line and column (from 1) of a character position (from 0)."""
    before = text[:position]
    line = before.count("\n") + 1
    column = position - (before.rfind("\n") + 1) + 1
    return line, column


def problem(text: str, position: int, message: str) -> Problem:
    line, column = locate(text, position)
    return Problem(position, line, column, message)


def parse(text: str) -> ParsedScript:
    """Split a Script into Segments, in order. Never raises: problems come back as errors."""
    segments: list[Segment] = []
    tags: list[Tag] = []
    errors: list[Problem] = []
    emotion = NEUTRAL
    speech_start = 0
    i = 0

    def flush_speech(end: int) -> None:
        raw = text[speech_start:end]
        words = " ".join(raw.split())
        if words:
            start = speech_start + (len(raw) - len(raw.lstrip()))
            segments.append(Segment(SPEECH, start, text=words, emotion=emotion))

    def error(position: int, message: str) -> None:
        errors.append(problem(text, position, message))

    while i < len(text):
        char = text[i]
        if char in _CLOSERS:
            opener = _CLOSERS[char]
            error(i, f"This {char} has no {opener} before it. Remove it, or add the {opener}.")
            flush_speech(i)
            i += 1
            speech_start = i
            continue
        if char not in _MARKERS:
            i += 1
            continue
        close, kind = _MARKERS[char]
        end = _find_close(text, i, close)
        if end is None:
            error(
                i,
                f"This {char} is never closed: a {kind} ends with {close} on the same line, "
                f"like {_EXAMPLES[char]}.",
            )
            flush_speech(i)
            i += 1
            speech_start = i
            continue
        flush_speech(i)
        inside = text[i + 1 : end]
        name = inside.strip().lower()
        bad = _name_problem(char, inside, name)
        if bad:
            error(i, bad)
        elif char == "[":
            emotion = name
            tags.append(Tag(name, i))
        elif char == "(":
            segments.append(Segment(VOCAL_EFFECT, i, name=name))
        else:
            segments.append(Segment(SOUND_EFFECT, i, name=name))
        i = end + 1
        speech_start = i
    flush_speech(len(text))
    if not errors and not any(s.kind in (SPEECH, SOUND_EFFECT) for s in segments):
        error(0, "There's nothing to say or play. Write some text, or add a {sound}.")
    return ParsedScript(text, segments, tags, errors)


def _find_close(text: str, start: int, close: str) -> int | None:
    """Where the marker opened at `start` closes, or None if it doesn't on its own line before
    another bracket begins or ends."""
    for j in range(start + 1, len(text)):
        char = text[j]
        if char == close:
            return j
        if char == "\n" or char in _MARKERS or char in _CLOSERS:
            return None
    return None


def _name_problem(opener: str, inside: str, name: str) -> str | None:
    close, kind = _MARKERS[opener]
    shown = f"{opener}{inside}{close}"
    if not name:
        return f"{shown} is empty: put a name inside, like {_EXAMPLES[opener]}."
    if opener == "[" and not EMOTION_NAME.fullmatch(name):
        return (
            f"{shown} can't be an Emotion tag: an emotion is one word of lowercase letters, "
            "digits, - and _, starting with a letter, like [angry] or [angry-soft]."
        )
    if opener == "(" and not VOCAL_EFFECT_NAME.fullmatch(name):
        return (
            f"{shown} can't be a Vocal effect: an effect is one word, like (laugh). "
            "To have words in brackets spoken, leave the brackets out."
        )
    if opener == "{" and (len(name) > MAX_SOUND_NAME or not SOUND_NAME.fullmatch(name)):
        return (
            f"{shown} can't be a Sound effect: a sound name is lowercase letters, digits, - and "
            f"_, starting with a letter or digit, up to {MAX_SOUND_NAME} characters, "
            "like {door-slam}."
        )
    return None


@dataclass(frozen=True)
class ScriptCheck:
    """What the check found. Ready when nothing is missing and nothing failed to parse;
    warnings (skipped Vocal effects) never stop a Script."""

    parsed: ParsedScript
    missing_emotions: list[str] = field(default_factory=list)
    missing_sounds: list[str] = field(default_factory=list)
    warnings: list[Problem] = field(default_factory=list)

    @property
    def parse_errors(self) -> list[Problem]:
        return self.parsed.errors

    @property
    def segments(self) -> list[Segment]:
        return self.parsed.segments

    @property
    def ready(self) -> bool:
        return not (self.missing_emotions or self.missing_sounds or self.parse_errors)

    def summary(self) -> str:
        """Why a Script isn't ready, in one sentence."""
        parts = []
        if self.missing_emotions:
            names = ", ".join(f"[{e}]" for e in self.missing_emotions)
            parts.append(f"the Voice has no preset for {names}")
        if self.missing_sounds:
            names = ", ".join(f"{{{s}}}" for s in self.missing_sounds)
            parts.append(f"the Sound library has no {names}")
        if self.parse_errors:
            count = len(self.parse_errors)
            parts.append(f"{count} {'tag needs' if count == 1 else 'tags need'} fixing")
        return "The Script can't be generated yet: " + "; ".join(parts) + "."


def check(
    text: str,
    has_emotion: Callable[[str], bool],
    has_sound: Callable[[str], bool],
    supported_effects: Iterable[str] = (),
) -> ScriptCheck:
    """Parse a Script and check it against a Voice's presets, the Sound library, and the Vocal
    effects the vocal-effect engine can render. Nothing is generated here."""
    parsed = parse(text)
    supported = frozenset(supported_effects)
    missing_emotions = _unique(t.emotion for t in parsed.tags if not has_emotion(t.emotion))
    sounds = (s.name for s in parsed.segments if s.kind == SOUND_EFFECT)
    missing_sounds = _unique(name for name in sounds if not has_sound(name))
    warnings = [
        problem(text, s.position, f"({s.name}) is skipped: Vocal effects can't be rendered yet.")
        for s in parsed.segments
        if s.kind == VOCAL_EFFECT and s.name not in supported
    ]
    return ScriptCheck(parsed, missing_emotions, missing_sounds, warnings)


def _unique(names: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(names))
