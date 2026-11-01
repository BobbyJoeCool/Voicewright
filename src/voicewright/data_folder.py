"""The app data folder: one folder outside the repo that holds everything the app stores."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataFolder:
    root: Path

    @property
    def voices(self) -> Path:
        return self.root / "voices"

    @property
    def drafts(self) -> Path:
        return self.root / "drafts"

    @property
    def sounds(self) -> Path:
        return self.root / "sounds"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def saved(self) -> Path:
        return self.root / "saved"

    def create(self) -> None:
        for folder in (self.voices, self.drafts, self.sounds, self.cache, self.saved):
            folder.mkdir(parents=True, exist_ok=True)
