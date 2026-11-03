import io
import threading
import time
import wave
from pathlib import Path

import pytest
from fakes import load_error
from fastapi.testclient import TestClient

from voicewright.app import create_app
from voicewright.engines import OutOfMemory, UnsupportedVocalEffect, default_engines

# No product endpoint starts a job until voice design (step 2.2). Until then these tests add a
# route that starts whatever job they give it, and check everything else through the API.


@pytest.fixture
def start_job(client):
    """Start a job doing `work` through an HTTP route; return the response."""
    works = {}

    def start_route(kind: str):
        return {"job_id": client.app.state.jobs.start(kind, works[kind]).id}

    client.app.add_api_route("/test/jobs/{kind}", start_route, methods=["POST"])

    def start(kind, work):
        works[kind] = work
        return client.post(f"/test/jobs/{kind}")

    return start


@pytest.fixture
def models(client):
    """The app's model manager, for jobs that use the engines."""
    return client.app.state.models


def wait_until_finished(client, job_id: str, timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"/jobs/{job_id}").json()
        if status["state"] != "running":
            return status
        time.sleep(0.02)
    pytest.fail(f"job {job_id} never finished")


def held_open(report_first=None):
    """Work that reports `report_first`, then waits until `release` is set."""
    release, started = threading.Event(), threading.Event()

    def work(report):
        if report_first:
            report(*report_first)
        started.set()
        assert release.wait(timeout=5)
        return {"done": True}

    return work, started, release


def test_status_shows_progress_while_a_job_runs(client, start_job):
    work, started, release = held_open(report_first=(1, 3, "Designing the angry preset"))
    job_id = start_job("voice design", work).json()["job_id"]
    assert started.wait(timeout=5)

    status = client.get(f"/jobs/{job_id}").json()
    release.set()

    assert status["state"] == "running"
    assert status["kind"] == "voice design"
    assert status["progress"] == {"step": 1, "total": 3, "message": "Designing the angry preset"}
    assert status["result"] is None and status["error"] is None


def test_status_shows_the_result_once_a_job_succeeds(client, start_job):
    job_id = start_job("voice design", lambda report: {"voice": "Gravel"}).json()["job_id"]

    status = wait_until_finished(client, job_id)

    assert status["state"] == "succeeded"
    assert status["result"] == {"voice": "Gravel"}
    assert status["error"] is None


def test_the_result_endpoint_waits_for_the_job(client, start_job):
    work, started, release = held_open()
    job_id = start_job("voice design", work).json()["job_id"]
    assert started.wait(timeout=5)

    while_running = client.get(f"/jobs/{job_id}/result")
    release.set()
    wait_until_finished(client, job_id)
    when_done = client.get(f"/jobs/{job_id}/result")

    assert while_running.status_code == 409
    assert "still running" in while_running.json()["detail"]
    assert when_done.status_code == 200
    assert when_done.json() == {"done": True}


def test_a_second_job_gets_409_while_one_runs(client, start_job):
    work, started, release = held_open()
    first = start_job("voice design", work).json()["job_id"]
    assert started.wait(timeout=5)

    second = start_job("generation", lambda report: None)
    release.set()

    assert second.status_code == 409
    assert "voice design job is already running" in second.json()["detail"]
    assert second.json()["running_job_id"] == first


def test_a_new_job_can_start_once_the_last_one_finished(client, start_job):
    first = start_job("voice design", lambda report: 1).json()["job_id"]
    wait_until_finished(client, first)

    second = start_job("generation", lambda report: 2)

    assert second.status_code == 200
    assert wait_until_finished(client, second.json()["job_id"])["result"] == 2


def test_a_new_job_can_start_once_the_last_one_failed(client, start_job):
    def fail(report):
        raise RuntimeError("boom")

    first = start_job("voice design", fail).json()["job_id"]
    wait_until_finished(client, first)

    assert start_job("generation", lambda report: 2).status_code == 200


def test_an_unknown_job_is_404(client):
    assert client.get("/jobs/nope").status_code == 404
    assert client.get("/jobs/nope/result").status_code == 404


def use_speech(models):
    def work(report):
        with models.speech() as speech:
            return len(speech.speak("Hello.", Path("neutral.wav"), 0.5, 0.5))

    return work


def test_a_model_that_fails_to_load_ends_the_job_with_a_readable_error(
    client, start_job, fakes, models
):
    fakes.fail_to_load["speech"] = load_error("speech model", "the weights are missing")

    job_id = start_job("generation", use_speech(models)).json()["job_id"]
    status = wait_until_finished(client, job_id)

    assert status["state"] == "failed"
    assert status["error"] == (
        "The generation job stopped: couldn't load the speech model: the weights are missing."
    )
    assert client.get("/").status_code == 200, "the app stays up"


