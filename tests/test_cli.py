import contextlib
import http.server
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

# The installed console script, so a broken [project.scripts] entry fails these tests.
VOICEWRIGHT = Path(sys.executable).parent / "voicewright"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def first_stdout_line(app: subprocess.Popen, timeout: float = 10) -> str:
    """The first line the app prints, or "" if it prints nothing in time."""
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: lines.put(app.stdout.readline()), daemon=True).start()
    try:
        return lines.get(timeout=timeout)
    except queue.Empty:
        return ""


@pytest.fixture
def browser_log(tmp_path):
    """Where the stand-in browser records each URL it is asked to open."""
    return tmp_path / "browser.log"


@pytest.fixture
def run_voicewright(tmp_path, browser_log):
    """Start the `voicewright` command with a temp HOME and a stand-in browser."""
    browser = tmp_path / "browser.sh"
    browser.write_text(f'#!/bin/sh\necho "$1" >> "{browser_log}"\n')
    browser.chmod(0o755)
    env = {**os.environ, "HOME": str(tmp_path / "home"), "BROWSER": str(browser)}

    started = []

    def start(*args):
        app = subprocess.Popen(
            [str(VOICEWRIGHT), *args],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # A terminal delivers Ctrl-C even when the shell running pytest ignores SIGINT.
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL),
        )
        started.append(app)
        return app

    yield start
    for app in started:
        if app.poll() is None:
            app.kill()
            app.communicate()


@pytest.fixture
def launch_with_config(run_voicewright):
    """Start the app with this config file on a free port."""
    return lambda config_path: run_voicewright(
        "--config", str(config_path), "--port", str(free_port())
    )


@pytest.fixture
def launch_with_data_folder(launch_with_config, write_config):
    """Start the app with a config whose data_folder is this path."""
    return lambda data_folder: launch_with_config(write_config(data_folder=str(data_folder)))


def finish(app: subprocess.Popen) -> tuple[str, str]:
    """Wait for the app to exit, killing it if it is still running after 10 seconds."""
    try:
        return app.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        app.kill()
        return app.communicate()


