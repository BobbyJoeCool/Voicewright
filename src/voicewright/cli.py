"""The `voicewright` command: start the local server and open the page in the browser."""

import argparse
import enum
import http.client
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from voicewright.app import create_app
from voicewright.config import ConfigError, default_config_path

HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class PortHolder(enum.Enum):
    """What already answers on the port the app wants."""

    NOTHING = enum.auto()
    VOICEWRIGHT = enum.auto()
    OTHER_PROGRAM = enum.auto()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="voicewright", description="Start Voicewright and open it in your browser."
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="config file to use; created with default settings if missing "
        f"(default: {default_config_path()})",
    )
    parser.add_argument(
        "--port",
        type=port_number,
        default=DEFAULT_PORT,
        help="local port to serve the page on (default: %(default)s)",
    )
    args = parser.parse_args()
    url = f"http://{HOST}:{args.port}/"
    config_path = args.config or default_config_path()

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
        webbrowser.open(url)
        return
    if holder is PortHolder.OTHER_PROGRAM:
        sys.exit(
            f"voicewright: port {args.port} is in use by another program; pick another with --port"
        )

    try:
        app = create_app(config_path)
    except ConfigError as error:
        sys.exit(f"voicewright: {error}")
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=args.port))
    threading.Thread(target=open_when_started, args=(server, url), daemon=True).start()
    try:
        server.run()
    except KeyboardInterrupt:
        # uvicorn shuts down cleanly on Ctrl-C, then re-raises it; uvicorn.run() hides it too.
        pass


def is_default_config(path: Path) -> bool:
    """Whether this is the config a plain `voicewright` uses, however the path is written."""
    return path.expanduser().resolve() == default_config_path().resolve()


def port_number(text: str) -> int:
    if not (text.isascii() and text.isdigit()) or not 1 <= int(text) <= 65535:
        raise argparse.ArgumentTypeError(f"{text} is not a port from 1 to 65535")
    return int(text)


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def whats_on(url: str) -> PortHolder:
    """What answers at this local address."""
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
    return b"<title>Voicewright</title>" in start


def open_when_started(server: uvicorn.Server, url: str) -> None:
    # A daemon thread: if the server never starts, it ends with the process.
    while not server.started:
        time.sleep(0.1)
    print(f"Voicewright is running at {url}", flush=True)
    webbrowser.open(url)


if __name__ == "__main__":
    main()
