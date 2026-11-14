"""The Output cache: keeps the last N Outputs (a setting from 5 to 10), cleared on startup."""

import pytest
from conftest import run_app
from fakes import FakeEngines
from scripts import generated_output, saved_voice

from voicewright.app import create_app
from voicewright.config import ConfigError, load_config


def make_outputs(client, voice: dict, count: int) -> list[dict]:
    return [generated_output(client, voice, f"Take {n}.") for n in range(count)]


def listed(client) -> list[str]:
    return [output["id"] for output in client.get("/outputs").json()]


def test_the_cache_keeps_the_newest_five_by_default(client):
    voice = saved_voice(client)

    made = make_outputs(client, voice, 6)

    assert client.get("/settings").json() == {"output_cache_size": 5, "output_cache_range": [5, 10]}
    assert listed(client) == [output["id"] for output in reversed(made[1:])]
    oldest = made[0]
    assert client.get(oldest["audio_url"]).status_code == 404
    assert client.get(f"/outputs/{oldest['id']}").status_code == 404


def test_a_bigger_cache_keeps_more_and_is_saved_in_the_config(client, config_path):
    voice = saved_voice(client)

    response = client.put("/settings", json={"output_cache_size": 7})

    assert response.status_code == 200
    assert response.json()["output_cache_size"] == 7
    assert load_config(config_path).output_cache_size == 7
    make_outputs(client, voice, 8)
    assert len(listed(client)) == 7


def test_a_smaller_cache_removes_the_oldest_at_once(client):
    voice = saved_voice(client)
    client.put("/settings", json={"output_cache_size": 8})
    made = make_outputs(client, voice, 7)

    client.put("/settings", json={"output_cache_size": 5})

    assert listed(client) == [output["id"] for output in reversed(made[2:])]


@pytest.mark.parametrize("size", [4, 11, 0, -5, 7.5, "7", True, None])
def test_a_size_outside_5_to_10_is_refused(client, config_path, size):
    before = config_path.read_text()

    response = client.put("/settings", json={"output_cache_size": size})

    assert response.status_code == 422
    assert config_path.read_text() == before
    assert client.get("/settings").json()["output_cache_size"] == 5


def test_changing_the_setting_keeps_the_rest_of_the_config(write_config, config_path):
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data_folder = config_path.parent.parent / "data"
    config_path.write_text(
        "# my settings\n"
        f'data_folder = "{data_folder}"\n'
        "output_cache_size = 5  # how many to keep\n"
        'freesound_api_key = "abc123"\n'
    )

    with run_app(config_path) as client:
        assert client.put("/settings", json={"output_cache_size": 9}).status_code == 200

    assert config_path.read_text() == (
        "# my settings\n"
        f'data_folder = "{data_folder}"\n'
        "output_cache_size = 9  # how many to keep\n"
        'freesound_api_key = "abc123"\n'
    )
    assert config_path.stat().st_mode & 0o777 == 0o600, "it holds the API key"


def test_a_config_without_the_setting_uses_five_and_gains_it_when_changed(config_path):
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'data_folder = "{config_path.parent.parent / "data"}"\n')

    with run_app(config_path) as client:
        assert client.get("/settings").json()["output_cache_size"] == 5
        client.put("/settings", json={"output_cache_size": 6})

    assert load_config(config_path).output_cache_size == 6


def test_the_setting_survives_a_restart(write_config):
    config = write_config()
    with run_app(config) as client:
        client.put("/settings", json={"output_cache_size": 10})

    with run_app(config) as client:
        assert client.get("/settings").json()["output_cache_size"] == 10


@pytest.mark.parametrize("value", [4, 11, '"5"', "true", "5.0"])
def test_a_config_with_a_bad_cache_size_says_how_to_fix_it(write_config, value, config_path):
    config = write_config()
    config.write_text(
        config.read_text().replace("output_cache_size = 5", f"output_cache_size = {value}")
    )

    with pytest.raises(ConfigError) as raised:
        create_app(config, FakeEngines().engines())

    assert "output_cache_size to be a whole number from 5 to 10" in str(raised.value)


def test_the_cache_is_cleared_when_the_app_starts(write_config, data_folder):
    config = write_config()
    fakes = FakeEngines()
    with run_app(config, fakes) as client:
        voice = saved_voice(client)
        output = generated_output(client, voice, "Remember me?")
    leftover = data_folder / "cache" / ".half-written"
    leftover.mkdir()

    with run_app(config, fakes) as client:
        assert client.get("/outputs").json() == []
        assert client.get(output["audio_url"]).status_code == 404
        assert [v["id"] for v in client.get("/voices").json()] == [voice["id"]], "Voices stay"

    assert list((data_folder / "cache").iterdir()) == []
