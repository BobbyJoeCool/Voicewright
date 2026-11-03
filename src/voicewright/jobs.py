"""The job runner: runs long operations one at a time in the background.

Voice design, preset generation, and Script generation each take minutes and need a large
model, so only one runs at a time. The page starts one, then polls its status for progress
and the result or error.
"""

import enum
import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from voicewright.engines import ModelLoadError, OutOfMemory

log = logging.getLogger(__name__)

# Finished jobs kept for the page to read back; older ones are forgotten.
FINISHED_JOBS_KEPT = 50


class JobState(enum.StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class Progress:
    """How far a job has got, e.g. step 3 of 7, "Rendering Segment 3"."""

    step: int = 0
    total: int | None = None
    message: str = "Starting"


@dataclass
class Job:
    id: str
    kind: str
    state: JobState = JobState.RUNNING
    progress: Progress = field(default_factory=Progress)
    result: Any = None
    error: str | None = None


class JobAlreadyRunning(Exception):
    """A job was started while another is still running."""

    def __init__(self, running: Job):
        super().__init__(f"a {running.kind} job is already running")
        self.running = running


# What a job does: given a way to report progress, return a JSON-ready result.
Work = Callable[[Callable[[int, int | None, str], None]], Any]


class JobRunner:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._running: Job | None = None

    def start(self, kind: str, work: Work) -> Job:
        """Start `work` in the background. Raises JobAlreadyRunning if a job is running."""
        with self._lock:
            if self._running is not None:
                raise JobAlreadyRunning(self._running)
            job = Job(id=uuid.uuid4().hex, kind=kind)
            self._jobs[job.id] = job
            self._running = job
            self._forget_old_jobs()
        # A daemon thread, so Ctrl-C doesn't wait minutes for a model to finish.
        threading.Thread(target=self._run, args=(job, work), daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def _run(self, job: Job, work: Work) -> None:
        def report(step: int, total: int | None, message: str) -> None:
            job.progress = Progress(step, total, message)

        try:
            result = work(report)
        except BaseException as error:  # noqa: BLE001 - every failure ends the job, not the app
            self._finish(job, error=failure_message(job, error))
        else:
            self._finish(job, result=result)

    def _finish(self, job: Job, result: Any = None, error: str | None = None) -> None:
        with self._lock:
            job.result, job.error = result, error
            # State last: a reader that sees "succeeded" or "failed" also sees the result or error.
            job.state = JobState.FAILED if error is not None else JobState.SUCCEEDED
            self._running = None

    def _forget_old_jobs(self) -> None:
        finished = [j for j in self._jobs.values() if j.state is not JobState.RUNNING]
        for old in finished[: max(0, len(finished) - FINISHED_JOBS_KEPT)]:
            del self._jobs[old.id]


def failure_message(job: Job, error: BaseException) -> str:
    """What to tell the user about a failed job, in one plain sentence."""
    if isinstance(error, ModelLoadError):
        return f"The {job.kind} job stopped: {error}."
    if isinstance(error, OutOfMemory | MemoryError):
        return f"The {job.kind} job ran out of memory. Close other apps, then try again."
    log.error("the %s job failed", job.kind, exc_info=error)
    return f"The {job.kind} job failed: {error or type(error).__name__}."
