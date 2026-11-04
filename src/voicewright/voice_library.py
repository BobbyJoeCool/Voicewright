"""The Voice library: saved Voices on disk, one folder each under the data folder's voices/.

Editing a saved Voice (adding, regenerating, or retuning a preset) makes a pending take, held
in the draft area at drafts/voices/<voice id>/ so it survives a restart. A pending take changes
the Voice only when accepted; rejecting it leaves the preset as it was. The neutral Reference
clip and the description are locked (spec story 23).

A folder holds voice.json and one standard WAV per Emotion preset. The JSON's presets follow the
preset file shape in docs/design.md section 3 (clip, exaggeration, cfg), plus each preset's
sample sentence, which a regenerated preset reads again (step 2.5).

A Voice is made by accepting a Draft voice: its presets' current takes are copied in, and the
draft (with every other take) is then removed. Folders are named by id, never by the Voice's
name, so a name can be any text and never reaches a path.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from voicewright.drafts import DESIGN, Draft, DraftStore, atomic_write, now

log = logging.getLogger(__name__)

VOICE_FILE = "voice.json"
PENDING_FILE = "pending.json"
VOICE_ID = re.compile(r"[0-9a-f]{32}")
TAKE_ID = re.compile(r"[a-z][a-z0-9_-]*-[0-9a-f]{8}")
NEUTRAL = "neutral"


class VoiceProblem(Exception):
    """The Voice can't do what was asked; the message says why."""


class NameTaken(Exception):
    def __init__(self, name: str, taken_by: str):
        super().__init__(f"a Voice named {taken_by} already exists; pick another name")


class DraftIncomplete(Exception):
    def __init__(self, missing: tuple[str, ...]):
        super().__init__(
            f"the Draft voice has no {', '.join(missing)} preset yet; regenerate it first"
        )


@dataclass(frozen=True)
class SavedPreset:
    clip: str
    exaggeration: float
    cfg: float
    sample: str


@dataclass(frozen=True)
class PendingTake:
    """A take for a saved Voice, waiting to be accepted or rejected.

    A design take is a new Reference clip, for a new or regenerated preset; a preview take is
    a retune, spoken at new values from the preset's current clip.
    """

    id: str
    emotion: str
    kind: str  # DESIGN or PREVIEW
    created: str
    exaggeration: float
    cfg: float
    sample: str

    @property
    def file(self) -> str:
        return f"{self.id}.wav"


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    description: str
    created: str
    presets: dict[str, SavedPreset]


def same_name(a: str, b: str) -> bool:
    """Voice names match ignoring case: "Narrator" and "narrator" would be confusing as two."""
    return a.casefold() == b.casefold()


