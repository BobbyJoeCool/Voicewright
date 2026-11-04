"""The Voice library: saved Voices on disk, one folder each under the data folder's voices/.

A folder holds voice.json and one standard WAV per Emotion preset. The JSON's presets follow the
preset file shape in docs/design.md section 3 (clip, exaggeration, cfg), plus each preset's
sample sentence, which a regenerated preset reads again (step 2.5).

A Voice is made by accepting a Draft voice: its presets' current takes are copied in, and the
draft (with every other take) is then removed. Folders are named by id, never by the Voice's
name, so a name can be any text and never reaches a path.
"""

import json
import logging
import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from voicewright.drafts import Draft, DraftStore, atomic_write, now

log = logging.getLogger(__name__)

VOICE_FILE = "voice.json"
VOICE_ID = re.compile(r"[0-9a-f]{32}")


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


def write_voice(folder: Path, voice: Voice) -> None:
    data = {
        "name": voice.name,
        "description": voice.description,
        "created": voice.created,
        "presets": {name: p.__dict__ for name, p in voice.presets.items()},
    }
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    atomic_write(folder / VOICE_FILE, text.encode("utf-8"))
