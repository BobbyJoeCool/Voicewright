"""The draft area: Draft voices on disk, one folder each under the data folder's drafts/.

A folder holds draft.json and one standard WAV per take. A take is any clip made for the draft:
a design take is a Reference clip designed by the voice design engine; a preview take is a
preset's sample sentence spoken by the speech engine with that preset's values, to hear a
retune. Each Emotion preset points at one design take, its current Reference clip. No take is
deleted while the draft is open (spec story 11): regenerating adds a take, and the user can go
back to an earlier one.

Every write is atomic (write a temp file, then rename), so a crash leaves the takes made so far,
never a half-written file. Draft voices are never cleared on startup.
"""

import json
import os
import re
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

DRAFT_FILE = "draft.json"
# Draft ids are made here, as 32 hex digits; anything else can't name a draft folder.
DRAFT_ID = re.compile(r"[0-9a-f]{32}")

DESIGN = "design"
PREVIEW = "preview"


class DraftProblem(Exception):
    """The draft can't do what was asked; the message says why."""


@dataclass(frozen=True)
class Take:
    id: str  # e.g. "angry-2" or "angry-preview-1"; also the WAV's file name, plus ".wav"
    emotion: str
    kind: str  # DESIGN or PREVIEW
    created: str
    # A design take: the description it was designed from.
    description: str | None = None
    # A preview take: the values it was spoken with, and the design take it cloned.
    exaggeration: float | None = None
    cfg: float | None = None
    clip: str | None = None

    @property
    def file(self) -> str:
        return f"{self.id}.wav"


@dataclass(frozen=True)
class Preset:
    """An Emotion preset: its current Reference clip (a design take) and its values."""

    take: str
    exaggeration: float
    cfg: float


@dataclass(frozen=True)
class Emotion:
    """What a Draft voice's emotion is designed from: its sample sentence and starting values."""

    name: str
    sample: str
    exaggeration: float
    cfg: float


@dataclass(frozen=True)
class Draft:
    id: str
    description: str
    created: str
    # Every emotion this Draft voice is meant to have, neutral first.
    emotions: tuple[Emotion, ...]
    # The presets designed so far; fewer than `emotions` if designing stopped part way.
    presets: dict[str, Preset]
    takes: tuple[Take, ...]

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(e.name for e in self.emotions if e.name not in self.presets)

    def emotion(self, name: str) -> Emotion | None:
        return next((e for e in self.emotions if e.name == name), None)

    def take(self, take_id: str) -> Take | None:
        return next((t for t in self.takes if t.id == take_id), None)


