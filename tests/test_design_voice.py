import threading

import pytest
from conftest import run_app
from fakes import load_error
from voices import DESCRIPTION, design, designed_draft, wait_until_finished


def test_a_new_draft_voice_gets_every_default_emotion(client):
    default_emotions = client.get("/emotions/defaults").json()

    draft = designed_draft(client)

    assert draft["emotions"][0] == "neutral", "neutral, the Voice's identity, comes first"
    assert set(draft["emotions"]) == {emotion["name"] for emotion in default_emotions}
    assert set(draft["presets"]) == set(draft["emotions"])
    assert draft["missing"] == []
    assert draft["description"] == DESCRIPTION


def test_each_preset_starts_from_its_default_values(client):
    default_emotions = client.get("/emotions/defaults").json()

    presets = designed_draft(client)["presets"]

    for emotion in default_emotions:
        preset = presets[emotion["name"]]
        assert (preset["exaggeration"], preset["cfg"]) == (emotion["exaggeration"], emotion["cfg"])


def test_every_clip_is_fetchable_as_the_wav_that_was_designed(client, fakes):
    draft = designed_draft(client)

    designed = {call.inputs["emotion"] or "neutral": call.wav for call in fakes.calls}
    for name, preset in draft["presets"].items():
        clip = client.get(preset["clip_url"])
        assert clip.status_code == 200
        assert clip.headers["content-type"] == "audio/wav"
        assert clip.content == designed[name], f"the {name} clip is the one designed for it"


def test_each_clip_is_designed_from_the_description_and_its_sample_sentence(client, fakes):
    samples = {e["name"]: e["sample"] for e in client.get("/emotions/defaults").json()}

    designed_draft(client)

    for call in fakes.calls:
        name = call.inputs["emotion"] or "neutral"
        assert call.model == "voice design"
        assert call.inputs["description"] == DESCRIPTION
        assert call.inputs["text"] == samples[name]
    assert fakes.calls[0].inputs["emotion"] is None, "the neutral clip gets no emotion"


def test_the_description_is_tidied_before_designing(client):
    status = design(client, "  A gravelly older man,\n slow and calm.  ")

    draft = client.get(f"/voices/drafts/{status['result']['draft_id']}").json()
    assert draft["description"] == "A gravelly older man, slow and calm."


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"description": ""}, id="empty"),
        pytest.param({"description": "  \n "}, id="blank"),
        pytest.param({"description": "x" * 501}, id="too-long"),
        pytest.param({}, id="missing"),
    ],
)
def test_a_design_needs_a_description(client, body):
    response = client.post("/voices/design", json=body)

    assert response.status_code == 422
    assert client.get("/jobs/current").json() is None, "no job started"


@pytest.fixture
def paused_after_neutral(fakes):
    """Hold the design job after the neutral clip, until `release` is set."""
    reached, release = threading.Event(), threading.Event()

    def pause(call_number):
        if call_number == 1:
            reached.set()
            assert release.wait(timeout=5)

    fakes.before_call = pause
    return reached, release


def test_progress_shows_which_clip_is_being_designed(client, paused_after_neutral):
    reached, release = paused_after_neutral
    job_id = client.post("/voices/design", json={"description": DESCRIPTION}).json()["job_id"]
    assert reached.wait(timeout=5)

    progress = client.get(f"/jobs/{job_id}").json()["progress"]
    release.set()
    wait_until_finished(client, job_id)

    total = len(client.get("/emotions/defaults").json())
    assert progress["step"] == 1 and progress["total"] == total
    assert progress["message"].startswith("Designing the ") and "preset" in progress["message"]


def test_a_second_design_while_one_runs_gets_409(client, paused_after_neutral):
    reached, release = paused_after_neutral
    first = client.post("/voices/design", json={"description": DESCRIPTION}).json()["job_id"]
    assert reached.wait(timeout=5)

    second = client.post("/voices/design", json={"description": "A bright young woman."})
    release.set()
    wait_until_finished(client, first)

    assert second.status_code == 409
    assert second.json()["running_job_id"] == first


def test_designing_borrows_memory_from_the_speech_model_and_gives_it_back(client, fakes):
    client.app.state.models.preload_speech()

    designed_draft(client)

    assert fakes.events == [
        "load speech",
        "close speech",
        "load voice design",
        "close voice design",
        "load speech",
    ]
    assert fakes.most_loaded_at_once == 1


def test_a_voice_design_model_that_fails_to_load_leaves_no_draft(client, fakes, data_folder):
    fakes.fail_to_load["voice design"] = load_error("voice design model", "the weights are missing")

    status = design(client)

    assert status["state"] == "failed"
    assert "couldn't load the voice design model: the weights are missing" in status["error"]
    assert draft_folders(data_folder) == []


def draft_folders(data_folder):
    """The Draft voices on disk, for checking what a failed design leaves behind."""
    return [p for p in (data_folder / "drafts").iterdir() if p.is_dir()]


def test_a_design_that_stops_part_way_keeps_the_clips_already_designed(client, fakes, data_folder):
    def fail_on_the_second_clip(call_number):
        if call_number == 1:
            raise MemoryError

    fakes.before_call = fail_on_the_second_clip

    status = design(client)

    assert status["state"] == "failed"
    assert "ran out of memory" in status["error"]
    [folder] = draft_folders(data_folder)
    draft = client.get(f"/voices/drafts/{folder.name}").json()
    assert list(draft["presets"]) == ["neutral"]
    assert len(draft["missing"]) == len(draft["emotions"]) - 1
    assert client.get(draft["presets"]["neutral"]["clip_url"]).status_code == 200


def test_a_draft_voice_survives_an_app_restart(write_config, fakes):
    config = write_config()
    with run_app(config, fakes) as first_run:
        draft = designed_draft(first_run)

    with run_app(config) as second_run:
        again = second_run.get(f"/voices/drafts/{draft['id']}")
        clip = second_run.get(draft["presets"]["neutral"]["clip_url"])

    assert again.json() == draft
    assert clip.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/voices/drafts/0123456789abcdef0123456789abcdef", id="unknown-draft"),
        pytest.param("/voices/drafts/..%2F..%2Fconfig", id="not-a-draft-id"),
        pytest.param("/voices/drafts/0123456789abcdef0123456789abcdef/takes/neutral-1", id="take"),
    ],
)
def test_an_unknown_draft_is_404(client, path):
    assert client.get(path).status_code == 404


def test_a_take_the_draft_lacks_is_404(client):
    draft = designed_draft(client)

    assert client.get(f"/voices/drafts/{draft['id']}/takes/whispering-1").status_code == 404
    assert client.get(f"/voices/drafts/{draft['id']}/takes/..%2Fdraft.json").status_code == 404