class VoiceLibrary:
    def __init__(self, root: Path, drafts: DraftStore):
        self.root = root
        self.drafts = drafts
        # Pending takes live in the draft area, which is never cleared on startup.
        self.pending_root = drafts.root / "voices"
        # Two accepts under one name at once must not both pass the name check.
        self._lock = threading.Lock()

    def accept(self, draft: Draft, name: str) -> Voice:
        """Save a Draft voice under `name`, then remove the draft and its takes.

        Raises NameTaken, or DraftIncomplete if a preset hasn't been designed.
        """
        if draft.missing:
            raise DraftIncomplete(draft.missing)
        with self._lock:
            for voice in self.list():
                if same_name(voice.name, name):
                    raise NameTaken(name, voice.name)
            voice = Voice(
                id=uuid.uuid4().hex,
                name=name,
                description=draft.description,
                created=now(),
                presets={},
            )
            # Built in a hidden folder, then renamed into place: a crash never leaves half a
            # Voice in the library.
            building = self.root / f".{voice.id}"
            building.mkdir(parents=True)
            try:
                presets = {}
                for emotion in draft.emotions:
                    preset = draft.presets[emotion.name]
                    clip = f"{emotion.name}.wav"
                    shutil.copyfile(self.drafts.clip_path(draft, emotion.name), building / clip)
                    presets[emotion.name] = SavedPreset(
                        clip, preset.exaggeration, preset.cfg, emotion.sample
                    )
                voice = Voice(voice.id, voice.name, voice.description, voice.created, presets)
                write_voice(building, voice)
                building.rename(self.root / voice.id)
            except BaseException:
                shutil.rmtree(building, ignore_errors=True)
                raise
        self.drafts.discard(draft.id)
        return voice

    def list(self) -> list[Voice]:
        """Every saved Voice, by name."""
        voices = []
        for folder in self.root.iterdir() if self.root.is_dir() else ():
            if VOICE_ID.fullmatch(folder.name) and (voice := self.get(folder.name)):
                voices.append(voice)
        return sorted(voices, key=lambda voice: voice.name.casefold())

    def get(self, voice_id: str) -> Voice | None:
        if not VOICE_ID.fullmatch(voice_id):
            return None
        path = self.root / voice_id / VOICE_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Voice(
                id=voice_id,
                name=data["name"],
                description=data["description"],
                created=data["created"],
                presets={name: SavedPreset(**p) for name, p in data["presets"].items()},
            )
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as error:
            # One broken Voice must not hide the rest of the library.
            log.warning("skipping the Voice in %s: %s", path.parent, error)
            return None

    def clip_path(self, voice_id: str, emotion: str) -> Path | None:
        voice = self.get(voice_id)
        if voice is None or emotion not in voice.presets:
            return None
        return self.root / voice_id / voice.presets[emotion].clip

    # Editing a saved Voice.

    def pending(self, voice_id: str) -> list[PendingTake]:
        """The takes waiting for a decision, oldest first."""
        path = self._pending_folder(voice_id) / PENDING_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        return [PendingTake(**take) for take in data]

    def add_pending(
        self,
        voice_id: str,
        emotion: str,
        kind: str,
        wav: bytes,
        exaggeration: float,
        cfg: float,
        sample: str,
    ) -> PendingTake:
        with self._lock:
            self._must_get(voice_id)
            take = PendingTake(
                id=f"{emotion}-{uuid.uuid4().hex[:8]}",
                emotion=emotion,
                kind=kind,
                created=now(),
                exaggeration=exaggeration,
                cfg=cfg,
                sample=sample,
            )
            folder = self._pending_folder(voice_id)
            folder.mkdir(parents=True, exist_ok=True)
            atomic_write(folder / take.file, wav)
            self._write_pending(voice_id, [*self.pending(voice_id), take])
            return take

    def pending_take_path(self, voice_id: str, take_id: str) -> Path | None:
        if not VOICE_ID.fullmatch(voice_id) or not any(
            t.id == take_id for t in self.pending(voice_id)
        ):
            return None
        return self._pending_folder(voice_id) / f"{take_id}.wav"

    def accept_take(self, voice_id: str, take_id: str) -> Voice:
        """Let a pending take replace (or add) its preset. A retune changes only the values."""
        with self._lock:
            voice = self._must_get(voice_id)
            takes = self.pending(voice_id)
            take = self._must_find(takes, take_id)
            folder = self.root / voice_id
            current = voice.presets.get(take.emotion)
            if take.kind == DESIGN:
                if take.emotion == NEUTRAL and current is not None:
                    raise VoiceProblem(
                        "the neutral Reference clip is locked once the Voice is saved"
                    )
                # A new file name for the new clip, so nothing still playing the old one breaks.
                clip = f"{take.id}.wav"
                shutil.copyfile(self._pending_folder(voice_id) / take.file, folder / clip)
                preset = SavedPreset(clip, take.exaggeration, take.cfg, take.sample)
            else:
                if current is None:
                    raise VoiceProblem(f"the Voice no longer has a {take.emotion} preset")
                preset = SavedPreset(current.clip, take.exaggeration, take.cfg, current.sample)
            updated = Voice(
                voice.id,
                voice.name,
                voice.description,
                voice.created,
                {**voice.presets, take.emotion: preset},
            )
            write_voice(folder, updated)
            if current is not None and current.clip != preset.clip:
                (folder / current.clip).unlink(missing_ok=True)
            self._drop_pending(voice_id, takes, [take])
            return updated

    def reject_take(self, voice_id: str, take_id: str) -> None:
        """Throw a pending take away; the preset stays as it was."""
        with self._lock:
            self._must_get(voice_id)
            takes = self.pending(voice_id)
            self._drop_pending(voice_id, takes, [self._must_find(takes, take_id)])

    def remove_preset(self, voice_id: str, emotion: str) -> Voice:
        """Remove any preset but neutral, with its pending takes."""
        if emotion == NEUTRAL:
            raise VoiceProblem("neutral can't be removed: untagged text is spoken with it")
        with self._lock:
            voice = self._must_get(voice_id)
            if emotion not in voice.presets:
                raise LookupError(emotion)
            presets = {name: p for name, p in voice.presets.items() if name != emotion}
            updated = Voice(voice.id, voice.name, voice.description, voice.created, presets)
            write_voice(self.root / voice_id, updated)
            (self.root / voice_id / voice.presets[emotion].clip).unlink(missing_ok=True)
            takes = self.pending(voice_id)
            self._drop_pending(voice_id, takes, [t for t in takes if t.emotion == emotion])
            return updated

    def delete(self, voice_id: str) -> bool:
        """Delete a Voice, its clips, and its pending takes. False if there was no such Voice."""
        with self._lock:
            if self.get(voice_id) is None:
                return False
            shutil.rmtree(self.root / voice_id)
            shutil.rmtree(self._pending_folder(voice_id), ignore_errors=True)
            return True

    def _must_get(self, voice_id: str) -> Voice:
        voice = self.get(voice_id)
        if voice is None:
            raise LookupError(voice_id)
        return voice

    @staticmethod
    def _must_find(takes: list[PendingTake], take_id: str) -> PendingTake:
        take = next((t for t in takes if t.id == take_id), None)
        if take is None:
            raise LookupError(take_id)
        return take

    def _pending_folder(self, voice_id: str) -> Path:
        return self.pending_root / voice_id

    def _drop_pending(self, voice_id: str, takes: list[PendingTake], drop: list[PendingTake]):
        keep = [t for t in takes if t not in drop]
        self._write_pending(voice_id, keep)
        for take in drop:
            (self._pending_folder(voice_id) / take.file).unlink(missing_ok=True)

    def _write_pending(self, voice_id: str, takes: list[PendingTake]) -> None:
        folder = self._pending_folder(voice_id)
        if not takes:
            shutil.rmtree(folder, ignore_errors=True)
            return
        text = json.dumps([t.__dict__ for t in takes], indent=2, ensure_ascii=False) + "\n"
        atomic_write(folder / PENDING_FILE, text.encode("utf-8"))


def write_voice(folder: Path, voice: Voice) -> None:
    data = {
        "name": voice.name,
        "description": voice.description,
        "created": voice.created,
        "presets": {name: p.__dict__ for name, p in voice.presets.items()},
    }
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    atomic_write(folder / VOICE_FILE, text.encode("utf-8"))
