"""The draft area: Draft voices on disk, one folder each under the data folder's drafts/.

A folder holds draft.json and one standard WAV per Emotion preset. Every write is atomic (write
a temp file, then rename), so a crash mid-design leaves a Draft voice with the presets designed
so far, never a half-written file. Draft voices are never cleared on startup.
"""

import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

DRAFT_FILE = "draft.json"
# Draft ids are made here, as 32 hex digits; anything else can't name a draft folder.
DRAFT_ID = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class Preset:
    """An Emotion preset: its Reference clip (a file name in the draft folder) and its values."""

    clip: str
    exaggeration: float
    cfg: float


@dataclass(frozen=True)
class Draft:
    id: str
    description: str
    created: str
    # Every emotion this Draft voice is meant to have, neutral first.
    emotions: tuple[str, ...]
    # The presets designed so far; fewer than `emotions` if designing stopped part way.
    presets: dict[str, Preset]

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(name for name in self.emotions if name not in self.presets)


class DraftStore:
    def __init__(self, root: Path):
        self.root = root

    def create(self, description: str, emotions: list[str]) -> Draft:
        draft = Draft(
            id=uuid.uuid4().hex,
            description=description,
            created=datetime.now(UTC).isoformat(timespec="seconds"),
            emotions=tuple(emotions),
            presets={},
        )
        self._folder(draft.id).mkdir(parents=True)
        self._write(draft)
        return draft

    def get(self, draft_id: str) -> Draft | None:
        if not DRAFT_ID.fullmatch(draft_id):
            return None
        try:
            data = json.loads((self._folder(draft_id) / DRAFT_FILE).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        return Draft(
            id=draft_id,
            description=data["description"],
            created=data["created"],
            emotions=tuple(data["emotions"]),
            presets={name: Preset(**preset) for name, preset in data["presets"].items()},
        )

    def save_preset(
        self, draft: Draft, emotion: str, wav: bytes, exaggeration: float, cfg: float
    ) -> Draft:
        """Keep this clip as the draft's preset for `emotion`; return the updated draft."""
        clip = f"{emotion}.wav"
        atomic_write(self._folder(draft.id) / clip, wav)
        updated = Draft(
            id=draft.id,
            description=draft.description,
            created=draft.created,
            emotions=draft.emotions,
            presets={**draft.presets, emotion: Preset(clip, exaggeration, cfg)},
        )
        self._write(updated)
        return updated

    def clip_path(self, draft_id: str, emotion: str) -> Path | None:
        """The Reference clip of this draft's preset, if it has been designed."""
        draft = self.get(draft_id)
        if draft is None or emotion not in draft.presets:
            return None
        return self._folder(draft_id) / draft.presets[emotion].clip

    def _folder(self, draft_id: str) -> Path:
        return self.root / draft_id

    def _write(self, draft: Draft) -> None:
        data = {
            "description": draft.description,
            "created": draft.created,
            "emotions": list(draft.emotions),
            # The preset file shape from docs/design.md section 3.
            "presets": {
                name: {"clip": p.clip, "exaggeration": p.exaggeration, "cfg": p.cfg}
                for name, p in draft.presets.items()
            },
        }
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        atomic_write(self._folder(draft.id) / DRAFT_FILE, text.encode("utf-8"))


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
