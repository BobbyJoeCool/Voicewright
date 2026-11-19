"""Browser end-to-end tests: the real page, driven by Playwright, against the app on fakes.

Each test gets its own app: a uvicorn server on a free local port, a fresh temp data folder,
the fake engines, and the fake Freesound. Nothing loads a real model, and the browser may not
reach anything but that server; Freesound preview clips are served from the test fixtures.

Run with `pytest tests/e2e` (a plain `pytest` leaves them out; see tests/conftest.py).
"""

import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
import uvicorn
from fakes import FIXTURES, FakeEngines, FakeFreesound
from playwright.sync_api import Page, Route, expect

from voicewright.app import create_app

# The fake engines finish in milliseconds, but the page polls a job every 700 ms.
expect.set_options(timeout=10_000)


def pytest_collection_modifyitems(items):
    here = Path(__file__).parent
    for item in items:
        if here in Path(item.fspath).parents:
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    # Let a test start a player without a click on it (the page itself plays new takes too).
    return {**browser_type_launch_args, "args": ["--autoplay-policy=no-user-gesture-required"]}


@dataclass
class LiveApp:
    """A running app: where it is, and the fakes behind it."""

    url: str
    fakes: FakeEngines
    freesound: FakeFreesound
    data_folder: Path
    config_path: Path


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def live_app(write_config, data_folder, config_path, fakes, freesound):
    """The app served over HTTP, on fakes and a fresh data folder. Stopped after the test."""
    app = create_app(write_config(), fakes.engines(), freesound=freesound)
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            pytest.fail("the app didn't start")
        time.sleep(0.02)
    try:
        yield LiveApp(f"http://127.0.0.1:{port}", fakes, freesound, data_folder, config_path)
    finally:
        # Let a held job finish, so the server can stop.
        fakes.before_call = None
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def page_errors():
    return []


@pytest.fixture
def vw(page: Page, live_app: LiveApp, page_errors) -> Page:
    """The page, open on a fresh app. Fails the test if the page throws a JavaScript error."""

    def only_local(route: Route) -> None:
        url = route.request.url
        if url.startswith(live_app.url):
            route.continue_()
        elif url.startswith("https://cdn.freesound.org/previews/"):
            route.fulfill(path=FIXTURES / "tone.ogg", content_type="audio/ogg")
        else:
            route.abort()

    page.route("**/*", only_local)
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.goto(live_app.url)
    yield page
    assert page_errors == [], f"the page threw: {page_errors}"
