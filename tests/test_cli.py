import json
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

    deadline = time.monotonic() + 10
    while not browser_log.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert browser_log.exists(), "the browser was never opened"
    assert browser_log.read_text().split() == [f"http://127.0.0.1:{port}/"]


def test_ctrl_c_stops_the_app_without_a_traceback(run_voicewright):
    app, _ = start_running(run_voicewright)

    app.send_signal(signal.SIGINT)
    _, stderr = app.communicate(timeout=10)

    assert "Traceback" not in stderr
    assert app.returncode == 0


def assert_fails_with_a_plain_message(app, *expected_in_message, exit_code=1):
    try:
        _, stderr = app.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        app.kill()
        _, stderr = app.communicate()
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
def test_a_bad_config_is_reported_by_file_name(run_voicewright, tmp_path, config_text):
    config_path = tmp_path / "config.toml"
    if isinstance(config_text, bytes):
        config_path.write_bytes(config_text)
    else:
        config_path.write_text(config_text)

    app = run_voicewright("--config", str(config_path), "--port", str(free_port()))

    assert_fails_with_a_plain_message(app, str(config_path))


def test_a_data_folder_that_cannot_be_created_is_reported(run_voicewright, tmp_path):
    taken = tmp_path / "taken"
    taken.write_text("a file, not a folder")
    config_path = tmp_path / "config.toml"
    config_path.write_text(f"data_folder = {json.dumps(str(taken))}\n")

    app = run_voicewright("--config", str(config_path), "--port", str(free_port()))

    assert_fails_with_a_plain_message(app, str(taken), str(config_path))


def test_a_config_path_that_cannot_be_used_is_reported(run_voicewright, tmp_path):
    folder = tmp_path / "a-folder"
    folder.mkdir()

    app = run_voicewright("--config", str(folder), "--port", str(free_port()))

    assert_fails_with_a_plain_message(app, str(folder))


@pytest.mark.parametrize("port", ["0", "70000", "abc"])
def test_a_port_outside_1_to_65535_is_a_usage_error(run_voicewright, port):
    app = run_voicewright("--port", port)

    assert_fails_with_a_plain_message(app, f"{port} is not a port from 1 to 65535", exit_code=2)


def test_a_second_launch_opens_the_running_app(run_voicewright, browser_log):
    _, port = start_running(run_voicewright)

    second = run_voicewright("--port", str(port))
    try:
        stdout, _ = second.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        second.kill()
        stdout, _ = second.communicate()

    assert second.returncode == 0
    assert "Voicewright is already running at" in stdout
    assert browser_log.read_text().split() == [f"http://127.0.0.1:{port}/"] * 2


def test_a_port_taken_by_another_program_is_reported(run_voicewright):
    with socket.socket() as other_program:
        other_program.bind(("127.0.0.1", 0))
        other_program.listen()
        port = other_program.getsockname()[1]

        app = run_voicewright("--port", str(port))

        assert_fails_with_a_plain_message(app, f"port {port} is in use", "--port")
