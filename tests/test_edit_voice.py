import pytest
from conftest import run_app
from voices import DESCRIPTION, designed_draft, run_job, succeeded

GENERIC = "I never thought it would come to this, but here we are, and there's no going back now."


@pytest.fixture
def voice(client) -> dict:
    """A saved Voice, accepted from a freshly designed Draft voice."""
    response = client.post(
        "/voices", json={"draft_id": designed_draft(client)["id"], "name": "Old Narrator"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def get_voice(client, voice_id: str) -> dict:
    return client.get(f"/voices/{voice_id}").json()


def pending_take(client, voice_id: str, path: str, body: dict | None = None) -> str:
    """Start an editing job at `path` (under the Voice) and return the pending take it made."""
    return succeeded(run_job(client, f"/voices/{voice_id}{path}", body))["take"]


def clip(client, url: str) -> bytes:
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "audio/wav"
    return response.content


def test_a_custom_preset_waits_as_a_pending_take_until_accepted(client, voice, fakes):
    take = pending_take(client, voice["id"], "/presets", {"name": "angry-soft"})

    waiting = get_voice(client, voice["id"])
    assert "angry-soft" not in waiting["presets"], "nothing changes until it's accepted"
    [pending] = waiting["pending"]
    assert pending["id"] == take and pending["emotion"] == "angry-soft"
    assert clip(client, pending["url"]) == fakes.calls[-1].wav

    accepted = client.post(f"/voices/{voice['id']}/takes/{take}/accept")

    assert accepted.status_code == 200
    preset = accepted.json()["presets"]["angry-soft"]
    assert clip(client, preset["clip_url"]) == fakes.calls[-1].wav
    assert accepted.json()["pending"] == []


def test_a_custom_preset_starts_from_neutrals_values_and_a_generic_sample(client, voice, fakes):
    take = pending_take(client, voice["id"], "/presets", {"name": "angry-soft"})

    preset = client.post(f"/voices/{voice['id']}/takes/{take}/accept").json()["presets"]
    neutral = voice["presets"]["neutral"]
    assert (preset["angry-soft"]["exaggeration"], preset["angry-soft"]["cfg"]) == (
        neutral["exaggeration"],
        neutral["cfg"],
    )
    assert preset["angry-soft"]["sample"] == GENERIC
    assert fakes.calls[-1].inputs == {
        "description": DESCRIPTION,
        "text": GENERIC,
        "emotion": "angry-soft",
    }, "designed from the Voice's locked description"


def test_a_custom_preset_can_bring_its_own_sample_and_values(client, voice, fakes):
    body = {"name": "Whispering", "sample": "Keep  it down.", "exaggeration": 0.2, "cfg": 0.7}

    take = pending_take(client, voice["id"], "/presets", body)

    presets = client.post(f"/voices/{voice['id']}/takes/{take}/accept").json()["presets"]
    whispering = presets["whispering"]
    assert (whispering["sample"], whispering["exaggeration"], whispering["cfg"]) == (
        "Keep it down.",
        0.2,
        0.7,
    )
    assert fakes.calls[-1].inputs["text"] == "Keep it down."


@pytest.mark.parametrize(
    "body, status",
    [
        pytest.param({"name": "angry"}, 409, id="already-a-preset"),
        pytest.param({"name": "very angry"}, 422, id="bad-name"),
        pytest.param({"name": "calm", "exaggeration": 3}, 422, id="value-out-of-range"),
    ],
)
def test_a_custom_preset_needs_a_new_proper_name(client, voice, body, status):
    response = client.post(f"/voices/{voice['id']}/presets", json=body)

    assert response.status_code == status
    assert client.get("/jobs/current").json() is None, "no job started"


def test_a_rejected_take_leaves_the_old_preset_in_place(client, voice):
    before = get_voice(client, voice["id"])
    old_clip = clip(client, before["presets"]["angry"]["clip_url"])
    take = pending_take(client, voice["id"], "/presets/angry/regenerate")

    rejected = client.delete(f"/voices/{voice['id']}/takes/{take}")

    assert rejected.status_code == 204
    after = get_voice(client, voice["id"])
    assert after["presets"] == before["presets"]
    assert clip(client, after["presets"]["angry"]["clip_url"]) == old_clip
    assert after["pending"] == []
    assert client.get(f"/voices/{voice['id']}/takes/{take}").status_code == 404


def test_an_accepted_regeneration_replaces_the_clip_and_keeps_the_values(client, voice, fakes):
    take = pending_take(client, voice["id"], "/presets/angry/regenerate")

    after = client.post(f"/voices/{voice['id']}/takes/{take}/accept").json()

    angry = after["presets"]["angry"]
    assert clip(client, angry["clip_url"]) == fakes.calls[-1].wav
    assert (angry["exaggeration"], angry["cfg"]) == (
        voice["presets"]["angry"]["exaggeration"],
        voice["presets"]["angry"]["cfg"],
    )
    for name in voice["presets"]:
        if name != "angry":
            assert after["presets"][name] == voice["presets"][name], f"{name} is untouched"


def test_an_accepted_retune_changes_the_values_not_the_clip(client, voice, fakes):
    old_clip = clip(client, voice["presets"]["sad"]["clip_url"])

    take = pending_take(
        client, voice["id"], "/presets/sad/retune", {"exaggeration": 0.9, "cfg": 0.2}
    )

    speak = fakes.calls[-1]
    assert speak.model == "speech"
    assert speak.inputs["reference_clip"].read_bytes() == old_clip
    assert (speak.inputs["exaggeration"], speak.inputs["cfg"]) == (0.9, 0.2)
    [pending] = get_voice(client, voice["id"])["pending"]
    assert pending["kind"] == "preview"
    assert clip(client, pending["url"]) == speak.wav, "the retune can be heard first"
    sad = client.post(f"/voices/{voice['id']}/takes/{take}/accept").json()["presets"]["sad"]
    assert (sad["exaggeration"], sad["cfg"]) == (0.9, 0.2)
    assert clip(client, sad["clip_url"]) == old_clip


def test_the_neutral_values_can_be_retuned(client, voice):
    take = pending_take(
        client, voice["id"], "/presets/neutral/retune", {"exaggeration": 0.6, "cfg": 0.4}
    )

    neutral = client.post(f"/voices/{voice['id']}/takes/{take}/accept").json()["presets"]
    assert (neutral["neutral"]["exaggeration"], neutral["neutral"]["cfg"]) == (0.6, 0.4)


def test_replacing_the_neutral_clip_is_refused(client, voice):
    response = client.post(f"/voices/{voice['id']}/presets/neutral/regenerate")

    assert response.status_code == 409
    assert "locked" in response.json()["detail"]
    assert client.get("/jobs/current").json() is None, "no job started"


def test_removing_neutral_is_refused(client, voice):
    response = client.delete(f"/voices/{voice['id']}/presets/neutral")

    assert response.status_code == 409
    assert "neutral" in get_voice(client, voice["id"])["presets"]


def test_any_other_preset_can_be_removed_with_its_pending_takes(client, voice):
    pending_take(client, voice["id"], "/presets/angry/regenerate")

    removed = client.delete(f"/voices/{voice['id']}/presets/angry")

    assert removed.status_code == 200
    assert "angry" not in removed.json()["presets"]
    assert removed.json()["pending"] == []
    assert client.get(voice["presets"]["angry"]["clip_url"]).status_code == 404


def test_several_pending_takes_wait_side_by_side(client, voice):
    first = pending_take(client, voice["id"], "/presets/angry/regenerate")
    second = pending_take(client, voice["id"], "/presets/angry/regenerate")

    client.post(f"/voices/{voice['id']}/takes/{second}/accept")

    [still_waiting] = get_voice(client, voice["id"])["pending"]
    assert still_waiting["id"] == first, "accepting one take leaves the others to decide on"


def test_pending_takes_survive_an_app_restart(write_config, fakes):
    config = write_config()
    with run_app(config, fakes) as first_run:
        draft = designed_draft(first_run)
        voice = first_run.post("/voices", json={"draft_id": draft["id"], "name": "A"}).json()
        take = pending_take(first_run, voice["id"], "/presets/angry/regenerate")

    with run_app(config) as second_run:
        [pending] = second_run.get(f"/voices/{voice['id']}").json()["pending"]
        assert pending["id"] == take
        assert second_run.post(f"/voices/{voice['id']}/takes/{take}/accept").status_code == 200


def test_a_failed_regeneration_changes_nothing(client, voice, fakes):
    # The voice design model is still loaded from designing the draft, so fail the design.
    fakes.fail_to_run["voice design"] = MemoryError()

    status = run_job(client, f"/voices/{voice['id']}/presets/angry/regenerate")

    assert status["state"] == "failed"
    assert get_voice(client, voice["id"]) == voice


def test_a_deleted_voice_is_gone_with_its_clips_and_pending_takes(client, voice, data_folder):
    pending_take(client, voice["id"], "/presets/angry/regenerate")

    response = client.delete(f"/voices/{voice['id']}")

    assert response.status_code == 204
    assert client.get("/voices").json() == []
    assert client.get(voice["presets"]["neutral"]["clip_url"]).status_code == 404
    assert not (data_folder / "voices" / voice["id"]).exists()
    assert not (data_folder / "drafts" / "voices" / voice["id"]).exists()
    assert client.delete(f"/voices/{voice['id']}").status_code == 404


def test_saved_clips_are_never_played_from_a_stale_cache(client, voice):
    response = client.get(voice["presets"]["angry"]["clip_url"])

    assert response.headers["cache-control"] == "no-cache"


def test_the_voice_design_model_gives_the_memory_back_after_editing(client, voice, fakes):
    client.app.state.models.preload_speech()
    events_before = len(fakes.events)

    pending_take(client, voice["id"], "/presets/angry/regenerate")

    assert fakes.events[events_before:] == [
        "close speech",
        "load voice design",
        "close voice design",
        "load speech",
    ]


@pytest.mark.parametrize(
    "method, path",
    [
        ("post", "/voices/0123456789abcdef0123456789abcdef/presets/angry/regenerate"),
        ("post", "/voices/{id}/presets/whispering/regenerate"),
        ("post", "/voices/{id}/presets/whispering/retune"),
        ("delete", "/voices/{id}/presets/whispering"),
        ("post", "/voices/{id}/takes/angry-0123abcd/accept"),
        ("delete", "/voices/{id}/takes/angry-0123abcd"),
        ("get", "/voices/{id}/takes/..%2Fvoice"),
    ],
)
def test_editing_what_isnt_there_is_404(client, voice, method, path):
    kwargs = {"json": {"exaggeration": 0.5, "cfg": 0.5}} if path.endswith("retune") else {}

    response = getattr(client, method)(path.format(id=voice["id"]), **kwargs)

    assert response.status_code == 404
