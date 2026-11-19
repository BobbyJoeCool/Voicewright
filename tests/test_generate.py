"""Generating a Script into one Output, on fake engines: the right clips, in order."""

import pytest
from fakes import FakeEngines, tone_wav
from scripts import (
    add_sound,
    generate,
    generated_output,
    loudness,
    pieces,
    pitch,
    read_wav,
    saved_voice,
)
from voices import succeeded

from voicewright.assembler import GAP_MS, TARGET_DBFS
from voicewright.engines import OutOfMemory


@pytest.fixture
def voice(client) -> dict:
    return saved_voice(client)


def speech_calls(fakes: FakeEngines):
    return [call for call in fakes.calls if call.model == "speech"]


def audio(client, url: str) -> bytes:
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "audio/wav"
    return response.content


def test_the_output_has_the_right_clips_in_order(client, voice, fakes):
    boom = add_sound(client, "boom")
    before = len(fakes.calls)

    output = generated_output(
        client, voice, "Hello there. [angry] Get out! {boom} (laugh) [sad] Goodbye."
    )

    spoken = speech_calls(fakes)[-3:]
    assert len(fakes.calls) == before + 3, "three lines spoken; the sound and (laugh) aren't"
    assert [c.inputs["text"] for c in spoken] == ["Hello there.", "Get out!", "Goodbye."]
    wav = audio(client, output["audio_url"])
    samples, rate, channels, width = read_wav(wav)
    assert (channels, width) == (1, 2), "standard WAV"
    found = pieces(wav)
    sound_samples, sound_rate, _, _ = read_wav(audio(client, boom["audio_url"]))
    expected = [
        pitch(read_wav(spoken[0].wav)[0], 24_000),
        pitch(read_wav(spoken[1].wav)[0], 24_000),
        pitch(sound_samples, sound_rate),
        pitch(read_wav(spoken[2].wav)[0], 24_000),
    ]
    assert len(found) == len(expected)
    for piece, hz in zip(found, expected, strict=True):
        assert pitch(piece, rate) == pytest.approx(hz, abs=8)


def test_each_line_is_spoken_with_its_emotions_clip_and_values(client, voice, fakes):
    generated_output(client, voice, "Calm. [angry] Furious. [excited] Thrilled!")

    spoken = speech_calls(fakes)[-3:]
    values = [(c.inputs["exaggeration"], c.inputs["cfg"]) for c in spoken]
    presets = voice["presets"]
    assert values == [
        (presets[e]["exaggeration"], presets[e]["cfg"]) for e in ("neutral", "angry", "excited")
    ]
    clips = [audio(client, presets[e]["clip_url"]) for e in ("neutral", "angry", "excited")]
    assert fakes.speech_references[-3:] == clips


def test_the_output_has_short_gaps_and_even_volume(client, voice, fakes):
    add_sound(client, "boom")

    output = generated_output(client, voice, "One. {boom} Two.")

    wav = audio(client, output["audio_url"])
    found = pieces(wav)
    assert len(found) == 3
    for piece in found:
        assert loudness(piece) == pytest.approx(TARGET_DBFS, abs=1.5)
    samples, rate, _, _ = read_wav(wav)
    sound_seconds = 0.51
    expected = 0.1 + sound_seconds + 0.1 + 2 * GAP_MS / 1000
    assert len(samples) / rate == pytest.approx(expected, abs=0.03)
    assert output["duration"] == pytest.approx(len(samples) / rate, abs=0.01)


def test_a_long_passage_reaches_the_speech_engine_whole(client, voice, fakes):
    passage = " ".join(f"word{n}" for n in range(120)) + "."

    generated_output(client, voice, passage)

    assert speech_calls(fakes)[-1].inputs["text"] == passage


def test_progress_counts_the_segments_that_make_sound(write_config, fakes):
    seen = []
    with_app = {}

    def note_progress(call_number):
        running = with_app["client"].app.state.jobs.running
        if running is not None and running.kind == "script":
            seen.append((running.progress.step, running.progress.total, running.progress.message))

    from conftest import run_app

    with run_app(write_config(), fakes) as client:
        with_app["client"] = client
        voice = saved_voice(client)
        add_sound(client, "boom")
        fakes.before_call = note_progress
        status = generate(client, voice, "[angry] Hello there, old friend. (laugh) {boom} Bye.")

    succeeded(status)
    assert seen == [
        (0, 3, "Speaking “Hello there, old friend.” (angry)"),
        (2, 3, "Speaking “Bye.” (angry)"),
    ]
    assert status["progress"] == {"step": 3, "total": 3, "message": "Putting the Output together"}


