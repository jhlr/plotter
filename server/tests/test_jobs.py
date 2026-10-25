import threading
import time

import pytest

from penarm.arm import Arm
from penarm.config import ArmConfig
from penarm.errors import Busy, Cancelled
from penarm.jobs import JobRunner
from penarm.link import SimLink


def test_job_runs_to_done_with_progress() -> None:
    runner = JobRunner()
    job = runner.submit("t", lambda cancel, progress: progress(3, 3))
    assert runner.wait(job, 2.0) and job.status == "done" and job.summary()["progress"] == "3/3"


def test_second_job_is_refused_while_busy_and_stop_cancels() -> None:
    runner = JobRunner()
    started = threading.Event()

    def forever(cancel, progress):  # type: ignore[no-untyped-def]
        started.set()
        while not cancel():
            time.sleep(0.005)
        raise Cancelled()

    job = runner.submit("long", forever)
    assert started.wait(2.0)
    with pytest.raises(Busy, match=job.id):
        runner.submit("other", lambda c, p: None)
    runner.stop()
    assert job.status == "cancelled"
    assert runner.wait(runner.submit("again", lambda c, p: None), 2.0)  # free again after the stop


def test_errors_are_reported_not_raised() -> None:
    runner = JobRunner()

    def boom(cancel, progress):  # type: ignore[no-untyped-def]
        raise TimeoutError("board gone")

    job = runner.submit("bad", boom)
    runner.wait(job, 2.0)
    assert job.status == "error" and "board gone" in str(job.summary()["error"])


def test_arm_stops_within_a_waypoint_when_cancelled() -> None:
    link = SimLink()
    arm = Arm(ArmConfig(), link)
    calls = {"n": 0}

    def cancel_after_30() -> bool:
        calls["n"] += 1
        return calls["n"] > 30

    c = arm.canvas
    stroke = [(5.0, c.h / 2), (c.w - 5.0, c.h / 2)]
    before = len(link.history)
    with pytest.raises(Cancelled):
        arm.draw_strokes([stroke], should_cancel=cancel_after_30)
    assert 25 <= len(link.history) - before <= 31  # halted early, nowhere near the full stroke


def test_arm_resyncs_after_a_board_reset() -> None:
    link = SimLink()
    arm = Arm(ArmConfig(), link)
    link.pos = (120.0, 40.0)  # the board came back in another pose
    link.resets += 1
    arm.draw_strokes([[(5.0, 5.0)]])
    assert arm.pos is not None
