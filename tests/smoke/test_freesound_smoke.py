"""Smoke test of the real Freesound API. Needs the internet and your API key; run by hand:

    .venv/bin/pytest -m smoke -s tests/smoke/test_freesound_smoke.py

The key comes from FREESOUND_API_KEY, or else your default config file's freesound_api_key.
Skipped when there's no key. Adds one sound to a temporary library, never your real one.
"""

import io
import os
import wave

import pytest
from conftest import run_app

from voicewright.config import FREESOUND_KEY_ENV, default_config_path, freesound_api_key
from voicewright.freesound import FreesoundClient

pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def key():
    # Reading a missing config file would write a default one: only read one that's there.
    config = default_config_path()
    found = freesound_api_key(config) if config.exists() else os.environ.get(FREESOUND_KEY_ENV, "")
    found = found.strip()
    if not found:
        pytest.skip("no Freesound API key in FREESOUND_API_KEY or the default config file")
    return found


def test_search_and_add_a_real_sound(key, write_config, tmp_path):
    client = FreesoundClient(lambda: key)
    page = client.search("thunder")
    assert page.results, "Freesound found no thunder at all"
    pick = min(page.results, key=lambda s: s.duration)
    print(f"\nPicked {pick.attribution}, {pick.duration:.1f}s")

    with run_app(write_config(), freesound=client) as app:
        response = app.post("/sounds", json={"freesound_id": pick.id, "name": "thunder"})
        assert response.status_code == 201, response.text
        audio = app.get(response.json()["audio_url"]).content

    with wave.open(io.BytesIO(audio)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth()) == (1, 2)
    saved = tmp_path / "freesound-thunder.wav"
    saved.write_bytes(audio)
    print(f"Saved {saved}; listen to check it")
