import threading

import pytest
from conftest import run_app
from voices import DESCRIPTION, designed_draft, get_draft, run_job, succeeded, wait_until_finished


def regenerate(client, draft_id: str, emotion: str) -> dict:
    return run_job(client, f"/voices/drafts/{draft_id}/presets/{emotion}/regenerate")


def retune(client, draft_id: str, emotion: str, exaggeration: float, cfg: float) -> dict:
    body = {"exaggeration": exaggeration, "cfg": cfg}
    return run_job(client, f"/voices/drafts/{draft_id}/presets/{emotion}/retune", body)


def clip(client, url: str) -> bytes:
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    return response.content


def test_regenerating_one_preset_leaves_the_others_untouched(client):
    before = designed_draft(client)
    clips_before = {name: clip(client, p["clip_url"]) for name, p in before["presets"].items()}

    succeeded(regenerate(client, before["id"], "angry"))
    after = get_draft(client, before["id"])

    assert after["presets"]["angry"]["take"] == "angry-2"
    assert clip(client, after["presets"]["angry"]["clip_url"]) != clips_before["angry"]
    for name, preset in after["presets"].items():
        if name != "angry":
            assert preset == before["presets"][name], f"{name} is untouched"
            assert clip(client, preset["clip_url"]) == clips_before[name]


def test_the_neutral_clip_can_be_regenerated(client, fakes):
    draft = designed_draft(client)

    succeeded(regenerate(client, draft["id"], "neutral"))

    assert get_draft(client, draft["id"])["presets"]["neutral"]["take"] == "neutral-2"
    assert fakes.calls[-1].inputs["emotion"] is None, "designed as neutral, with no emotion"
    assert fakes.calls[-1].inputs["description"] == DESCRIPTION


def test_a_regenerated_take_is_designed_from_the_description_and_sample(client, fakes):
    samples = {e["name"]: e["sample"] for e in client.get("/emotions/defaults").json()}
    draft = designed_draft(client)

    succeeded(regenerate(client, draft["id"], "sad"))

    assert fakes.calls[-1].inputs == {
        "description": DESCRIPTION,
        "text": samples["sad"],
        "emotion": "sad",
    }


def test_regenerating_keeps_the_presets_tuned_values(client):
    draft = designed_draft(client)
    succeeded(retune(client, draft["id"], "angry", 0.9, 0.2))

    succeeded(regenerate(client, draft["id"], "angry"))

    preset = get_draft(client, draft["id"])["presets"]["angry"]
    assert (preset["exaggeration"], preset["cfg"]) == (0.9, 0.2)


def test_regenerating_a_missing_preset_fills_it_in(client, fakes, data_folder):
    def fail_on_the_second_clip(call_number):
        if call_number == 1:
            raise MemoryError

    fakes.before_call = fail_on_the_second_clip
    status = run_job(client, "/voices/design", {"description": DESCRIPTION})
    assert status["state"] == "failed"
    [draft_id] = [p.name for p in (data_folder / "drafts").iterdir() if p.is_dir()]
    fakes.before_call = None
    missing = get_draft(client, draft_id)["missing"][0]
    retune_first = client.post(
        f"/voices/drafts/{draft_id}/presets/{missing}/retune", json={"exaggeration": 1, "cfg": 0.5}
    )
    assert retune_first.status_code == 409, "a preset with no clip can't be retuned yet"

    succeeded(regenerate(client, draft_id, missing))

    draft = get_draft(client, draft_id)
    assert missing in draft["presets"]
    assert missing not in draft["missing"]


def test_retuning_speaks_the_sample_from_the_current_clip_with_the_new_values(client, fakes):
    samples = {e["name"]: e["sample"] for e in client.get("/emotions/defaults").json()}
    draft = designed_draft(client)

    result = succeeded(retune(client, draft["id"], "angry", 0.9, 0.2))

    speak = fakes.calls[-1]
    assert speak.model == "speech"
    assert speak.inputs["text"] == samples["angry"]
    assert (speak.inputs["exaggeration"], speak.inputs["cfg"]) == (0.9, 0.2)
    assert speak.inputs["reference_clip"].read_bytes() == clip(
        client, draft["presets"]["angry"]["clip_url"]
    ), "cloned from the preset's current Reference clip"
    after = get_draft(client, draft["id"])
    preview = next(t for t in after["takes"] if t["id"] == result["take"])
    assert preview["kind"] == "preview"
    assert (preview["exaggeration"], preview["cfg"], preview["clip"]) == (0.9, 0.2, "angry-1")
    assert clip(client, preview["url"]) == speak.wav, "the retune can be heard"


def test_retuning_changes_the_values_not_the_clip(client):
    draft = designed_draft(client)

    succeeded(retune(client, draft["id"], "angry", 0.9, 0.2))

    preset = get_draft(client, draft["id"])["presets"]["angry"]
    assert (preset["exaggeration"], preset["cfg"]) == (0.9, 0.2)
    assert preset["take"] == draft["presets"]["angry"]["take"]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"exaggeration": 2.5, "cfg": 0.5}, id="exaggeration-too-high"),
        pytest.param({"exaggeration": 0.5, "cfg": -0.1}, id="cfg-below-zero"),
        pytest.param({"exaggeration": 0.5}, id="no-cfg"),
    ],
)
def test_a_retune_needs_values_in_range(client, body):
    draft = designed_draft(client)

    response = client.post(f"/voices/drafts/{draft['id']}/presets/angry/retune", json=body)

    assert response.status_code == 422