def test_a_loader_crashing_its_own_way_is_reported_as_a_load_failure(
    client, start_job, fakes, models
):
    fakes.fail_to_load["speech"] = FileNotFoundError("no such file: model.safetensors")

    job_id = start_job("generation", use_speech(models)).json()["job_id"]
    status = wait_until_finished(client, job_id)

    assert "couldn't load the speech model: no such file: model.safetensors" in status["error"]


@pytest.mark.parametrize(
    "error", [OutOfMemory("[METAL] Insufficient Memory"), MemoryError()], ids=["engine", "python"]
)
def test_running_out_of_memory_ends_the_job_with_a_readable_error(
    client, start_job, fakes, models, error
):
    fakes.fail_to_run["speech"] = error

    job_id = start_job("generation", use_speech(models)).json()["job_id"]
    status = wait_until_finished(client, job_id)

    assert status["state"] == "failed"
    assert (
        status["error"] == "The generation job ran out of memory. Close other apps, then try again."
    )
    assert client.get("/").status_code == 200, "the app stays up"


def test_an_unexpected_failure_ends_the_job_with_its_message(client, start_job):
    def fail(report):
        raise ValueError("the description is empty")

    status = wait_until_finished(client, start_job("voice design", fail).json()["job_id"])

    assert status["error"] == "The voice design job failed: the description is empty."
    assert client.get(f"/jobs/{status['id']}/result").status_code == 409


def test_voice_design_borrows_the_memory_and_the_speech_model_comes_back(
    client, start_job, fakes, models
):
    models.preload_speech()

    def design(report):
        with models.voice_design() as engine:
            engine.design("A gravelly older man.", "Hello.", emotion="angry")

    wait_until_finished(client, start_job("voice design", design).json()["job_id"])

    assert fakes.events == [
        "load speech",
        "close speech",
        "load voice design",
        "close voice design",
        "load speech",
    ]
    assert fakes.most_loaded_at_once == 1
    assert fakes.loaded == {"speech"}, "the speech model is ready for the next Script"


def test_the_speech_model_comes_back_even_if_voice_design_fails_to_load(
    client, start_job, fakes, models
):
    fakes.fail_to_load["voice design"] = load_error("voice design model")

    def design(report):
        with models.speech():
            pass
        with models.voice_design() as engine:
            engine.design("A gravelly older man.", "Hello.")

    status = wait_until_finished(client, start_job("voice design", design).json()["job_id"])

    assert "couldn't load the voice design model" in status["error"]
    assert fakes.events == ["load speech", "close speech", "load speech"]


def test_a_model_used_twice_in_a_row_loads_once(client, start_job, fakes, models):
    def design_two(report):
        with models.voice_design() as engine:
            engine.design("A gravelly older man.", "One.")
        with models.voice_design() as engine:
            engine.design("A gravelly older man.", "Two.")

    wait_until_finished(client, start_job("voice design", design_two).json()["job_id"])

    assert fakes.events == ["load voice design"]


def test_each_fake_clip_is_a_distinct_standard_wav(client, start_job, fakes, models):
    def speak_twice(report):
        with models.speech() as speech:
            speech.speak("One.", Path("neutral.wav"), 0.5, 0.5)
            speech.speak("Two.", Path("angry.wav"), 0.7, 0.3)

    wait_until_finished(client, start_job("generation", speak_twice).json()["job_id"])

    first, second = (call.wav for call in fakes.calls)
    assert first != second
    for clip in (first, second):
        with wave.open(io.BytesIO(clip)) as wav:
            assert (wav.getnchannels(), wav.getsampwidth()) == (1, 2)
    assert fakes.calls[1].inputs["reference_clip"] == Path("angry.wav")


def test_v1_supports_no_vocal_effects():
    vocal_effects = default_engines().vocal_effects

    assert vocal_effects.supported_effects == frozenset()
    with pytest.raises(UnsupportedVocalEffect, match=r"\(laugh\) is skipped"):
        vocal_effects.render("laugh", Path("neutral.wav"))


def test_without_real_engines_a_job_needing_a_model_fails_readably(write_config):
    with TestClient(create_app(write_config(), default_engines())) as client:
        models = client.app.state.models
        job = client.app.state.jobs.start("generation", use_speech(models))
        status = wait_until_finished(client, job.id)

    assert status["error"] == (
        "The generation job stopped: couldn't load the speech model: "
        "it isn't part of this version of Voicewright yet."
    )
