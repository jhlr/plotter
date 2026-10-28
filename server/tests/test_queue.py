import os
from collections.abc import Callable

import pytest

from penarm.arm import Arm
from penarm.config import ArmConfig
from penarm.errors import Cancelled
from penarm.journal import Journal
from penarm.link import SerialLink, Waypoint
from penarm.shapes import rect_points
from tests.fakes import FakeBoard


def _link(board: FakeBoard, name: str, retries: int = 8) -> SerialLink:
    return SerialLink(f"/dev/fake-{os.getpid()}-q-{name}", opener=lambda p, b: board, boot_wait=0.0,
                      time_scale=0.01, retries=retries)


def _points(n: int) -> list[Waypoint]:
    return [Waypoint(60.0 + i * 0.1, 100.0 - i * 0.1, 20) for i in range(n)]


def test_waypoints_are_streamed_through_a_small_queue_in_order() -> None:
    board = FakeBoard(queue_size=16)
    link = _link(board, "order")
    try:
        pts = _points(300)
        done: list[int] = []
        link.run_path(pts, progress=lambda d, t: done.append(d))
        assert board.accepted == [(round(a, 2), round(b, 2)) for a, b, _ in pts]
        assert board.accepted_ms == [20] * 300
        assert board.s == board.accepted[-1] and done[-1] == 300
        assert link.target == (pts[-1].a, pts[-1].b)
    finally:
        link.close()


def test_lost_replies_never_duplicate_or_drop_a_waypoint() -> None:
    board = FakeBoard(drop=0.35, queue_size=16, seed=7)
    link = _link(board, "drop", retries=12)
    try:
        pts = _points(200)
        link.run_path(pts)
        assert board.accepted == [(round(a, 2), round(b, 2)) for a, b, _ in pts]  # exactly once, in order
        assert board.executed == 200
    finally:
        link.close()


def test_cancel_clears_the_boards_queue() -> None:
    board = FakeBoard(queue_size=16)
    link = _link(board, "cancel")
    calls = {"n": 0}

    def cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 5

    try:
        with pytest.raises(Cancelled):
            link.run_path(_points(500), should_cancel=cancel)
        assert board.queue == [] and board.executed < 500
    finally:
        link.close()


def test_a_board_restart_mid_drawing_is_reported_not_papered_over() -> None:
    board = FakeBoard(queue_size=16)
    link = _link(board, "reset")
    calls = {"n": 0}

    def progress(done: int, total: int) -> None:
        calls["n"] += 1
        if calls["n"] == 3:
            board.reset("zz")

    try:
        with pytest.raises(RuntimeError, match="lost its queue"):
            link.run_path(_points(300), progress=progress)
    finally:
        link.close()


def test_arm_draws_a_rectangle_through_the_queue_and_ends_where_planned() -> None:
    board = FakeBoard(queue_size=32)
    link = _link(board, "arm")
    try:
        arm = Arm(ArmConfig(), link)
        c = arm.canvas
        arm.draw_strokes([rect_points(10.0, 10.0, min(40.0, c.w - 20), min(15.0, c.h - 20))])
        assert len(board.accepted) > 80
        assert arm.pos is not None and arm.canvas.from_page(*arm.pos) == pytest.approx((10.0, 10.0), abs=1e-6)
    finally:
        link.close()


def test_cancelled_drawing_takes_the_position_from_the_board() -> None:
    board = FakeBoard(queue_size=16)
    link = _link(board, "armcancel")
    try:
        arm = Arm(ArmConfig(), link)
        n = {"i": 0}

        def cancel() -> bool:
            n["i"] += 1
            return n["i"] > 3

        c = arm.canvas
        with pytest.raises(Cancelled):
            arm.draw_strokes([[(5.0, 5.0), (c.w - 5.0, 5.0)]], should_cancel=cancel)
        assert arm.pos is not None and arm.pos != arm.canvas.to_page(c.w - 5.0, 5.0)
    finally:
        link.close()


def test_waypoints_are_timed_for_a_steady_tip_speed_with_soft_ends() -> None:
    board = FakeBoard(queue_size=32)
    link = _link(board, "feed")
    try:
        cfg = ArmConfig()
        arm = Arm(cfg, link)
        c = arm.canvas
        arm.draw_strokes([[(10.0, 10.0), (min(150.0, c.w - 10), 10.0)]])
        steady = round(cfg.seg_mm / cfg.feed_mm_s * 1000)
        ms = board.accepted_ms
        assert ms[len(ms) // 2] == steady
        assert ms[-1] > steady  # braking into the end of the stroke
    finally:
        link.close()


def _cancel_once_drawing(journal: Journal) -> Callable[[], bool]:
    """Cancels once the arm has got past the approach and drawn a little of the figure."""
    return lambda: (e := journal.load()) is not None and e.progress >= 20


def test_an_interrupted_drawing_resumes_where_the_arm_stands_not_from_its_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("penarm.journal.SAVE_EVERY_S", 0.0)
    board = FakeBoard(queue_size=16)
    link = _link(board, "resume")
    try:
        journal = Journal()
        arm = Arm(ArmConfig(), link, journal)
        c = arm.canvas
        rect = [rect_points(10.0, 10.0, min(60.0, c.w - 20), min(30.0, c.h - 20))]
        with pytest.raises(Cancelled):
            arm.draw_strokes(rect, should_cancel=_cancel_once_drawing(journal))
        stopped_at = board.s
        before = len(board.accepted)

        arm2 = Arm(ArmConfig(), link, journal)  # a new process: only the journal and the board's pose survive
        arm2.draw_strokes(rect, resume=True)
        resumed = board.accepted[before:]
        assert max(abs(resumed[0][0] - stopped_at[0]), abs(resumed[0][1] - stopped_at[1])) < 3.0
        assert len(resumed) < before + 150  # not a whole second lap
        assert journal.load() is None  # finished: nothing left to resume
    finally:
        link.close()


def test_resume_refuses_when_the_arm_is_not_on_the_drawing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("penarm.journal.SAVE_EVERY_S", 0.0)
    board = FakeBoard(queue_size=16)
    link = _link(board, "offpath")
    try:
        journal = Journal()
        arm = Arm(ArmConfig(), link, journal)
        c = arm.canvas
        rect = [rect_points(10.0, 10.0, min(60.0, c.w - 20), min(30.0, c.h - 20))]
        with pytest.raises(Cancelled):
            arm.draw_strokes(rect, should_cancel=_cancel_once_drawing(journal))
        board.s = (170.0, 170.0)  # somebody moved the arm
        with pytest.raises(ValueError, match="not on the interrupted drawing"):
            Arm(ArmConfig(), link, journal).draw_strokes(rect, resume=True)
    finally:
        link.close()


def test_one_wrong_status_reply_is_not_mistaken_for_a_board_restart() -> None:
    board = FakeBoard(queue_size=16)
    link = _link(board, "garble")
    calls = {"n": 0}

    def progress(done: int, total: int) -> None:
        calls["n"] += 1
        if calls["n"] == 3:
            board.garble_status = True  # one S reply with a bad sequence number

    try:
        link.run_path(_points(200), progress=progress)
        assert board.executed == 200
    finally:
        link.close()
