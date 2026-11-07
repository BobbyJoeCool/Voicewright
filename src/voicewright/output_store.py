"""The Output store: the Output cache and the saved folder (docs/design.md section 8).

Every Output goes into the temporary Output cache under the data folder's cache/: one folder
per Output, named by its id, holding output.wav and output.json (the record of what made it:
the Script, the Voice, the preset values used, and the credits of every sound used).

The cache keeps the last N Outputs (the output_cache_size setting, 5 to 10): adding one past
that removes the oldest, and the cache is emptied when the app starts (spec stories 50, 51, 54).

Folders are written under a hidden name and renamed into place, so a listing never sees half
an Output.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from voicewright.drafts import atomic_write, now

log = logging.getLogger(__name__)

AUDIO_FILE = "output.wav"
RECORD_FILE = "output.json"
OUTPUT_ID = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class Output:
    id: str
    created: str
    duration: float
    record: dict  # script, voice, presets, sounds, warnings


class OutputCache:
    """The temporary Output cache, keeping the newest `size` Outputs."""

    def __init__(self, root: Path, size: int):
        self.root = root
        self._size = size
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        return self._size

    def resize(self, size: int) -> None:
        """Keep `size` Outputs from now on; a smaller size removes the oldest at once."""
        with self._lock:
            self._size = size
            self._evict()

    def clear(self) -> None:
        """Remove every cached Output, and anything half written: done at startup."""
        with self._lock:
            for path in self.root.iterdir() if self.root.is_dir() else ():
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)

    def add(self, wav: Path, duration: float, record: dict) -> Output:
        """Keep the WAV at `wav` (moved, not copied) as a new Output with its record."""
        output = Output(id=uuid.uuid4().hex, created=now(), duration=duration, record=record)
        with self._lock:
            building = self.root / f".{output.id}"
            building.mkdir(parents=True)
            try:
                shutil.move(wav, building / AUDIO_FILE)
                data = {"created": output.created, "duration": duration, **record}
                text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
                atomic_write(building / RECORD_FILE, text.encode("utf-8"))
                building.rename(self.root / output.id)
            except BaseException:
                shutil.rmtree(building, ignore_errors=True)
                raise
            self._evict()
        return output

    def _evict(self) -> None:
        """Remove the oldest Outputs past the size. Call with the lock held."""
        for old in self.list()[self._size :]:
            shutil.rmtree(self.root / old.id, ignore_errors=True)

    def list(self) -> list[Output]:
        """Every cached Output, newest first."""
        found = []
        for folder in self.root.iterdir() if self.root.is_dir() else ():
            if OUTPUT_ID.fullmatch(folder.name) and (output := self.get(folder.name)):
                found.append(output)
        return sorted(found, key=lambda output: output.created, reverse=True)

    def get(self, output_id: str) -> Output | None:
        if not OUTPUT_ID.fullmatch(output_id):
            return None
        path = self.root / output_id / RECORD_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            created, duration = data.pop("created"), float(data.pop("duration"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as error:
            log.warning("skipping the Output in %s: %s", path.parent, error)
            return None
        return Output(output_id, created, duration, data)

    def audio_path(self, output_id: str) -> Path | None:
        if self.get(output_id) is None:
            return None
        return self.root / output_id / AUDIO_FILE


# A Saved output's id doubles as its file names: when it was saved, then whose Voice, then a
# short random part, e.g. 2026-11-07-143022-old-narrator-1a2b3c.
SAVED_ID = re.compile(r"\d{4}-\d{2}-\d{2}-\d{6}-[a-z0-9-]+-[0-9a-f]{6}")


@dataclass(frozen=True)
class SavedOutput:
    id: str
    saved: str
    record: dict  # the sidecar: script, voice, presets, sounds, warnings, duration, …

    @property
    def audio_file(self) -> str:
        return f"{self.id}.wav"

    @property
    def sidecar_file(self) -> str:
        return f"{self.id}.json"


def slug(text: str, fallback: str = "voice") -> str:
    """Text as a file-name part: lowercase letters, digits, and hyphens."""
    words = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return words[:40].rstrip("-") or fallback


class SavedOutputs:
    """The saved folder: Outputs the user chose to keep, never cleaned up (story 52).

    Each is two files side by side, named by its id: the WAV and a sidecar JSON recording the
    Script, the Voice, the preset values used, and the credits for every sound used (story 53),
    so the Output can be reproduced or shared with the right attribution.
    """

    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()

    def save(self, output: Output, audio: Path) -> tuple[SavedOutput, bool]:
        """Copy a cached Output into the saved folder with its sidecar. Saving one already
        saved gives back the first copy. Returns (saved output, whether it is new)."""
        with self._lock:
            for saved in self.list():
                if saved.record.get("output_id") == output.id:
                    return saved, False
            when = datetime.now().astimezone()
            voice = slug(output.record.get("voice", {}).get("name", ""))
            saved_id = f"{when:%Y-%m-%d-%H%M%S}-{voice}-{uuid.uuid4().hex[:6]}"
            sidecar = {
                "saved": when.isoformat(timespec="microseconds"),
                "created": output.created,
                "duration": output.duration,
                "audio": f"{saved_id}.wav",
                "output_id": output.id,
                **output.record,
            }
            saved = SavedOutput(saved_id, sidecar["saved"], sidecar)
            self.root.mkdir(parents=True, exist_ok=True)
            # The WAV first, under a hidden name, then the sidecar: a listing goes by sidecars,
            # so it never shows a Saved output whose audio isn't all there.
            partial = self.root / f".{saved.audio_file}"
            try:
                shutil.copyfile(audio, partial)
                partial.rename(self.root / saved.audio_file)
                text = json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n"
                atomic_write(self.root / saved.sidecar_file, text.encode("utf-8"))
            except BaseException:
                partial.unlink(missing_ok=True)
                (self.root / saved.audio_file).unlink(missing_ok=True)
                raise
            return saved, True

    def list(self) -> list[SavedOutput]:
        """Every Saved output, newest first."""
        found = []
        for path in self.root.glob("*.json") if self.root.is_dir() else ():
            if SAVED_ID.fullmatch(path.stem) and (saved := self.get(path.stem)):
                found.append(saved)
        return sorted(found, key=lambda saved: (saved.saved, saved.id), reverse=True)

    def get(self, saved_id: str) -> SavedOutput | None:
        if not SAVED_ID.fullmatch(saved_id):
            return None
        path = self.root / f"{saved_id}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            saved = SavedOutput(saved_id, str(record["saved"]), record)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as error:
            log.warning("skipping the Saved output %s: %s", path, error)
            return None
        if not (self.root / saved.audio_file).is_file():
            return None
        return saved

    def audio_path(self, saved_id: str) -> Path | None:
        saved = self.get(saved_id)
        return None if saved is None else self.root / saved.audio_file

    def sidecar_path(self, saved_id: str) -> Path | None:
        saved = self.get(saved_id)
        return None if saved is None else self.root / saved.sidecar_file
