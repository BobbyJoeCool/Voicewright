"""Saving an Output: a copy in the saved folder with a sidecar record, kept for good."""

import json

import pytest
from conftest import run_app
from fakes import FakeEngines
from scripts import add_sound, generated_output, saved_voice


@pytest.fixture
def voice(client) -> dict:
    return saved_voice(client)


def save(client, output: dict):
    return client.post(f"/outputs/{output['id']}/save")


def test_the_sidecar_records_the_script_voice_values_and_credits(client, voice, data_folder):
    boom = add_sound(client, "boom", 101)
    rain = add_sound(client, "rain", 202)
    script = "Hello. [angry] Get out! {boom} (laugh) [sad] It's over. {rain} {boom}"
    output = generated_output(client, voice, script)

    response = save(client, output)

    assert response.status_code == 201, response.text
    saved = response.json()
    sidecar = json.loads((data_folder / "saved" / f"{saved['id']}.json").read_text())
    presets = voice["presets"]
    assert sidecar == {
        "saved": saved["saved"],
        "created": output["created"],
        "duration": output["duration"],
        "audio": f"{saved['id']}.wav",
        "output_id": output["id"],
        "script": script,
        "voice": {
            "id": voice["id"],
            "name": "Old Narrator",
            "description": voice["description"],
        },
        "presets": {
            emotion: {
                "exaggeration": presets[emotion]["exaggeration"],
                "cfg": presets[emotion]["cfg"],
            }
            for emotion in ("neutral", "angry", "sad")
        },
        "sounds": [{"name": "boom", **boom["credit"]}, {"name": "rain", **rain["credit"]}],
        "warnings": ["(laugh) is skipped: Vocal effects can't be rendered yet."],
        "segments": 6,
    }
    for credit in sidecar["sounds"]:
        assert {"name", "source", "author", "license"} <= credit.keys()
    assert client.get(saved["record_url"]).json() == sidecar


def test_a_saved_output_is_the_same_audio_and_named_for_its_voice(client, voice, data_folder):
    output = generated_output(client, voice, "Keep this one.")

    saved = save(client, output).json()

    assert "-old-narrator-" in saved["id"]
    audio = client.get(saved["audio_url"])
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/wav"
    assert audio.content == client.get(output["audio_url"]).content
    assert f'filename="{saved["id"]}.wav"' in audio.headers["content-disposition"]
    assert sorted(p.name for p in (data_folder / "saved").iterdir()) == [
        f"{saved['id']}.json",
        f"{saved['id']}.wav",
    ]


def test_the_credits_are_the_sounds_used_even_if_one_is_replaced_later(client, voice):
    add_sound(client, "boom", 101)
    output = generated_output(client, voice, "{boom}")
    assert client.put("/sounds/boom", json={"freesound_id": 303}).status_code == 200

    saved = save(client, output).json()

    assert [credit["title"] for credit in saved["sounds"]] == ["Big Boom"]


def test_a_saved_output_survives_eviction_from_the_cache(client, voice):
    first = generated_output(client, voice, "Save me.")
    saved = save(client, first).json()

    for n in range(5):
        generated_output(client, voice, f"Filler {n}.")

    assert client.get(first["audio_url"]).status_code == 404, "evicted from the cache"
    assert [s["id"] for s in client.get("/saved").json()] == [saved["id"]]
    assert client.get(saved["audio_url"]).status_code == 200


def test_a_saved_output_survives_a_restart(write_config):
    config = write_config()
    fakes = FakeEngines()
    with run_app(config, fakes) as client:
        output = generated_output(client, saved_voice(client), "Still here?")
        saved = save(client, output).json()

    with run_app(config, fakes) as client:
        assert client.get("/outputs").json() == []
        assert client.get("/saved").json() == [saved]
        assert client.get(saved["audio_url"]).status_code == 200


def test_saving_twice_keeps_one_copy(client, voice, data_folder):
    output = generated_output(client, voice, "Once is enough.")

    first = save(client, output)
    second = save(client, output)

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == first.json()
    assert len(list((data_folder / "saved").iterdir())) == 2


def test_an_output_shows_what_it_was_saved_as(client, voice):
    output = generated_output(client, voice, "Mark me saved.")
    assert output["saved_id"] is None

    saved = save(client, output).json()

    assert client.get(f"/outputs/{output['id']}").json()["saved_id"] == saved["id"]
    assert client.get("/outputs").json()[0]["saved_id"] == saved["id"]


def test_saved_outputs_list_newest_first(client, voice):
    ids = [
        save(client, generated_output(client, voice, f"Take {n}.")).json()["id"] for n in range(3)
    ]

    assert [s["id"] for s in client.get("/saved").json()] == list(reversed(ids))


def test_an_output_downloads_under_a_readable_name(client, voice):
    output = generated_output(client, voice, "Download me.")

    response = client.get(output["audio_url"])

    assert output["download_name"].startswith("old-narrator-")
    assert output["download_name"].endswith(".wav")
    assert f'filename="{output["download_name"]}"' in response.headers["content-disposition"]


def test_a_half_saved_output_isnt_listed(client, voice, data_folder):
    saved = save(client, generated_output(client, voice, "Whole.")).json()
    (data_folder / "saved" / f"{saved['id']}.wav").unlink()

    assert client.get("/saved").json() == []
    assert client.get(saved["audio_url"]).status_code == 404


@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/outputs/" + "a" * 32 + "/save"),
        ("GET", "/saved/2026-11-07-143022-old-narrator-abcdef"),
        ("GET", "/saved/2026-11-07-143022-old-narrator-abcdef/audio"),
        ("GET", "/saved/2026-11-07-143022-old-narrator-abcdef/record"),
        ("GET", "/saved/..%2Fconfig"),
        ("GET", "/saved/not-an-id/audio"),
    ],
)
def test_what_isnt_there_is_404(client, method, path):
    assert client.request(method, path).status_code == 404
