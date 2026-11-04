"""The Default emotion set: the emotions every new Voice starts with.

They live in default_emotions.json, so adding one is an edit to that file, not to code. Each has
the sample sentence its Emotion preset reads and its starting Chatterbox values (ADR 0002),
which are starting points to tune by ear.
"""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_EMOTIONS_FILE = Path(__file__).parent / "default_emotions.json"

# Written in a Script as [name], so a name is lowercase letters, digits, - and _.
NAME = re.compile(r"[a-z][a-z0-9_-]*")
# Chatterbox's ranges: exaggeration 0 (flat) to 2 (very intense), cfg 0 to 1.
EXAGGERATION_RANGE = (0.0, 2.0)
CFG_RANGE = (0.0, 1.0)


class DefaultEmotionsError(Exception):
    """The Default emotion set file can't be used; the message says what to fix."""


@dataclass(frozen=True)
class DefaultEmotion:
    name: str
    sample: str
    exaggeration: float
    cfg: float


def load_default_emotions(path: Path = DEFAULT_EMOTIONS_FILE) -> tuple[DefaultEmotion, ...]:
    """Read the Default emotion set, in file order. Raises DefaultEmotionsError."""
    try:
        entries = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_repeats)
    except OSError as error:
        raise DefaultEmotionsError(f"can't read {path}: {error.strerror}") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DefaultEmotionsError(f"{path} is not valid JSON: {error}") from None
    except RepeatedName as repeated:
        raise DefaultEmotionsError(f"{path} lists {repeated} more than once") from None
    if not isinstance(entries, dict):
        raise DefaultEmotionsError(f'{path} needs an object of emotions, like {{"neutral": …}}')
    if "neutral" not in entries:
        raise DefaultEmotionsError(f"{path} needs a neutral emotion: every Voice is built on it")
    return tuple(emotion(path, name, entry) for name, entry in entries.items())


class RepeatedName(ValueError):
    pass


def no_repeats(pairs: list[tuple[str, object]]) -> dict:
    """A JSON object, refusing a name given twice: JSON would quietly keep only the last."""
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise RepeatedName(key)
        seen[key] = value
    return seen


def emotion(path: Path, name: str, entry) -> DefaultEmotion:
    where = f"{path}, emotion {name!r}"
    if not NAME.fullmatch(name):
        raise DefaultEmotionsError(
            f"{where}: a name is lowercase letters, digits, - and _, starting with a letter"
        )
    if not isinstance(entry, dict):
        raise DefaultEmotionsError(f"{where} needs sample, exaggeration, and cfg")
    if set(entry) != {"sample", "exaggeration", "cfg"}:
        unknown = sorted(set(entry) - {"sample", "exaggeration", "cfg"})
        missing = sorted({"sample", "exaggeration", "cfg"} - set(entry))
        problems = [f"missing {', '.join(missing)}"] if missing else []
        problems += [f"unknown {', '.join(unknown)}"] if unknown else []
        raise DefaultEmotionsError(f"{where}: {'; '.join(problems)}")
    sample = entry["sample"]
    if not isinstance(sample, str) or not sample.strip():
        raise DefaultEmotionsError(f"{where} needs a sample sentence")
    return DefaultEmotion(
        name=name,
        sample=sample.strip(),
        exaggeration=value_in(where, "exaggeration", entry["exaggeration"], EXAGGERATION_RANGE),
        cfg=value_in(where, "cfg", entry["cfg"], CFG_RANGE),
    )


def value_in(where: str, key: str, value, bounds: tuple[float, float]) -> float:
    low, high = bounds
    # bool is an int in Python; true is not a setting.
    is_number = isinstance(value, int | float) and not isinstance(value, bool)
    if not is_number or not math.isfinite(value) or not low <= value <= high:
        raise DefaultEmotionsError(f"{where}: {key} must be a number from {low:g} to {high:g}")
    return float(value)
