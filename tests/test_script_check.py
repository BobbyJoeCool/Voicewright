"""Checking a Script: parsing, and every rejection and warning case, through the API."""

import pytest
from scripts import add_sound, check, saved_voice


@pytest.fixture
def voice(client) -> dict:
    return saved_voice(client)


def segments(response) -> list[tuple]:
    """The Segments, each as (kind, emotion or name, text)."""
    return [(s["kind"], s["emotion"] or s["name"], s["text"]) for s in response.json()["segments"]]


def ready(response) -> dict:
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is True
    assert (body["missing_emotions"], body["missing_sounds"], body["parse_errors"]) == ([], [], [])
    return body


def rejected(response) -> dict:
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["ready"] is False
    assert body["detail"].startswith("The Script can't be generated yet")
    return body


def test_untagged_speech_is_neutral(client, voice):
    response = check(client, voice, "The road out of town runs past the river.")

    ready(response)
    assert segments(response) == [
        ("speech", "neutral", "The road out of town runs past the river.")
    ]


def test_emotion_tags_carry_forward_and_effects_land_in_order(client, voice):
    add_sound(client, "explosion")

    response = check(
        client,
        voice,
        "Hello there. [angry] I hate you! (scream) {explosion} Still angry. [sad] Goodbye.",
    )

    ready(response)
    assert segments(response) == [
        ("speech", "neutral", "Hello there."),
        ("speech", "angry", "I hate you!"),
        ("vocal_effect", "scream", None),
        ("sound_effect", "explosion", None),
        ("speech", "angry", "Still angry."),
        ("speech", "sad", "Goodbye."),
    ]


def test_names_are_matched_ignoring_case(client, voice):
    add_sound(client, "door-slam")

    response = check(client, voice, "[ANGRY] Out! { Door-Slam }")

    ready(response)
    assert segments(response) == [
        ("speech", "angry", "Out!"),
        ("sound_effect", "door-slam", None),
    ]


def test_whitespace_between_markers_is_dropped_and_spacing_is_tidied(client, voice):
    add_sound(client, "boom")

    response = check(client, voice, "  [sad]  \n\n {boom}\n  One,\n   two.  ")

    ready(response)
    assert segments(response) == [("sound_effect", "boom", None), ("speech", "sad", "One, two.")]


def test_a_segment_knows_where_it_starts(client, voice):
    add_sound(client, "boom")

    response = check(client, voice, "Hi. {boom}  [sad]  Bye.")

    assert [s["position"] for s in ready(response)["segments"]] == [0, 4, 19]


def test_a_skipped_vocal_effect_is_a_warning_not_a_rejection(client, voice):
    response = check(client, voice, "Well. (laugh) That's funny.\n(Sigh)")

    body = ready(response)
    assert body["warnings"] == [
        {
            "position": 6,
            "line": 1,
            "column": 7,
            "message": "(laugh) is skipped: Vocal effects can't be rendered yet.",
        },
        {
            "position": 28,
            "line": 2,
            "column": 1,
            "message": "(sigh) is skipped: Vocal effects can't be rendered yet.",
        },
    ]


def test_every_missing_emotion_is_listed_once_in_order(client, voice):
    response = check(client, voice, "[furious] A. [sad] B. [whisper] C. [Furious] D. [whisper]")

    body = rejected(response)
    assert body["missing_emotions"] == ["furious", "whisper"]
    assert "[furious], [whisper]" in body["detail"]


def test_a_tag_with_no_speech_after_it_is_still_checked(client, voice):
    assert rejected(check(client, voice, "Hello. [furious]"))["missing_emotions"] == ["furious"]


def test_every_missing_sound_is_listed_once_in_order(client, voice):
    add_sound(client, "boom")

    response = check(client, voice, "{thunder} A {boom} B {rain} {Thunder}")

    assert rejected(response)["missing_sounds"] == ["thunder", "rain"]


def test_one_request_reports_every_problem_at_once(client, voice):
    response = check(client, voice, "[furious] Stop! {thunder} (laugh) [angry Unclosed.")

    body = rejected(response)
    assert body["missing_emotions"] == ["furious"]
    assert body["missing_sounds"] == ["thunder"]
    assert [(e["line"], e["column"]) for e in body["parse_errors"]] == [(1, 35)]
    assert "never closed" in body["parse_errors"][0]["message"]
    assert len(body["warnings"]) == 1
    assert "[furious]" in body["detail"]
    assert "{thunder}" in body["detail"]
    assert "1 tag needs fixing" in body["detail"]


@pytest.mark.parametrize(
    "script, position, line, column, says",
    [
        ("[angry I hate you", 0, 1, 1, "This [ is never closed"),
        ("Hi (laugh", 3, 1, 4, "This ( is never closed"),
        ("Hi {boom", 3, 1, 4, "This { is never closed"),
        ("Line one.\n[angry\nTwo.", 10, 2, 1, "This [ is never closed"),
        ("Hi [angry (laugh) there", 3, 1, 4, "This [ is never closed"),
        ("Hi] there", 2, 1, 3, "This ] has no [ before it"),
        ("Hi) there", 2, 1, 3, "This ) has no ( before it"),
        ("Hi} there", 2, 1, 3, "This } has no { before it"),
        ("Hi [] there", 3, 1, 4, "[] is empty"),
        ("Hi {  } there", 3, 1, 4, "{  } is empty"),
        ("Hi [very angry] there", 3, 1, 4, "[very angry] can't be an Emotion tag"),
        ("Hi [2angry] there", 3, 1, 4, "[2angry] can't be an Emotion tag"),
        ("Hi (and then) there", 3, 1, 4, "(and then) can't be a Vocal effect"),
        ("Hi {door slam} there", 3, 1, 4, "{door slam} can't be a Sound effect"),
        ("Hi {" + "a" * 61 + "} there", 3, 1, 4, "{" + "a" * 61 + "} can't be a Sound effect"),
    ],
)
def test_a_malformed_tag_is_a_parse_error_with_its_position(
    client, voice, script, position, line, column, says
):
    body = rejected(check(client, voice, script))

    [error] = body["parse_errors"]
    assert (error["position"], error["line"], error["column"]) == (position, line, column)
    assert error["message"].startswith(says), error["message"]


def test_every_parse_error_is_reported(client, voice):
    body = rejected(check(client, voice, "One] two [three\n{} four (five six)"))

    where = [(e["line"], e["column"]) for e in body["parse_errors"]]
    assert where == [(1, 4), (1, 10), (2, 1), (2, 9)]
    assert "4 tags need fixing" in body["detail"]


@pytest.mark.parametrize("script", ["", "   \n ", "(laugh) (sigh)", "[sad]"])
def test_a_script_with_nothing_to_say_or_play_is_rejected(client, voice, script):
    [error] = rejected(check(client, voice, script))["parse_errors"]

    assert error["message"].startswith("There's nothing to say or play")


def test_a_script_of_just_a_sound_is_fine(client, voice):
    add_sound(client, "boom")

    ready(check(client, voice, "{boom}"))


def test_checking_generates_nothing(client, voice, fakes):
    calls = len(fakes.calls)

    ready(check(client, voice, "Hello. [angry] Goodbye."))

    assert len(fakes.calls) == calls
    assert client.get("/jobs/current").json() is None


def test_a_voice_that_isnt_there_is_404(client):
    response = client.post("/scripts/check", json={"voice_id": "0" * 32, "script": "Hi."})

    assert response.status_code == 404


def test_a_script_that_is_far_too_long_is_refused(client, voice):
    response = check(client, voice, "word " * 4001)

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "string_too_long"
