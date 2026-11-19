"""The Sound library: named sounds that Sound effects in a Script resolve to (ADR 0001).

Each sound lives in its own folder under the data folder's sounds/, named by the sound's name:
sound.wav (standard WAV) and sound.json (its credit: where it came from, who made it, and its
license and attribution, for the credits in a Saved output's record).

Names are lowercase. A name typed with capitals means the same sound ("Explosion" is
"explosion"), so `{Explosion}` and `{explosion}` in a Script play the same file. Because a name
is checked against SOUND_NAME before it reaches a path, it is safe as a folder name.

Adding or replacing writes a hidden folder first and then renames it into place, so a reader
sees the old sound or the new one, never half of each.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import uuid
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

from voicewright.drafts import now

log = logging.getLogger(__name__)

SOUND_FILE = "sound.wav"
CREDIT_FILE = "sound.json"
# What can go inside {} in a Script: lowercase letters, digits, - and _, e.g. {door-slam}.
SOUND_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
MAX_NAME = 60
NAME_RULE = (
    "a sound name is lowercase letters, digits, - and _, starting with a letter or digit, "
    f"up to {MAX_NAME} characters, e.g. door-slam"
)


class BadSoundName(ValueError):
    def __init__(self, text: str):
        super().__init__(f"{text!r} can't be a sound name: {NAME_RULE}")


class SoundExists(Exception):
    def __init__(self, name: str):
        super().__init__(
            f"the Sound library already has {{{name}}}; replace it or pick another name"
        )
        self.name = name


class SoundMissing(Exception):
    def __init__(self, name: str):
        super().__init__(f"the Sound library has no {{{name}}}")
        self.name = name


def sound_name(text: str) -> str:
    """The sound name `text` means: trimmed and lowercased. Raises BadSoundName."""
    name = text.strip().lower()
    if len(name) > MAX_NAME or not SOUND_NAME.fullmatch(name):
        raise BadSoundName(text)
    return name


@dataclass(frozen=True)
class Credit:
    """Where a sound came from, for crediting it (spec story 31)."""

    title: str  # the sound's own name at its source
    author: str
    license: str
    source: str  # the sound's page, e.g. https://freesound.org/s/12345/
    attribution: str  # the line to credit it with
    freesound_id: int | None = None


@dataclass(frozen=True)
class Sound:
    name: str
    added: str
    duration: float  # seconds
    credit: Credit


class SoundLibrary:
    def __init__(self, root: Path):
        self.root = root
        # Two adds under one name at once must not both pass the "not taken" check.
        self._lock = threading.Lock()

    def list(self) -> list[Sound]:
        """Every sound, by name. A sound whose record can't be read is skipped with a warning."""
        sounds = []
        for folder in sorted(self.root.iterdir()) if self.root.is_dir() else []:
            if folder.name.startswith(".") or not SOUND_NAME.fullmatch(folder.name):
                continue
            sound = self._read(folder.name)
            if sound is not None:
                sounds.append(sound)
        return sounds

    def get(self, name: str) -> Sound | None:
        """The sound `name` means, ignoring case; None if there's none (or the name is bad)."""
        try:
            return self._read(sound_name(name))
        except BadSoundName:
            return None

    def audio_path(self, name: str) -> Path | None:
        sound = self.get(name)
        return self._folder(sound.name) / SOUND_FILE if sound else None

    def add(self, name: str, wav: Path, credit: Credit) -> Sound:
        """Store the standard WAV at `wav` as `name`. Raises BadSoundName or SoundExists."""
        name = sound_name(name)
        with self._lock:
            if self._folder(name).exists():
                raise SoundExists(name)
            return self._write(name, wav, credit)

    def replace(self, name: str, wav: Path, credit: Credit) -> Sound:
        """Swap the sound behind `name`, keeping the name (spec story 33). Raises SoundMissing."""
        name = self._existing(name)
        with self._lock:
            if not self._folder(name).exists():
                raise SoundMissing(name)
            return self._write(name, wav, credit)

    def remove(self, name: str) -> None:
        """Remove the sound and its record. Raises SoundMissing."""
        name = self._existing(name)
        with self._lock:
            folder = self._folder(name)
            if not folder.exists():
                raise SoundMissing(name)
            # Renamed away first, so a reader never finds a folder with half its files gone.
            gone = self.root / f".removed-{uuid.uuid4().hex}"
            folder.rename(gone)
            shutil.rmtree(gone, ignore_errors=True)

    # --- On disk ----------------------------------------------------------------------------

    def _existing(self, name: str) -> str:
        try:
            return sound_name(name)
        except BadSoundName:
            # No sound can have a name that breaks the rule.
            raise SoundMissing(name.strip().lower()) from None

    def _folder(self, name: str) -> Path:
        return self.root / name

    def _write(self, name: str, wav: Path, credit: Credit) -> Sound:
        sound = Sound(name=name, added=now(), duration=wav_seconds(wav), credit=credit)
        self.root.mkdir(parents=True, exist_ok=True)
        staging = self.root / f".new-{uuid.uuid4().hex}"
        staging.mkdir()
        try:
            shutil.copyfile(wav, staging / SOUND_FILE)
            (staging / CREDIT_FILE).write_text(json.dumps(record(sound), indent=2) + "\n")
            folder = self._folder(name)
            old = None
            if folder.exists():
                old = self.root / f".old-{uuid.uuid4().hex}"
                folder.rename(old)
            staging.rename(folder)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        if old is not None:
            shutil.rmtree(old, ignore_errors=True)
        return sound

    def _read(self, name: str) -> Sound | None:
        folder = self._folder(name)
        if not (folder / CREDIT_FILE).is_file():
            return None
        try:
            data = json.loads((folder / CREDIT_FILE).read_text())
            credit = Credit(**data["credit"])
            return Sound(
                name=name, added=data["added"], duration=float(data["duration"]), credit=credit
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            log.warning("skipping the sound %s: can't read %s: %s", name, CREDIT_FILE, error)
            return None


def record(sound: Sound) -> dict:
    """sound.json's contents. The name is the folder's, so it isn't repeated."""
    return {"added": sound.added, "duration": sound.duration, "credit": asdict(sound.credit)}


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as wav:
        return round(wav.getnframes() / wav.getframerate(), 3)