def test_editing_the_description_redesigns_every_preset_from_it(client, fakes):
    draft = designed_draft(client)
    calls_before = len(fakes.calls)

    succeeded(
        run_job(
            client, f"/voices/drafts/{draft['id']}/redesign", {"description": "A bright woman."}
        )
    )

    after = get_draft(client, draft["id"])
    assert after["description"] == "A bright woman."
    assert {p["take"] for p in after["presets"].values()} == {
        f"{name}-2" for name in after["emotions"]
    }
    redesigned = fakes.calls[calls_before:]
    assert len(redesigned) == len(after["emotions"])
    assert {call.inputs["description"] for call in redesigned} == {"A bright woman."}
    earlier = next(t for t in after["takes"] if t["id"] == "angry-1")
    assert earlier["description"] == DESCRIPTION, "each take remembers what it was designed from"


def test_no_take_is_deleted_while_the_draft_is_open(client):
    draft = designed_draft(client)
    succeeded(regenerate(client, draft["id"], "angry"))
    succeeded(regenerate(client, draft["id"], "angry"))
    succeeded(retune(client, draft["id"], "sad", 0.4, 0.6))
    succeeded(
        run_job(
            client, f"/voices/drafts/{draft['id']}/redesign", {"description": "A bright woman."}
        )
    )

    takes = get_draft(client, draft["id"])["takes"]

    emotions = len(draft["emotions"])
    assert len(takes) == emotions + 2 + 1 + emotions
    assert len({t["id"] for t in takes}) == len(takes), "every take has its own id"
    for take in takes:
        assert client.get(take["url"]).status_code == 200, f"{take['id']} is still there"


def test_an_earlier_take_can_be_chosen_again(client):
    draft = designed_draft(client)
    first = clip(client, draft["presets"]["angry"]["clip_url"])
    succeeded(regenerate(client, draft["id"], "angry"))

    chosen = client.put(f"/voices/drafts/{draft['id']}/presets/angry", json={"take": "angry-1"})

    assert chosen.status_code == 200
    preset = chosen.json()["presets"]["angry"]
    assert preset["take"] == "angry-1"
    assert clip(client, preset["clip_url"]) == first


@pytest.mark.parametrize(
    "take", ["sad-1", "angry-preview-1", "angry-9"], ids=["other-emotion", "preview", "unknown"]
)
def test_only_a_designed_take_of_that_emotion_can_be_chosen(client, take):
    draft = designed_draft(client)
    succeeded(retune(client, draft["id"], "angry", 0.9, 0.2))

    response = client.put(f"/voices/drafts/{draft['id']}/presets/angry", json={"take": take})

    assert response.status_code == 409
    assert get_draft(client, draft["id"])["presets"]["angry"]["take"] == "angry-1"


def test_review_jobs_wait_their_turn(client, fakes):
    draft = designed_draft(client)
    reached, release = threading.Event(), threading.Event()

    def pause(call_number):
        reached.set()
        assert release.wait(timeout=5)

    fakes.before_call = pause
    first = client.post(f"/voices/drafts/{draft['id']}/presets/angry/regenerate").json()["job_id"]
    assert reached.wait(timeout=5)

    second = client.post(
        f"/voices/drafts/{draft['id']}/presets/sad/retune", json={"exaggeration": 1, "cfg": 0.5}
    )
    release.set()
    wait_until_finished(client, first)

    assert second.status_code == 409


@pytest.mark.parametrize(
    "path",
    [
        "/voices/drafts/0123456789abcdef0123456789abcdef/presets/angry/regenerate",
        "/voices/drafts/{id}/presets/whispering/regenerate",
        "/voices/drafts/{id}/presets/whispering/retune",
        "/voices/drafts/0123456789abcdef0123456789abcdef/redesign",
    ],
    ids=["unknown-draft", "unknown-emotion", "retune-unknown-emotion", "redesign-unknown-draft"],
)
def test_review_actions_on_something_that_isnt_there_are_404(client, path):
    draft = designed_draft(client)
    body = {"exaggeration": 0.5, "cfg": 0.5, "description": "A bright woman."}

    response = client.post(path.format(id=draft["id"]), json=body)

    assert response.status_code == 404
    assert client.get("/jobs/current").json() is None, "no job started"


def test_takes_survive_an_app_restart(write_config, fakes):
    config = write_config()
    with run_app(config, fakes) as first_run:
        draft = designed_draft(first_run)
        succeeded(regenerate(first_run, draft["id"], "angry"))
        before = get_draft(first_run, draft["id"])

    with run_app(config) as second_run:
        after = get_draft(second_run, draft["id"])
        assert all(second_run.get(t["url"]).status_code == 200 for t in after["takes"])

    assert after == before
