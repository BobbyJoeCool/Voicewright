"""The `voicewright` command: start the local server and open the page in the browser."""

import argparse
import enum
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
        default=default_config_path(),
        help="config file to use; created with default settings if missing (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=port_number,
        default=DEFAULT_PORT,
        help="local port to serve the page on (default: %(default)s)",
    )
    args = parser.parse_args()
    url = f"http://{HOST}:{args.port}/"

    holder = whats_on(url)
    if holder is PortHolder.VOICEWRIGHT:
        print(f"Voicewright is already running at {url}", flush=True)
        webbrowser.open(url)
        return
    if holder is PortHolder.OTHER_PROGRAM:
        sys.exit(
            f"voicewright: port {args.port} is in use by another program; pick another with --port"
        )

    try:
        app = create_app(args.config)
    except ConfigError as error:
        sys.exit(f"voicewright: {error}")
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=args.port))
    threading.Thread(target=open_when_started, args=(server, url), daemon=True).start()
    try:
        server.run()
    except KeyboardInterrupt:
        # uvicorn shuts down cleanly on Ctrl-C, then re-raises it; uvicorn.run() hides it too.
        pass


def port_number(text: str) -> int:
    if not (text.isascii() and text.isdigit()) or not 1 <= int(text) <= 65535:
        raise argparse.ArgumentTypeError(f"{text} is not a port from 1 to 65535")
    return int(text)


def whats_on(url: str) -> PortHolder:
    """What answers at this local address."""
    # No proxies: the probe only ever talks to this machine.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=2) as response:
            is_voicewright = b"<title>Voicewright</title>" in response.read()
            return PortHolder.VOICEWRIGHT if is_voicewright else PortHolder.OTHER_PROGRAM
    except urllib.error.URLError as error:
        # Refused means nothing listens. Any other failure to connect, or an HTTP error, means
        # a program holds the port, including one listening on every address.
        refused = isinstance(error.reason, ConnectionRefusedError)
        return PortHolder.NOTHING if refused else PortHolder.OTHER_PROGRAM
    except OSError:
        # A program accepted the connection but never answered in time, or dropped it.
        return PortHolder.OTHER_PROGRAM


def open_when_started(server: uvicorn.Server, url: str) -> None:
    # A daemon thread: if the server never starts, it ends with the process.
    while not server.started:
        time.sleep(0.1)
    print(f"Voicewright is running at {url}", flush=True)
    webbrowser.open(url)


if __name__ == "__main__":
    main()
