"""The real Freesound client, against a stand-in server on localhost: never the internet."""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import run_app
from fakes import FIXTURES, FakeEngines
from fastapi.testclient import TestClient

from voicewright.app import create_app
from voicewright.config import FREESOUND_KEY_ENV, freesound_api_key
from voicewright.freesound import (
    BAD_API_KEY,
    FIELDS,
    NO_API_KEY,
    PAGE_SIZE,
    UNREACHABLE,
    FreesoundClient,
    FreesoundSoundMissing,
    FreesoundUnavailable,
    license_name,
)

OGG = (FIXTURES / "tone.ogg").read_bytes()


def sound_json(sound_id: int, base: str, **overrides) -> dict:
    data = {
        "id": sound_id,
        "name": f"Sound {sound_id}",
        "username": "maker",
        "license": "Creative Commons 0",
        "url": f"https://freesound.org/people/maker/sounds/{sound_id}/",
        "duration": 1.25,
        "previews": {
            "preview-hq-ogg": f"{base}/previews/{sound_id}.ogg",
            "preview-hq-mp3": f"{base}/previews/{sound_id}.mp3",
        },
    }
    data.update(overrides)
    return data


class StandIn:
    """A tiny Freesound on localhost. `routes` maps a path to (status, body); every request
    is kept, with its query and headers."""

    def __init__(self):
        self.routes: dict[str, tuple[int, bytes]] = {}
        self.requests: list[dict] = []
        stand_in = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                url = urlparse(self.path)
                stand_in.requests.append(
                    {"path": url.path, "query": parse_qs(url.query), "headers": dict(self.headers)}
                )
                status, body = stand_in.routes.get(url.path, (404, b'{"detail": "Not found."}'))
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def reply(self, path: str, data, status: int = 200) -> None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.routes[path] = (status, body)

    def client(self, key: str = "secret-key") -> FreesoundClient:
        return FreesoundClient(lambda: key, key_hint="the test config", base_url=self.base)


@pytest.fixture
def stand_in():
    server = StandIn()
    yield server
    server.server.shutdown()
    server.server.server_close()


