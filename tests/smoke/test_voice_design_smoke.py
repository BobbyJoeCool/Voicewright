"""Smoke test of designing a Draft voice with the real models on the M2. Slow, and run by hand:

    .venv/bin/pytest -m smoke -s

Needs the speech and voice-design extras. The speech model is loaded first, as at startup, so
this also checks the swap: Chatterbox out, Qwen in, then Chatterbox back.
"""

import io
import sys
import time
import wave

import pytest
from fastapi.testclient import TestClient

from voicewright.app import create_app
from voicewright.engines import NO_MODELS, default_engines

pytestmark = pytest.mark.smoke

DESCRIPTION = "A gravelly older man with a slow, calm, warm voice."


@pytest.fixture
def real_app(write_config):
    if sys.platform != "darwin":
        pytest.skip("the models run on Apple Silicon only")
    pytest.importorskip("chatterbox.tts_mlx", reason="needs pip install -e '.[speech]'")
    pytest.importorskip("mlx_audio.tts.utils", reason="needs pip install -e '.[voice-design]'")
    with pytest.MonkeyPatch.context() as env:
        env.delenv(NO_MODELS, raising=False)
        engines = default_engines()
    with TestClient(create_app(write_config(), engines)) as client:
        yield client


def seconds_of(clip: bytes) -> float:
    with wave.open(io.BytesIO(clip)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth()) == (1, 2), "standard WAV"
        return wav.getnframes() / wav.getframerate()


def test_a_draft_voice_is_designed_with_every_default_emotion(real_app, data_folder):
    models = real_app.app.state.models
    models.preload_speech()
    started = time.perf_counter()

    job_id = real_app.post("/voices/design", json={"description": DESCRIPTION}).json()["job_id"]
    while (status := real_app.get(f"/jobs/{job_id}").json())["state"] == "running":
        time.sleep(1)
    took = time.perf_counter() - started

    assert status["state"] == "succeeded", status["error"]
    draft = real_app.get(f"/voices/drafts/{status['result']['draft_id']}").json()
    print(
        f"\n  designed {len(draft['presets'])} clips in {took:.0f}s; listen in "
        f"{data_folder / 'drafts' / draft['id']}"
    )
    assert draft["missing"] == []
    for name, preset in draft["presets"].items():
        seconds = seconds_of(real_app.get(preset["clip_url"]).content)
        print(f"  {name}: {seconds:.1f}s")
        if name == "neutral":
            assert 6 < seconds < 30, "the neutral clip reads three sentences, about 15 s"
        else:
            assert 1.5 < seconds < 15
    assert models.loaded == "speech model", "the speech model is back for Scripts"
