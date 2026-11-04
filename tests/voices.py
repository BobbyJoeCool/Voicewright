"""Shared steps for the Voice tests: start a job through the API and wait for it."""

import time

import pytest

DESCRIPTION = "A gravelly older man with a slow, calm, warm voice."


def wait_until_finished(client, job_id: str, timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"/jobs/{job_id}").json()
        if status["state"] != "running":
            return status
        time.sleep(0.02)
    pytest.fail(f"job {job_id} never finished")


def run_job(client, path: str, body: dict | None = None) -> dict:
    """POST to a route that starts a job, wait for it, and return its final status."""
    started = client.post(path, json=body)
    assert started.status_code == 202, started.text
    return wait_until_finished(client, started.json()["job_id"])


def succeeded(status: dict) -> dict:
    assert status["state"] == "succeeded", status["error"]
    return status["result"]


def design(client, description: str = DESCRIPTION) -> dict:
    """Design a Draft voice and wait for the job; return the job's final status."""
    return run_job(client, "/voices/design", {"description": description})


def get_draft(client, draft_id: str) -> dict:
    response = client.get(f"/voices/drafts/{draft_id}")
    assert response.status_code == 200, response.text
    return response.json()


def designed_draft(client, description: str = DESCRIPTION) -> dict:
    return get_draft(client, succeeded(design(client, description))["draft_id"])
