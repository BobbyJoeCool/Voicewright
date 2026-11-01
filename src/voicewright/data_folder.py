"""The app data folder: one folder outside the repo that holds everything the app stores."""

import os
from dataclasses import dataclass
from pathlib import Path

SUBFOLDERS = ("voices", "drafts", "sounds", "cache", "saved")


class MissingLinkTarget(Exception):
    """The data folder goes through a link whose target isn't there (e.g. an unplugged drive)."""

    def __init__(self, link: Path):
        self.link = link
        # realpath, unlike Path.resolve, follows a chain of links without raising on a loop.
        self.target = Path(os.path.realpath(link))


@dataclass(frozen=True)
class DataFolder:
    root: Path

    def create(self) -> None:
        """Create the data folder and its subfolders. Raises MissingLinkTarget or OSError."""
        for path in (self.root, *self.root.parents):
            if path.is_symlink() and not path.exists():
                raise MissingLinkTarget(path)
        for name in SUBFOLDERS:
            (self.root / name).mkdir(parents=True, exist_ok=True)
