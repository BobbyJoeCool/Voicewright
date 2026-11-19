"""The Freesound client: search, and fetch one sound to add to the Sound library (ADR 0001).

Search and download only. Generation never calls it: Sound effects play from the local Sound
library. Tests use a fake with the same interface (tests/fakes.py), so no test reaches the network.

What gets downloaded is the sound's high-quality preview (OGG, about 192 kbps), not the original
upload: Freesound requires OAuth2, a per-user login flow, for original files, while an API key
covers search, sound details, and previews (docs/design.md section 6, Sound library).

Every failure to use Freesound is FreesoundUnavailable with a `reason` the API passes on with
HTTP 503: `no_api_key`, `bad_api_key`, or `unreachable` (spec story 35).
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

API = "https://freesound.org/apiv2"
KEY_SIGNUP = "https://freesound.org/apiv2/apply"
FIELDS = "id,name,username,license,url,duration,previews"
PAGE_SIZE = 15
# A preview is a few MB at most; anything far bigger isn't a preview.
MAX_DOWNLOAD = 50 * 1024 * 1024
TIMEOUT = 15

NO_API_KEY = "no_api_key"
BAD_API_KEY = "bad_api_key"
UNREACHABLE = "unreachable"


class FreesoundUnavailable(Exception):
    """Freesound can't be used right now. `reason` is one of the three reasons above."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


class FreesoundSoundMissing(Exception):
    def __init__(self, sound_id: int):
        super().__init__(f"Freesound has no sound {sound_id}")
        self.sound_id = sound_id


@dataclass(frozen=True)
class FreesoundSound:
    """One Freesound result: enough to preview it, judge its license, and credit it."""

    id: int
    title: str
    author: str
    license: str
    url: str  # the sound's page on Freesound
    duration: float
    preview_url: str  # high-quality preview, OGG if there is one, else MP3

    @property
    def attribution(self) -> str:
        return f'"{self.title}" by {self.author} ({self.url}), licensed under {self.license}'


@dataclass(frozen=True)
class SearchPage:
    results: list[FreesoundSound]
    count: int  # results across every page
    page: int
    has_next: bool


class Freesound(Protocol):
    def search(self, query: str, page: int = 1) -> SearchPage:
        """One page of results for `query`."""

    def sound(self, sound_id: int) -> FreesoundSound:
        """One sound by id. Raises FreesoundSoundMissing."""

    def download(self, sound: FreesoundSound) -> bytes:
        """The sound's audio, in whatever format Freesound serves (not WAV)."""


def license_name(value: str) -> str:
    """A license as people read it. Freesound gives a name ("Attribution"), or, in older
    replies, a Creative Commons URL, which is turned into the same kind of name."""
    value = (value or "").strip()
    found = re.search(r"creativecommons\.org/(?:licenses|publicdomain)/([a-z+-]+)/([\d.]+)", value)
    if not found:
        return value or "unknown license"
    kind, version = found.groups()
    names = {
        "zero": "Creative Commons 0",
        "by": f"Attribution {version}",
        "by-nc": f"Attribution NonCommercial {version}",
        "sampling+": f"Sampling+ {version}",
    }
    return names.get(kind, f"CC {kind.upper()} {version}")


def parse_sound(data: dict) -> FreesoundSound | None:
    """A FreesoundSound from Freesound's JSON, or None if it has no preview to play."""
    previews = data.get("previews") or {}
    preview = previews.get("preview-hq-ogg") or previews.get("preview-hq-mp3")
    if not preview or "id" not in data:
        return None
    return FreesoundSound(
        id=int(data["id"]),
        title=str(data.get("name") or f"Sound {data['id']}"),
        author=str(data.get("username") or "unknown"),
        license=license_name(str(data.get("license") or "")),
        url=str(data.get("url") or f"https://freesound.org/s/{data['id']}/"),
        duration=float(data.get("duration") or 0),
        preview_url=str(preview),
    )


class FreesoundClient:
    """The real client. `api_key` is asked for the key on each call, so a key added to the
    config file works without a restart; `key_hint` says where to put one."""

    def __init__(
        self,
        api_key: Callable[[], str],
        key_hint: str = "the config file's freesound_api_key",
        base_url: str = API,
        timeout: float = TIMEOUT,
    ):
        self._api_key = api_key
        self._key_hint = key_hint
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def search(self, query: str, page: int = 1) -> SearchPage:
        params = {"query": query, "page": page, "page_size": PAGE_SIZE, "fields": FIELDS}
        try:
            data = self._get_json("/search/", params)
        except _NotFound:
            # Freesound answers a page past the last one with 404.
            return SearchPage(results=[], count=0, page=page, has_next=False)
        try:
            results = [s for s in map(parse_sound, data.get("results") or []) if s is not None]
            return SearchPage(
                results=results,
                count=int(data.get("count") or 0),
                page=page,
                has_next=bool(data.get("next")),
            )
        except (TypeError, ValueError, AttributeError):
            raise self._odd_reply() from None

    def sound(self, sound_id: int) -> FreesoundSound:
        try:
            data = self._get_json(f"/sounds/{int(sound_id)}/", {"fields": FIELDS})
        except _NotFound:
            raise FreesoundSoundMissing(sound_id) from None
        try:
            sound = parse_sound(data)
        except (TypeError, ValueError, AttributeError):
            raise self._odd_reply() from None
        if sound is None:
            raise FreesoundSoundMissing(sound_id)
        return sound

    def download(self, sound: FreesoundSound) -> bytes:
        # Previews are public files: the API key isn't sent with them.
        try:
            with self._open(urllib.request.Request(sound.preview_url)) as response:
                audio = response.read(MAX_DOWNLOAD + 1)
        except _NotFound:
            raise FreesoundSoundMissing(sound.id) from None
        if len(audio) > MAX_DOWNLOAD:
            raise FreesoundUnavailable(
                UNREACHABLE, "Freesound sent a file far too big for a preview"
            )
        return audio

    # --- HTTP --------------------------------------------------------------------------------

    def _get_json(self, path: str, params: dict) -> dict:
        key = self._api_key().strip()
        if not key:
            raise FreesoundUnavailable(
                NO_API_KEY,
                f"Searching Freesound needs an API key. Get one at {KEY_SIGNUP}, then put it in "
                f"{self._key_hint}",
            )
        url = f"{self._base_url}{path}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"Authorization": f"Token {key}"})
        with self._open(request) as response:
            body = response.read()
        try:
            data = json.loads(body)
        except ValueError:
            raise self._odd_reply() from None
        if not isinstance(data, dict):
            raise self._odd_reply()
        return data

    def _open(self, request: urllib.request.Request):
        try:
            return urllib.request.urlopen(request, timeout=self._timeout)  # noqa: S310
        except urllib.error.HTTPError as error:
            error.close()
            if error.code in (401, 403):
                raise FreesoundUnavailable(
                    BAD_API_KEY,
                    f"Freesound refused the API key; check {self._key_hint}",
                ) from None
            if error.code == 404:
                raise _NotFound from None
            raise FreesoundUnavailable(
                UNREACHABLE,
                f"Freesound isn't answering properly right now (HTTP {error.code}); "
                "try again later. Everything else works offline",
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            why = getattr(error, "reason", None) or error
            raise FreesoundUnavailable(
                UNREACHABLE,
                f"Can't reach Freesound ({why}); check your internet connection. "
                "Everything else works offline",
            ) from None

    def _odd_reply(self) -> FreesoundUnavailable:
        return FreesoundUnavailable(UNREACHABLE, "Freesound sent a reply Voicewright can't read")


class _NotFound(Exception):
    """Freesound answered 404."""