def wait_for_opens(browser_log, count: int) -> list[str]:
    """The URLs the browser was asked to open, once there are `count` of them (or 10s pass)."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        opened = browser_log.read_text().split() if browser_log.exists() else []
        if len(opened) >= count:
            return opened
        time.sleep(0.1)
    return opened


@contextlib.contextmanager
def serving(handler: type[http.server.BaseHTTPRequestHandler]):
    """Serve this handler on a free local port, quietly; yield the port, then shut it down."""

    class Quiet(handler):
        def log_message(self, *args):
            pass

    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()


def start_running(run_voicewright, *args):
    """Start the app on a free port; retry if another process takes the port first."""
    for _ in range(3):
        port = free_port()
        app = run_voicewright(*args, "--port", str(port))
        if "Voicewright is running at" in first_stdout_line(app):
            return app, port
        app.kill()
        app.communicate()
    pytest.fail("the app never started")


def test_the_command_opens_the_page_in_the_browser(run_voicewright, browser_log):
    _, port = start_running(run_voicewright)

    assert wait_for_opens(browser_log, 1) == [f"http://127.0.0.1:{port}/"]


def test_ctrl_c_stops_the_app_without_a_traceback(run_voicewright):
    app, _ = start_running(run_voicewright)

    app.send_signal(signal.SIGINT)
    _, stderr = app.communicate(timeout=10)

    assert "Traceback" not in stderr
    assert app.returncode == 0


def assert_fails_with_a_plain_message(app, *expected_in_message, exit_code=1):
    _, stderr = finish(app)
    assert app.returncode == exit_code, "the app should refuse to start"
    assert "Traceback" not in stderr
    for text in expected_in_message:
        assert text in stderr


@pytest.mark.parametrize(
    "config_text",
    [
        pytest.param("data_folder = /no/quotes\n", id="malformed-toml"),
        pytest.param("output_cache_size = 5\n", id="no-data-folder"),
        pytest.param("data_folder = 5\n", id="data-folder-not-text"),
        pytest.param('data_folder = "relative/data"\n', id="relative-data-folder"),
        pytest.param('data_folder = ""\n', id="empty-data-folder"),
        pytest.param('data_folder = "~nosuchuser/x"\n', id="unknown-user-home"),
        pytest.param('data_folder = "/Users/Zoë"\n'.encode("latin-1"), id="not-utf-8"),
        pytest.param('data_folder = "/tmp/a\\u0000b"\n', id="null-character"),
    ],
)
def test_a_bad_config_is_reported_by_file_name(launch_with_config, tmp_path, config_text):
    config_path = tmp_path / "config.toml"
    if isinstance(config_text, bytes):
        config_path.write_bytes(config_text)
    else:
        config_path.write_text(config_text)

    app = launch_with_config(config_path)

    assert_fails_with_a_plain_message(app, str(config_path))


def test_a_data_folder_that_cannot_be_created_is_reported(
    launch_with_data_folder, config_path, tmp_path
):
    taken = tmp_path / "taken"
    taken.write_text("a file, not a folder")

    app = launch_with_data_folder(taken)

    assert_fails_with_a_plain_message(app, str(taken), str(config_path))


def test_a_config_path_that_cannot_be_used_is_reported(launch_with_config, tmp_path):
    folder = tmp_path / "a-folder"
    folder.mkdir()

    app = launch_with_config(folder)

    assert_fails_with_a_plain_message(app, str(folder))


@pytest.mark.parametrize("port", ["0", "70000", "abc", "²", "１２３４"])
def test_a_port_outside_1_to_65535_is_a_usage_error(run_voicewright, port):
    app = run_voicewright("--port", port)

    assert_fails_with_a_plain_message(app, f"{port} is not a port from 1 to 65535", exit_code=2)


def test_a_second_launch_opens_the_running_app(run_voicewright, browser_log):
    _, port = start_running(run_voicewright)

    second = run_voicewright("--port", str(port))
    stdout, _ = finish(second)

    assert second.returncode == 0
    assert "Voicewright is already running at" in stdout
    assert wait_for_opens(browser_log, 2) == [f"http://127.0.0.1:{port}/"] * 2


@pytest.mark.parametrize("address", ["127.0.0.1", "0.0.0.0"])
def test_a_port_taken_by_another_program_is_reported(run_voicewright, address):
    with socket.socket() as other_program:
        other_program.bind((address, 0))
        other_program.listen()
        port = other_program.getsockname()[1]

        app = run_voicewright("--port", str(port))

        assert_fails_with_a_plain_message(app, f"port {port} is in use", "--port")


@pytest.mark.parametrize("below_the_link", ["", "Voicewright"])
def test_a_data_folder_linked_to_a_missing_target_is_reported(
    launch_with_data_folder, tmp_path, below_the_link
):
    link = tmp_path / "data-link"
    missing = tmp_path / "unmounted-drive" / "Voicewright"
    link.symlink_to(missing)
    data_folder = link / below_the_link if below_the_link else link

    app = launch_with_data_folder(data_folder)

    assert_fails_with_a_plain_message(app, str(link), f"links to {missing}", "doesn't exist")


@pytest.mark.parametrize(
    "status, page",
    [
        pytest.param(200, b"<title>Some other app</title>", id="another-page"),
        pytest.param(404, b"not found", id="http-error"),
    ],
)
def test_a_port_taken_by_another_web_server_is_reported(run_voicewright, status, page):
    class OtherWebServer(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.end_headers()
            self.wfile.write(page)

    with serving(OtherWebServer) as port:
        app = run_voicewright("--port", str(port))

        assert_fails_with_a_plain_message(app, f"port {port} is in use", "--port")


def test_a_data_folder_link_that_loops_is_reported(launch_with_data_folder, tmp_path):
    link = tmp_path / "data-link"
    link.symlink_to(link)
    app = launch_with_data_folder(link)

    assert_fails_with_a_plain_message(app, str(link), "doesn't exist")


def test_a_chain_of_links_names_the_final_missing_target(launch_with_data_folder, tmp_path):
    missing = tmp_path / "unmounted-drive" / "Voicewright"
    middle = tmp_path / "middle-link"
    middle.symlink_to(missing)
    link = tmp_path / "data-link"
    link.symlink_to(middle)
    app = launch_with_data_folder(link)

    assert_fails_with_a_plain_message(app, f"links to {missing}, which doesn't exist")


@pytest.fixture
def locked_folder(tmp_path):
    """A folder nobody can look inside, unlocked again so pytest can clean it up."""
    folder = tmp_path / "locked"
    folder.mkdir()
    folder.chmod(0o000)
    yield folder
    folder.chmod(0o700)


def test_a_data_folder_under_a_locked_folder_is_reported(launch_with_data_folder, locked_folder):
    data_folder = locked_folder / "Voicewright"

    app = launch_with_data_folder(data_folder)

    assert_fails_with_a_plain_message(app, str(data_folder), "Permission denied")


def test_a_port_taken_by_a_program_that_does_not_speak_http_is_reported(run_voicewright):
    with socket.socket() as other_program:
        other_program.bind(("127.0.0.1", 0))
        other_program.listen()
        port = other_program.getsockname()[1]

        def greet_like_ssh():
            connection, _ = other_program.accept()
            with connection:
                connection.sendall(b"SSH-2.0-OpenSSH_9.0\r\n")
                connection.recv(1024)

        threading.Thread(target=greet_like_ssh, daemon=True).start()

        app = run_voicewright("--port", str(port))

        assert_fails_with_a_plain_message(app, f"port {port} is in use", "--port")


def test_a_port_taken_by_a_server_that_never_stops_answering_is_reported(run_voicewright):
    class EndlessStream(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            try:
                while True:
                    self.wfile.write(b"data: tick\n\n" * 100)
                    self.wfile.flush()
                    time.sleep(0.2)
            except OSError:
                pass

    with serving(EndlessStream) as port:
        app = run_voicewright("--port", str(port))

        assert_fails_with_a_plain_message(app, f"port {port} is in use", "--port")


def test_a_port_that_redirects_to_a_running_voicewright_is_not_it(run_voicewright):
    _, voicewright_port = start_running(run_voicewright)

    class Redirect(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{voicewright_port}/")
            self.end_headers()

    with serving(Redirect) as port:
        app = run_voicewright("--port", str(port))

        assert_fails_with_a_plain_message(app, f"port {port} is in use", "--port")


def test_a_second_launch_with_its_own_config_does_not_open_the_running_app(
    run_voicewright, write_config, browser_log
):
    _, port = start_running(run_voicewright)

    second = run_voicewright("--config", str(write_config()), "--port", str(port))

    assert_fails_with_a_plain_message(second, "already running", "--port")
    assert wait_for_opens(browser_log, 1) == [f"http://127.0.0.1:{port}/"]
