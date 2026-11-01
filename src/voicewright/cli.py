"""The `voicewright` command: start the local server and open the page in the browser."""

import argparse
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from voicewright.app import create_app
from voicewright.config import default_config_path

HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def main() -> None:
    parser = argparse.ArgumentParser(prog="voicewright", description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="config file to use; created with default settings if missing (default: %(default)s)",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="(default: %(default)s)")
    args = parser.parse_args()

    server = uvicorn.Server(uvicorn.Config(create_app(args.config), host=HOST, port=args.port))
    url = f"http://{HOST}:{args.port}/"
    threading.Thread(target=open_when_started, args=(server, url), daemon=True).start()
    server.run()


def open_when_started(server: uvicorn.Server, url: str) -> None:
    while not server.started:
        if server.should_exit:
            return
        time.sleep(0.1)
    print(f"Voicewright is running at {url}")
    webbrowser.open(url)


if __name__ == "__main__":
    main()