def closed_port_url() -> str:
    """A localhost URL nothing listens on: as unreachable as Freesound with no network."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


# --- Search ----------------------------------------------------------------------------------


def test_search_sends_the_key_and_asks_for_what_the_page_shows(stand_in):
    stand_in.reply("/search/", {"count": 0, "next": None, "results": []})

    stand_in.client().search("door slam", page=3)

    [request] = stand_in.requests
    assert request["headers"]["Authorization"] == "Token secret-key"
    assert request["query"] == {
        "query": ["door slam"],
        "page": ["3"],
        "page_size": [str(PAGE_SIZE)],
        "fields": [FIELDS],
    }


def test_search_results_are_parsed_with_the_ogg_preview_preferred(stand_in):
    base = stand_in.base
    stand_in.reply(
        "/search/",
        {
            "count": 40,
            "next": f"{base}/search/?page=2",
            "results": [
                sound_json(1, base),
                sound_json(2, base, previews={"preview-hq-mp3": f"{base}/previews/2.mp3"}),
                sound_json(3, base, previews={}),  # nothing to preview: left out
                sound_json(4, base, license="http://creativecommons.org/licenses/by/3.0/"),
            ],
        },
    )

    page = stand_in.client().search("boom")

    assert (page.count, page.page, page.has_next) == (40, 1, True)
    assert [s.id for s in page.results] == [1, 2, 4]
    first = page.results[0]
    assert (first.title, first.author, first.duration) == ("Sound 1", "maker", 1.25)
    assert first.preview_url.endswith("/previews/1.ogg")
    assert page.results[1].preview_url.endswith("/previews/2.mp3")
    assert page.results[2].license == "Attribution 3.0"


def test_a_page_past_the_last_is_empty(stand_in):
    page = stand_in.client().search("boom", page=99)  # the stand-in answers 404

    assert (page.results, page.has_next) == ([], False)


# --- The three reasons -----------------------------------------------------------------------


def test_no_key_is_no_api_key_and_nothing_is_sent(stand_in):
    with pytest.raises(FreesoundUnavailable) as raised:
        stand_in.client(key="  ").search("boom")

    assert raised.value.reason == NO_API_KEY
    assert "freesound.org/apiv2/apply" in str(raised.value)
    assert "the test config" in str(raised.value)
    assert stand_in.requests == []


def test_a_refused_key_is_bad_api_key(stand_in):
    stand_in.reply("/search/", {"detail": "Invalid token."}, status=401)

    with pytest.raises(FreesoundUnavailable) as raised:
        stand_in.client().search("boom")

    assert raised.value.reason == BAD_API_KEY


@pytest.mark.parametrize(
    "status, body", [(500, b"oops"), (503, b"down"), (429, b"slow down"), (200, b"<html>")]
)
def test_a_broken_reply_is_unreachable(stand_in, status, body):
    stand_in.reply("/search/", body, status=status)

    with pytest.raises(FreesoundUnavailable) as raised:
        stand_in.client().search("boom")

    assert raised.value.reason == UNREACHABLE


def test_no_server_is_unreachable():
    client = FreesoundClient(lambda: "secret-key", base_url=closed_port_url(), timeout=2)

    with pytest.raises(FreesoundUnavailable) as raised:
        client.search("boom")

    assert raised.value.reason == UNREACHABLE
    assert "Can't reach Freesound" in str(raised.value)


# --- Through the app: both 503 reasons on the real client --------------------------------


def test_the_app_says_no_api_key_when_the_config_has_none(write_config, monkeypatch):
    monkeypatch.delenv(FREESOUND_KEY_ENV, raising=False)
    config = write_config(freesound_api_key="")

    # The app's own client, built from the config: no fake, and no key, so no network.
    with TestClient(create_app(config, FakeEngines().engines())) as client:
        response = client.get("/sounds/search", params={"q": "boom"})

    assert response.status_code == 503
    assert response.json()["reason"] == NO_API_KEY
    assert str(config) in response.json()["detail"], "says which file to put the key in"


def test_the_app_says_unreachable_when_freesound_cant_be_reached(write_config):
    client = FreesoundClient(lambda: "secret-key", base_url=closed_port_url(), timeout=2)

    with run_app(write_config(), freesound=client) as app:
        responses = [
            app.get("/sounds/search", params={"q": "boom"}),
            app.post("/sounds", json={"freesound_id": 1, "name": "boom"}),
        ]

    for response in responses:
        assert response.status_code == 503
        assert response.json()["reason"] == UNREACHABLE


def test_a_key_added_to_the_config_works_without_a_restart(write_config, monkeypatch, stand_in):
    monkeypatch.delenv(FREESOUND_KEY_ENV, raising=False)
    config = write_config(freesound_api_key="")
    client = FreesoundClient(lambda: freesound_api_key(config), base_url=stand_in.base)
    stand_in.reply("/search/", {"count": 0, "next": None, "results": []})
    with run_app(config, freesound=client) as app:
        assert app.get("/sounds/search", params={"q": "boom"}).status_code == 503
        write_config(freesound_api_key="added-later")
        assert app.get("/sounds/search", params={"q": "boom"}).status_code == 200

    assert stand_in.requests[-1]["headers"]["Authorization"] == "Token added-later"


def test_the_environment_key_wins_over_the_config(write_config, monkeypatch):
    config = write_config(freesound_api_key="from-config")
    assert freesound_api_key(config) == "from-config"
    monkeypatch.setenv(FREESOUND_KEY_ENV, " from-env ")
    assert freesound_api_key(config) == "from-env"


# --- One sound, and its download -------------------------------------------------------------


def test_adding_through_the_real_client_converts_the_preview(write_config, stand_in):
    stand_in.reply("/sounds/7/", sound_json(7, stand_in.base, name="Door Slam"))
    stand_in.reply("/previews/7.ogg", OGG)

    with run_app(write_config(), freesound=stand_in.client()) as app:
        response = app.post("/sounds", json={"freesound_id": 7, "name": "door-slam"})

    assert response.status_code == 201, response.text
    assert response.json()["credit"]["title"] == "Door Slam"
    preview_request = stand_in.requests[-1]
    assert preview_request["path"] == "/previews/7.ogg"
    assert "Authorization" not in preview_request["headers"], "the key stays with the API"


def test_a_sound_freesound_doesnt_have_is_missing(stand_in):
    with pytest.raises(FreesoundSoundMissing):
        stand_in.client().sound(404404)


def test_a_preview_that_is_gone_is_missing(stand_in):
    stand_in.reply("/sounds/8/", sound_json(8, stand_in.base))
    client = stand_in.client()

    with pytest.raises(FreesoundSoundMissing):
        client.download(client.sound(8))


@pytest.mark.parametrize(
    "value, name",
    [
        ("Creative Commons 0", "Creative Commons 0"),
        ("Attribution", "Attribution"),
        ("Attribution NonCommercial", "Attribution NonCommercial"),
        ("http://creativecommons.org/publicdomain/zero/1.0/", "Creative Commons 0"),
        ("https://creativecommons.org/licenses/by/4.0/", "Attribution 4.0"),
        ("http://creativecommons.org/licenses/by-nc/3.0/", "Attribution NonCommercial 3.0"),
        ("http://creativecommons.org/licenses/sampling+/1.0/", "Sampling+ 1.0"),
        ("", "unknown license"),
    ],
)
def test_licenses_read_as_names(value, name):
    assert license_name(value) == name
