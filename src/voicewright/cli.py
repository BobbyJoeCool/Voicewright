"""The `voicewright` command: start the local server and open the page in its own window."""

import argparse
import enum
import http.client
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from voicewright.app import create_app, page_title
from voicewright.config import ConfigError, default_config_path, expand_home
from voicewright.default_emotions import DefaultEmotionsError
from voicewright.engines import models_turned_off

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
# The longest the port check may take in all. Per-read timeouts alone don't bound it: a program
# that sends a byte every second never trips a two-second read timeout.
PROBE_SECONDS = 3
# Browsers that can open a page as an app window (--app): no tabs, no address bar. The first one
# installed is used. On the Mac they are app bundles; elsewhere, commands on the PATH.
APP_WINDOW_BROWSERS = ("Google Chrome", "Microsoft Edge", "Brave Browser", "Chromium")
APP_WINDOW_COMMANDS = (
    "google-chrome",
    "microsoft-edge",
    "brave-browser",
    "chromium",
    "chromium-browser",
)


class PortHolder(enum.Enum):
    """What already answers on the port the app wants."""

    NOTHING = enum.auto()
    VOICEWRIGHT = enum.auto()
    OTHER_PROGRAM = enum.auto()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="voicewright", description="Start Voicewright and open it in its own window."
    )
    parser.add_argument(
        "--config",
        help="config file to use; created with default settings if missing "
        f"(default: {default_config_path()})",
    )
    parser.add_argument(
        "--port",
        type=port_number,
        default=DEFAULT_PORT,
        help="local port to serve the page on (default: %(default)s)",
    )
    parser.add_argument(
        "--tab",
        action="store_true",
        help="open the page in a browser tab instead of its own app window",
    )
    args = parser.parse_args()
    url = f"http://{HOST}:{args.port}/"
    try:
        config_path = config_file(args.config)
    except RuntimeError:
        sys.exit(f"voicewright: can't find the home folder for --config {args.config}")

    try:
        holder = whats_on(url)
    except KeyboardInterrupt:
        # Ctrl-C while waiting on whatever holds the port: stop quietly, as a shell would.
        sys.exit(130)
    if holder is PortHolder.VOICEWRIGHT and not is_default_config(config_path):
        # The running app may use another config; opening it would quietly ignore this one.
        sys.exit(
            f"voicewright: Voicewright is already running at {url}, maybe with another config; "
            "stop it first, or pick another port with --port"
        )
    if holder is PortHolder.VOICEWRIGHT:
        print(f"Voicewright is already running at {url}", flush=True)
        open_page(url, tab=args.tab)
        return
    if holder is PortHolder.OTHER_PROGRAM:
        sys.exit(
            f"voicewright: port {args.port} is in use by another program; pick another with --port"
        )

    try:
        app = create_app(config_path)
    except (ConfigError, DefaultEmotionsError) as error:
        sys.exit(f"voicewright: {error}")
    if not models_turned_off():
        app.state.jobs.start("startup", load_speech_model(app.state.models))
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=args.port))
    threading.Thread(target=open_when_started, args=(server, url, args.tab), daemon=True).start()
    try:
        server.run()
    except KeyboardInterrupt:
        # uvicorn shuts down cleanly on Ctrl-C, then re-raises it; uvicorn.run() hides it too.
        pass


def load_speech_model(models):
    """The startup job: load the speech model once, so the first Script doesn't wait for it."""

    def work(report):
        report(0, None, "Loading the speech model")
        models.preload_speech()

    return work


def config_file(text: str | None) -> Path:
    """The config file `--config` names, with a leading ~ meaning a home folder."""
    if text is None:
        return default_config_path()
    if text.startswith("~"):
        return expand_home(text)
    try:
        # Absolute, so messages name the real file: "./~/x" would otherwise print as "~/x".
        return Path(text).absolute()
    except OSError:
        # The working folder is gone; keep the path as typed and let loading report it.
        return Path(text)


