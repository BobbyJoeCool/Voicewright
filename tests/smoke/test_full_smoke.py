"""The full v1 smoke test on the M2, with the real models (step 5.2). Slow, and run by hand:

    .venv/bin/pytest -m smoke -s tests/smoke/test_full_smoke.py

It designs a Voice, accepts it, renders a short tagged Script with an emotion change and a
sound, and saves the Output, all through the API. Only adding the sound uses the internet
(Freesound, with your API key; without one, a local tone stands in). Everything after that runs
offline: every connection that isn't to this machine is refused, and Hugging Face is told not
to look online, so a model that tried to download would fail the test. Turning Wi-Fi off as
well is the stricter check. macOS memory pressure is sampled the whole time and must never
reach critical (red).

Needs the speech and voice-design extras, and both models already downloaded. Uses a
temporary data folder, never your real one.
"""

import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from voicewright.app import create_app
from voicewright.audio_converter import convert
from voicewright.config import FREESOUND_KEY_ENV, default_config_path, freesound_api_key
from voicewright.engines import NO_MODELS, default_engines
from voicewright.sound_library import Credit, SoundLibrary

pytestmark = pytest.mark.smoke

FIXTURES = Path(__file__).parent.parent / "fixtures"
DESCRIPTION = "A gravelly older man with a slow, calm, warm voice."
SCRIPT = (
    "The storm had been building all afternoon. {thunder}\n"
    "[angry] I told you to bring the animals in before dark!\n"
    "[sad] Now half of them are out there in the rain."
)
# kern.memorystatus_vm_pressure_level: 1 normal (green), 2 warning (yellow), 4 critical (red).
PRESSURE = {1: "normal", 2: "warning", 4: "critical"}
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


class PressureWatch:
    """Samples macOS memory pressure once a second on a background thread."""

    def __init__(self):
        self.levels: list[int] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            out = subprocess.run(
                ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if out.isdigit():
                self.levels.append(int(out))
            self._stop.wait(1)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()

    @property
    def worst(self) -> int:
        return max(self.levels, default=1)


def refuse_the_internet(monkeypatch):
    """Refuse every connection that isn't to this machine, and keep Hugging Face offline."""
    connect = socket.socket.connect

    def local_only(sock, address):
        host = address[0] if isinstance(address, tuple) else address
        if sock.family in (socket.AF_INET, socket.AF_INET6) and host not in LOCAL_HOSTS:
            raise OSError(f"smoke test is offline: refused a connection to {address}")
        return connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", local_only)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")


def freesound_key() -> str:
    # Reading a missing config file would write a default one: only read one that's there.
    config = default_config_path()
    found = freesound_api_key(config) if config.exists() else os.environ.get(FREESOUND_KEY_ENV, "")
    return found.strip()


def wait_for(client: TestClient, job_id: str) -> dict:
    while (status := client.get(f"/jobs/{job_id}").json())["state"] == "running":
        time.sleep(1)
    assert status["state"] == "succeeded", status["error"]
    return status


def seconds_of(clip: bytes) -> float:
    with wave.open(io.BytesIO(clip)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth()) == (1, 2), "standard WAV"
        return wav.getnframes() / wav.getframerate()


def add_thunder(client: TestClient, key: str, data_folder: Path, tmp_path: Path) -> str:
    """Add a `thunder` sound: the shortest Freesound result, or a local tone without a key."""
    if key:
        results = client.get("/sounds/search", params={"q": "thunder"}).json()["results"]
        assert results, "Freesound found no thunder at all"
        pick = min(results, key=lambda s: s["duration"])
        response = client.post("/sounds", json={"freesound_id": pick["id"], "name": "thunder"})
        assert response.status_code == 201, response.text
        return f"Freesound {pick['id']}"
    wav = tmp_path / "tone.wav"
    convert(FIXTURES / "tone.flac", wav)
    credit = Credit("tone", "Voicewright tests", "CC0", "tests/fixtures/tone.flac", "Test tone")
    SoundLibrary(data_folder / "sounds").add("thunder", wav, credit)
    return "a local test tone (no Freesound key)"


@pytest.fixture
def real_app(write_config):
    if sys.platform != "darwin":
        pytest.skip("the models run on Apple Silicon only")
    pytest.importorskip("chatterbox.tts_mlx", reason="needs pip install -e '.[speech]'")
    pytest.importorskip("mlx_audio.tts.utils", reason="needs pip install -e '.[voice-design]'")
    key = freesound_key()
    with pytest.MonkeyPatch.context() as env:
        env.delenv(NO_MODELS, raising=False)
        engines = default_engines()
    with TestClient(create_app(write_config(freesound_api_key=key), engines)) as client:
        yield client, key


def test_design_render_and_save_offline(real_app, data_folder, tmp_path, monkeypatch):
    client, key = real_app
    started = time.perf_counter()

    # Online: the only step that needs the internet.
    source = add_thunder(client, key, data_folder, tmp_path)
    print(f"\n  added thunder from {source}")

    refuse_the_internet(monkeypatch)
    with PressureWatch() as pressure:
        models = client.app.state.models
        models.preload_speech()

        job = client.post("/voices/design", json={"description": DESCRIPTION}).json()["job_id"]
        draft_id = wait_for(client, job)["result"]["draft_id"]
        print(f"  designed a Draft voice at {time.perf_counter() - started:.0f}s")

        voice = client.post("/voices", json={"draft_id": draft_id, "name": "Smoke Narrator"})
        assert voice.status_code == 201, voice.text
        voice_id = voice.json()["id"]

        request = {"voice_id": voice_id, "script": SCRIPT}
        check = client.post("/scripts/check", json=request)
        assert check.status_code == 200, check.text
        job = client.post("/scripts/generate", json=request).json()["job_id"]
        output_id = wait_for(client, job)["result"]["output_id"]
        print(f"  rendered the Script at {time.perf_counter() - started:.0f}s")

        saved = client.post(f"/outputs/{output_id}/save")
        assert saved.status_code == 201, saved.text
        saved_id = saved.json()["id"]

    audio = client.get(f"/saved/{saved_id}/audio").content
    record = json.loads(client.get(f"/saved/{saved_id}/record").content)
    seconds = seconds_of(audio)
    listen = tmp_path / "smoke-output.wav"
    listen.write_bytes(audio)
    print(f"  saved a {seconds:.1f}s Output -> {listen}")
    print(
        f"  memory pressure: worst {PRESSURE.get(pressure.worst, pressure.worst)} over "
        f"{len(pressure.levels)} samples; total {time.perf_counter() - started:.0f}s"
    )

    # Three spoken lines and a sound, with gaps: well over a few seconds, nowhere near a minute.
    assert 6 < seconds < 60
    assert record["voice"]["name"] == "Smoke Narrator"
    assert record["script"] == SCRIPT
    assert {"neutral", "angry", "sad"} <= set(record["presets"])
    assert [s["name"] for s in record["sounds"]] == ["thunder"]
    assert pressure.levels, "memory pressure was never sampled"
    assert pressure.worst < 4, "memory pressure reached critical (red)"
