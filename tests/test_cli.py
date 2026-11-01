import json
import os
import queue
import signal
import socket
import subprocess
import sys
import threading

import pytest


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
def run_voicewright(tmp_path):
    """Start the `voicewright` command with a temp HOME and a browser that does nothing."""
    env = {**os.environ, "HOME": str(tmp_path / "home"), "BROWSER": "true"}

    started = []

    def start(*args):
        app = subprocess.Popen(
            [sys.executable, "-m", "voicewright.cli", *args],
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


def test_ctrl_c_stops_the_app_without_a_traceback(run_voicewright):
    app = run_voicewright("--port", str(free_port()))
    assert "Voicewright is running at" in first_stdout_line(app)

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
