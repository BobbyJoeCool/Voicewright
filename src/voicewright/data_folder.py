"""The app data folder: one folder outside the repo that holds everything the app stores."""

from dataclasses import dataclass
from pathlib import Path

SUBFOLDERS = ("voices", "drafts", "sounds", "cache", "saved")


@dataclass(frozen=True)
class DataFolder:
    root: Path

    def create(self) -> None:
        for name in SUBFOLDERS:
            (self.root / name).mkdir(parents=True, exist_ok=True)
