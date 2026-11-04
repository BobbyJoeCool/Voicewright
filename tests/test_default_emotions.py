import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from voicewright.app import create_app
from voicewright.default_emotions import DEFAULT_EMOTIONS_FILE, DefaultEmotionsError

# Draft voices arrive in step 2.2; its tests check a new Draft voice gets every emotion listed
# here. These check the list itself, as the API serves it.


def shipped_emotions() -> dict:
    return json.loads(DEFAULT_EMOTIONS_FILE.read_text(encoding="utf-8"))


def test_v1_starts_every_voice_with_neutral_angry_sad_and_excited(client):
    names = [emotion["name"] for emotion in client.get("/emotions/defaults").json()]

    assert {"neutral", "angry", "sad", "excited"} <= set(names)


def test_every_emotion_in_the_file_is_served_with_its_sample_and_values(client):
    served = client.get("/emotions/defaults").json()

    assert served == [{"name": name, **entry} for name, entry in shipped_emotions().items()], (
        "every emotion, in file order, with its sample sentence and starting values"
    )


@pytest.fixture
def emotions_file(tmp_path):
    """Write a Default emotion set file; return its path."""

    def write(entries) -> Path:
        path = tmp_path / "default_emotions.json"
        path.write_text(entries if isinstance(entries, str) else json.dumps(entries))
        return path

    return write


def test_an_emotion_added_to_the_file_is_served_with_no_code_change(
    write_config, fakes, emotions_file
):
    entries = shipped_emotions()
    entries["whispering"] = {"sample": "Keep your voice down.", "exaggeration": 0.4, "cfg": 0.6}

    app = create_app(write_config(), fakes.engines(), default_emotions_file=emotions_file(entries))
    with TestClient(app) as client:
        served = client.get("/emotions/defaults").json()

    assert served[-1] == {
        "name": "whispering",
        "sample": "Keep your voice down.",
        "exaggeration": 0.4,
        "cfg": 0.6,
    }


NEUTRAL = {"sample": "Hello.", "exaggeration": 0.5, "cfg": 0.5}


@pytest.mark.parametrize(
    "entries, problem",
    [
        pytest.param("{not json", "is not valid JSON", id="not-json"),
        pytest.param(["neutral"], "needs an object of emotions", id="a-list"),
        pytest.param({"angry": NEUTRAL}, "needs a neutral emotion", id="no-neutral"),
        pytest.param(
            f'{{"neutral": {json.dumps(NEUTRAL)}, "neutral": {json.dumps(NEUTRAL)}}}',
            "lists neutral more than once",
            id="repeated-name",
        ),
        pytest.param({"neutral": NEUTRAL, "Very Angry": NEUTRAL}, "lowercase", id="bad-name"),
        pytest.param({"neutral": "calm"}, "needs sample, exaggeration, and cfg", id="not-object"),
        pytest.param(
            {"neutral": {"sample": "Hello.", "exaggeration": 0.5}}, "missing cfg", id="missing"
        ),
        pytest.param({"neutral": {**NEUTRAL, "speed": 1}}, "unknown speed", id="unknown-setting"),
        pytest.param({"neutral": {**NEUTRAL, "sample": "  "}}, "needs a sample", id="no-sample"),
        pytest.param(
            {"neutral": {**NEUTRAL, "exaggeration": 3}},
            "exaggeration must be a number from 0 to 2",
            id="exaggeration-too-high",
        ),
        pytest.param(
            {"neutral": {**NEUTRAL, "cfg": "0.5"}},
            "cfg must be a number from 0 to 1",
            id="cfg-as-text",
        ),
        pytest.param(
            {"neutral": {**NEUTRAL, "cfg": True}}, "cfg must be a number", id="cfg-as-true"
        ),
    ],
)
def test_a_broken_file_is_refused_with_what_to_fix(
    write_config, fakes, emotions_file, entries, problem
):
    path = emotions_file(entries)

    with pytest.raises(DefaultEmotionsError, match=problem) as refused:
        create_app(write_config(), fakes.engines(), default_emotions_file=path)

    assert str(path) in str(refused.value), "the message names the file"


def test_a_missing_file_is_refused(write_config, fakes, tmp_path):
    with pytest.raises(DefaultEmotionsError, match="can't read"):
        create_app(write_config(), fakes.engines(), default_emotions_file=tmp_path / "gone.json")
