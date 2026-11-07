"""The Output store: where finished Outputs go (docs/design.md section 8).

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