class DraftStore:
    def __init__(self, root: Path):
        self.root = root
        # Jobs and requests change drafts from different threads; each change re-reads the
        # draft under this lock, so none is lost.
        self._lock = threading.Lock()

    def create(self, description: str, emotions: list[Emotion]) -> Draft:
        draft = Draft(
            id=uuid.uuid4().hex,
            description=description,
            created=now(),
            emotions=tuple(emotions),
            presets={},
            takes=(),
        )
        self._folder(draft.id).mkdir(parents=True)
        self._write(draft)
        return draft

    def get(self, draft_id: str) -> Draft | None:
        if not DRAFT_ID.fullmatch(draft_id):
            return None
        try:
            text = (self._folder(draft_id) / DRAFT_FILE).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        data = json.loads(text)
        return Draft(
            id=draft_id,
            description=data["description"],
            created=data["created"],
            emotions=tuple(Emotion(**emotion) for emotion in data["emotions"]),
            presets={name: Preset(**preset) for name, preset in data["presets"].items()},
            takes=tuple(Take(**take) for take in data["takes"]),
        )

    def add_design_take(self, draft_id: str, emotion: str, wav: bytes, description: str) -> Draft:
        """Keep a newly designed clip as a take, and make it the preset's Reference clip.

        A preset that already exists keeps its values (they may have been tuned); a new one
        starts from its emotion's starting values.
        """
        with self._lock:
            draft = self._must_get(draft_id)
            take = Take(
                id=self._next_take_id(draft, emotion),
                emotion=emotion,
                kind=DESIGN,
                created=now(),
                description=description,
            )
            atomic_write(self._folder(draft_id) / take.file, wav)
            current = draft.presets.get(emotion)
            start = draft.emotion(emotion)
            preset = (
                replace(current, take=take.id)
                if current
                else Preset(take.id, start.exaggeration, start.cfg)
            )
            return self._save(draft, {**draft.presets, emotion: preset}, take)

    def add_preview_take(
        self, draft_id: str, emotion: str, wav: bytes, clip: str, exaggeration: float, cfg: float
    ) -> Draft:
        """Keep a retune's preview as a take, and give the preset the values it was spoken with."""
        with self._lock:
            draft = self._must_get(draft_id)
            take = Take(
                id=self._next_take_id(draft, emotion, PREVIEW),
                emotion=emotion,
                kind=PREVIEW,
                created=now(),
                exaggeration=exaggeration,
                cfg=cfg,
                clip=clip,
            )
            atomic_write(self._folder(draft_id) / take.file, wav)
            preset = replace(draft.presets[emotion], exaggeration=exaggeration, cfg=cfg)
            return self._save(draft, {**draft.presets, emotion: preset}, take)

    def choose_take(self, draft_id: str, emotion: str, take_id: str) -> Draft:
        """Make an earlier design take of this emotion its Reference clip again."""
        with self._lock:
            draft = self._must_get(draft_id)
            take = draft.take(take_id)
            if take is None or take.emotion != emotion or take.kind != DESIGN:
                raise DraftProblem(f"{take_id} is not a designed {emotion} clip of this draft")
            if emotion not in draft.presets:
                raise DraftProblem(f"this draft has no {emotion} preset yet")
            preset = replace(draft.presets[emotion], take=take_id)
            return self._save(draft, {**draft.presets, emotion: preset})

    def set_description(self, draft_id: str, description: str) -> Draft:
        with self._lock:
            draft = replace(self._must_get(draft_id), description=description)
            self._write(draft)
            return draft

    def list(self) -> list[Draft]:
        """Every Draft voice still open, oldest first: what the page offers to resume."""
        found = []
        for folder in self.root.iterdir() if self.root.is_dir() else ():
            if DRAFT_ID.fullmatch(folder.name) and (draft := self.get(folder.name)):
                found.append(draft)
        return sorted(found, key=lambda draft: draft.created)

    def discard(self, draft_id: str) -> bool:
        """Remove a Draft voice and every take. False if there was no such draft."""
        if not DRAFT_ID.fullmatch(draft_id) or not self._folder(draft_id).is_dir():
            return False
        with self._lock:
            shutil.rmtree(self._folder(draft_id))
        return True

    def take_path(self, draft_id: str, take_id: str) -> Path | None:
        draft = self.get(draft_id)
        take = draft.take(take_id) if draft else None
        return None if take is None else self._folder(draft_id) / take.file

    def clip_path(self, draft: Draft, emotion: str) -> Path:
        """The current Reference clip of a preset the draft has."""
        return self._folder(draft.id) / draft.take(draft.presets[emotion].take).file

    def _must_get(self, draft_id: str) -> Draft:
        draft = self.get(draft_id)
        if draft is None:
            raise DraftProblem(f"the Draft voice {draft_id} no longer exists")
        return draft

    def _next_take_id(self, draft: Draft, emotion: str, kind: str = DESIGN) -> str:
        stem = emotion if kind == DESIGN else f"{emotion}-{PREVIEW}"
        count = sum(1 for t in draft.takes if t.emotion == emotion and t.kind == kind)
        return f"{stem}-{count + 1}"

    def _save(self, draft: Draft, presets: dict[str, Preset], take: Take | None = None) -> Draft:
        takes = draft.takes if take is None else (*draft.takes, take)
        updated = replace(draft, presets=presets, takes=takes)
        self._write(updated)
        return updated

    def _folder(self, draft_id: str) -> Path:
        return self.root / draft_id

    def _write(self, draft: Draft) -> None:
        data = {
            "description": draft.description,
            "created": draft.created,
            "emotions": [e.__dict__ for e in draft.emotions],
            "presets": {name: p.__dict__ for name, p in draft.presets.items()},
            "takes": [
                {key: value for key, value in t.__dict__.items() if value is not None}
                for t in draft.takes
            ],
        }
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        atomic_write(self._folder(draft.id) / DRAFT_FILE, text.encode("utf-8"))


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")  # orders drafts made in one second


def atomic_write(path: Path, content: bytes) -> None:
    """Replace `path` with `content` all at once: readers see the old file or the new one."""
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
