"""One drawing job at a time on a worker thread: calls return fast, long strokes survive client timeouts,
and any job can be cancelled between waypoints."""
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from .errors import Busy, Cancelled

Work = Callable[[Callable[[], bool], Callable[[int, int], None]], None]  # (should_cancel, report_progress)


@dataclass
class Job:
    id: str
    label: str
    status: str = "running"  # running | done | cancelled | error
    error: str | None = None
    done: int = 0
    total: int = 0
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    _finished_evt: threading.Event = field(default_factory=threading.Event)

    def summary(self) -> dict[str, object]:
        end = self.finished or time.monotonic()
        out: dict[str, object] = {"job_id": self.id, "label": self.label, "status": self.status,
                                  "progress": f"{self.done}/{self.total}", "seconds": round(end - self.started, 1)}
        if self.error:
            out["error"] = self.error
        return out


class JobRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._current: Job | None = None

    def submit(self, label: str, work: Work) -> Job:
        with self._lock:
            if self._current is not None and self._current.status == "running":
                raise Busy(f"job {self._current.id} ({self._current.label}) is still running: wait for it or call stop()")
            job = Job(id=uuid.uuid4().hex[:8], label=label)
            self._jobs[job.id] = job
            self._current = job
        threading.Thread(target=self._run, args=(job, work), daemon=True).start()
        return job

    def _run(self, job: Job, work: Work) -> None:
        def progress(done: int, total: int) -> None:
            job.done, job.total = done, total

        try:
            work(job.cancel.is_set, progress)
            job.status = "done"
        except Cancelled:
            job.status = "cancelled"
        except Exception as exc:  # reported to the LLM through job_status
            job.status, job.error = "error", f"{type(exc).__name__}: {exc}"
        finally:
            job.finished = time.monotonic()
            job._finished_evt.set()

    def wait(self, job: Job, timeout: float) -> bool:
        return job._finished_evt.wait(timeout)

    def get(self, job_id: str | None = None) -> Job:
        with self._lock:
            job = self._jobs.get(job_id) if job_id else self._current
        if job is None:
            raise ValueError("no such job" if job_id else "no job has run yet")
        return job

    def stop(self) -> Job | None:
        with self._lock:
            job = self._current
        if job is not None and job.status == "running":
            job.cancel.set()
            job._finished_evt.wait(5.0)
        return job