def test_a_script_of_only_sounds_needs_no_speech_model(client, voice, fakes):
    add_sound(client, "boom")
    fakes.events.clear()

    output = generated_output(client, voice, "{boom} {boom}")

    assert fakes.events == [], "the speech model wasn't loaded"
    assert len(pieces(audio(client, output["audio_url"]))) == 2


def test_the_output_keeps_a_record_of_what_made_it(client, voice):
    boom = add_sound(client, "boom")

    output = generated_output(client, voice, "Hi. [sad] Oh no. {boom} (sigh)")

    assert output["voice_name"] == "Old Narrator"
    assert output["script"] == "Hi. [sad] Oh no. {boom} (sigh)"
    presets = voice["presets"]
    assert output["presets"] == {
        e: {"exaggeration": presets[e]["exaggeration"], "cfg": presets[e]["cfg"]}
        for e in ("neutral", "sad")
    }
    assert output["sounds"] == [{"name": "boom", **boom["credit"]}]
    assert output["warnings"] == ["(sigh) is skipped: Vocal effects can't be rendered yet."]
    assert client.get("/outputs").json() == [output]


def test_a_rejected_script_starts_no_job(client, voice, fakes):
    calls = len(fakes.calls)

    response = client.post(
        "/scripts/generate", json={"voice_id": voice["id"], "script": "[furious] {thunder} [bad"}
    )

    assert response.status_code == 422
    body = response.json()
    assert body["missing_emotions"] == ["furious"]
    assert body["missing_sounds"] == ["thunder"]
    assert len(body["parse_errors"]) == 1
    assert client.get("/jobs/current").json() is None
    assert len(fakes.calls) == calls
    assert client.get("/outputs").json() == []


def test_generating_while_a_job_runs_is_409(client, voice, fakes):
    import threading

    release = threading.Event()
    fakes.before_call = lambda n: release.wait(5)
    first = client.post("/scripts/generate", json={"voice_id": voice["id"], "script": "One."})
    try:
        second = client.post("/scripts/generate", json={"voice_id": voice["id"], "script": "Two."})
    finally:
        release.set()

    assert first.status_code == 202
    assert second.status_code == 409
    assert "script job is already running" in second.json()["detail"]


def test_a_failed_generation_leaves_no_output_and_says_why(client, voice, fakes):
    fakes.fail_to_run["speech"] = OutOfMemory("MLX ran out")

    status = generate(client, voice, "Hello.")

    assert status["state"] == "failed"
    assert "ran out of memory" in status["error"]
    assert client.get("/outputs").json() == []


def test_a_preset_changed_after_generate_starts_doesnt_change_the_output(client, voice, fakes):
    """What a Script uses is copied when it starts, so editing the Voice mid-job is safe."""
    import threading

    release = threading.Event()
    fakes.before_call = lambda n: release.wait(5)
    started = client.post(
        "/scripts/generate", json={"voice_id": voice["id"], "script": "[angry] Hey!"}
    )
    assert client.delete(f"/voices/{voice['id']}/presets/angry").status_code == 200
    release.set()
    from voices import wait_until_finished

    status = wait_until_finished(client, started.json()["job_id"])

    assert status["state"] == "succeeded", status["error"]
    assert (
        speech_calls(fakes)[-1].inputs["exaggeration"] == voice["presets"]["angry"]["exaggeration"]
    )


def test_outputs_that_arent_there_are_404(client):
    assert client.get("/outputs/" + "a" * 32).status_code == 404
    assert client.get("/outputs/" + "a" * 32 + "/audio").status_code == 404
    assert client.get("/outputs/not-an-id").status_code == 404


def test_the_fake_tones_differ_enough_to_tell_apart():
    """The order test tells clips apart by pitch: neighbouring fake calls must not blur."""
    a, b = (read_wav(tone_wav(hz))[0] for hz in (300, 320))
    assert abs(pitch(a, 24_000) - pitch(b, 24_000)) > 16
