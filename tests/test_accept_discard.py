import threading

import pytest
from conftest import run_app
from voices import DESCRIPTION, designed_draft, get_draft, run_job, succeeded


def accept(client, draft_id: str, name: str = "Old Narrator"):
    return client.post("/voices", json={"draft_id": draft_id, "name": name})


def accepted_voice(client, name: str = "Old Narrator") -> dict:
    response = accept(client, designed_draft(client)["id"], name)
    assert response.status_code == 201, response.text
    return response.json()


def test_an_accepted_voice_appears_in_the_list_with_its_presets(client):
    draft = designed_draft(client)
    accepted = accept(client, draft["id"]).json()

    [voice] = client.get("/voices").json()

    assert voice == accepted
    assert voice["name"] == "Old Narrator"
    assert voice["description"] == DESCRIPTION
    assert set(voice["presets"]) == set(draft["emotions"])
    for name, preset in voice["presets"].items():
        drafted = draft["presets"][name]
        assert (preset["exaggeration"], preset["cfg"]) == (drafted["exaggeration"], drafted["cfg"])


def test_each_saved_preset_plays_the_take_chosen_in_review(client):
    draft = designed_draft(client)
    succeeded(run_job(client, f"/voices/drafts/{draft['id']}/presets/angry/regenerate"))
    client.put(f"/voices/drafts/{draft['id']}/presets/angry", json={"take": "angry-1"})
    succeeded(
        run_job(
            client,
            f"/voices/drafts/{draft['id']}/presets/sad/retune",
            {"exaggeration": 0.4, "cfg": 0.6},
        )
    )
    reviewed = get_draft(client, draft["id"])
    chosen = {name: client.get(p["clip_url"]).content for name, p in reviewed["presets"].items()}

    voice = accept(client, draft["id"]).json()

    for name, preset in voice["presets"].items():
        saved = client.get(preset["clip_url"])
        assert saved.headers["content-type"] == "audio/wav"
        assert saved.content == chosen[name], f"{name} is the take chosen in review"
    assert (voice["presets"]["sad"]["exaggeration"], voice["presets"]["sad"]["cfg"]) == (0.4, 0.6)


def test_a_voice_can_be_fetched_by_id(client):
    voice = accepted_voice(client)

    assert client.get(f"/voices/{voice['id']}").json() == voice


def test_accepting_closes_the_draft_and_its_takes(client):
    draft = designed_draft(client)

    accept(client, draft["id"])

    assert client.get(f"/voices/drafts/{draft['id']}").status_code == 404
    assert client.get("/voices/drafts").json() == []


@pytest.mark.parametrize("name", ["Old Narrator", "old narrator", "  OLD   narrator "])
def test_a_duplicate_name_is_refused_with_409(client, name):
    accepted_voice(client, "Old Narrator")
    second = designed_draft(client)

    response = accept(client, second["id"], name)

    assert response.status_code == 409
    assert "Old Narrator already exists" in response.json()["detail"]
    assert client.get(f"/voices/drafts/{second['id']}").status_code == 200, "the draft stays"
    assert len(client.get("/voices").json()) == 1


def test_two_accepts_under_one_name_at_once_save_only_one(client):
    drafts = [designed_draft(client)["id"] for _ in range(2)]
    results = []
    threads = [
        threading.Thread(target=lambda d=d: results.append(accept(client, d).status_code))
        for d in drafts
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == [201, 409]
    assert len(client.get("/voices").json()) == 1


def test_a_draft_with_missing_presets_cant_be_accepted(client, fakes):
    def fail_on_the_second_clip(call_number):
        if call_number == 1:
            raise MemoryError

    fakes.before_call = fail_on_the_second_clip
    assert run_job(client, "/voices/design", {"description": DESCRIPTION})["state"] == "failed"
    [draft] = client.get("/voices/drafts").json()

    response = accept(client, draft["id"])

    assert response.status_code == 409
    assert "regenerate it first" in response.json()["detail"]
    assert client.get("/voices").json() == []


@pytest.mark.parametrize(
    "name", ["", "   ", "x" * 61, "Bad\x07Name"], ids=["empty", "blank", "too-long", "control"]
)
def test_a_voice_needs_a_proper_name(client, name):
    draft = designed_draft(client)

    assert accept(client, draft["id"], name).status_code == 422


def test_accepting_an_unknown_draft_is_404(client):
    assert accept(client, "0123456789abcdef0123456789abcdef").status_code == 404


def test_a_discarded_draft_is_gone_with_every_take(client, data_folder):
    draft = designed_draft(client)

    response = client.delete(f"/voices/drafts/{draft['id']}")

    assert response.status_code == 204
    assert client.get(f"/voices/drafts/{draft['id']}").status_code == 404
    assert not (data_folder / "drafts" / draft["id"]).exists(), "its takes are off the disk"
    assert client.delete(f"/voices/drafts/{draft['id']}").status_code == 404


def test_open_drafts_are_listed_oldest_first(client):
    first = designed_draft(client, "A gravelly older man.")
    second = designed_draft(client, "A bright young woman.")

    listed = client.get("/voices/drafts").json()

    assert [d["id"] for d in listed] == [first["id"], second["id"]]
    assert listed[0] == get_draft(client, first["id"])


def test_a_draft_still_exists_after_an_app_restart(write_config, fakes):
    config = write_config()
    with run_app(config, fakes) as first_run:
        draft = designed_draft(first_run)

    with run_app(config) as second_run:
        listed = second_run.get("/voices/drafts").json()

    assert [d["id"] for d in listed] == [draft["id"]], "offered for resume on startup"


def test_saved_voices_survive_an_app_restart(write_config, fakes):
    config = write_config()
    with run_app(config, fakes) as first_run:
        voice = accepted_voice(first_run)

    with run_app(config) as second_run:
        assert second_run.get("/voices").json() == [voice]
        assert second_run.get(voice["presets"]["neutral"]["clip_url"]).status_code == 200


def test_voices_are_listed_by_name(client):
    for name in ["Zed", "anna", "Bob"]:
        accepted_voice(client, name)

    assert [v["name"] for v in client.get("/voices").json()] == ["anna", "Bob", "Zed"]


def test_a_broken_voice_file_doesnt_hide_the_others(client, data_folder):
    voice = accepted_voice(client, "Good")
    broken = data_folder / "voices" / ("f" * 32)
    broken.mkdir()
    (broken / "voice.json").write_text("{not json")

    assert client.get("/voices").json() == [voice]


@pytest.mark.parametrize(
    "path",
    [
        "/voices/0123456789abcdef0123456789abcdef",
        "/voices/..%2Fdrafts",
        "/voices/{id}/clips/whispering",
        "/voices/{id}/clips/..%2Fvoice.json",
    ],
    ids=["unknown-voice", "not-a-voice-id", "unknown-emotion", "not-a-clip"],
)
def test_what_isnt_there_is_404(client, path):
    voice = accepted_voice(client)

    assert client.get(path.format(id=voice["id"])).status_code == 404