def is_default_config(path: Path) -> bool:
    """Whether this is the config a plain `voicewright` uses, however the path is written."""
    try:
        return path.resolve() == default_config_path().resolve()
    except (RuntimeError, OSError):
        # A link loop (RuntimeError), or a working folder that no longer exists: it can't be
        # the default, which resolves.
        return False


def port_number(text: str) -> int:
    if not (text.isascii() and text.isdigit()) or not 1 <= int(text) <= 65535:
        raise argparse.ArgumentTypeError(f"{text} is not a port from 1 to 65535")
    return int(text)


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def whats_on(url: str) -> PortHolder:
    """What answers at this local address, decided within PROBE_SECONDS.

    The check runs on a daemon thread, so one still stuck past the deadline ends with the
    process. A program that keeps the check waiting that long is not Voicewright.
    """
    answers: list[PortHolder] = []
    check = threading.Thread(target=lambda: answers.append(ask(url)), daemon=True)
    check.start()
    check.join(timeout=PROBE_SECONDS)
    return answers[0] if answers else PortHolder.OTHER_PROGRAM


def ask(url: str) -> PortHolder:
    """What answers at this local address, asked once over HTTP."""
    # No proxies and no redirects: the probe only ever talks to this address. A redirect then
    # surfaces as an HTTP error, which means another program holds the port.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirects())
    try:
        with opener.open(url, timeout=2) as response:
            return (
                PortHolder.VOICEWRIGHT
                if has_voicewright_title(response)
                else PortHolder.OTHER_PROGRAM
            )
    except urllib.error.URLError as error:
        # Refused means nothing listens. Any other failure to connect, or an HTTP error, means
        # a program holds the port, including one listening on every address.
        refused = isinstance(error.reason, ConnectionRefusedError)
        return PortHolder.NOTHING if refused else PortHolder.OTHER_PROGRAM
    except (OSError, http.client.HTTPException):
        # A program accepted the connection but never answered in time, dropped it, or
        # answered with something other than HTTP (an SSH or database banner).
        return PortHolder.OTHER_PROGRAM


def has_voicewright_title(response) -> bool:
    """Whether the page's opening bytes carry Voicewright's title.

    Reads for at most about two seconds: some servers stream forever, and the title is near the
    top of the page anyway.
    """
    deadline = time.monotonic() + 2
    start = b""
    while len(start) < 64 * 1024 and time.monotonic() < deadline:
        chunk = response.read1(4096)
        if not chunk:
            break
        start += chunk
    return page_title() in start


def open_when_started(server: uvicorn.Server, url: str, tab: bool = False) -> None:
    # A daemon thread: if the server never starts, it ends with the process.
    while not server.started:
        time.sleep(0.1)
    print(f"Voicewright is running at {url}", flush=True)
    open_page(url, tab=tab)


def open_page(url: str, *, tab: bool = False) -> None:
    """Open the page in its own app window when a browser that can is installed; otherwise, or
    with `tab`, in the usual browser. A BROWSER setting is the user's choice, so it wins."""
    command = None if tab or os.environ.get("BROWSER") else app_window_command(url)
    if command:
        try:
            subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return
        except OSError:
            pass  # The browser couldn't be started; a tab still works.
    webbrowser.open(url)


def app_window_command(
    url: str, platform: str = sys.platform, app_folders=None
) -> list[str] | None:
    """The command that opens `url` as an app window, or None if no such browser is found."""
    if platform == "darwin":
        folders = app_folders or (Path("/Applications"), Path.home() / "Applications")
        for name in APP_WINDOW_BROWSERS:
            for folder in folders:
                app = folder / f"{name}.app"
                if app.is_dir():
                    # -n hands the flag over even when the browser is already open.
                    return ["open", "-na", str(app), "--args", f"--app={url}"]
        return None
    for name in APP_WINDOW_COMMANDS:
        found = shutil.which(name)
        if found:
            return [found, f"--app={url}"]
    return None


if __name__ == "__main__":
    main()
