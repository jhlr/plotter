import os

import pytest

from penarm.arm import Arm
from penarm.config import ArmConfig
from penarm.errors import Unreachable
from penarm.kinematics import page_to_servos
from penarm.link import SerialLink
from penarm.program import MAX_DELTA, decode, encode
from penarm.shapes import rect_points
from tests.fakes import FakeBoard


def _link(board: FakeBoard, name: str) -> SerialLink:
    return SerialLink(f"/dev/fake-{os.getpid()}-p-{name}", opener=lambda p, b: board, boot_wait=0.0, time_scale=0.01)


def test_encode_decode_tracks_the_quantised_position_without_drift() -> None:
    pts = [(90.0 + 0.037 * i, 60.0 - 0.021 * i) for i in range(400)]
    start, steps = encode(pts)
    back = decode(start, steps)
    assert abs(back[-1][0] - pts[-1][0]) <= 0.05 and abs(back[-1][1] - pts[-1][1]) <= 0.05  # error never accumulates
    assert all(abs(da) <= MAX_DELTA and abs(db) <= MAX_DELTA for da, db in steps)


def test_a_jump_larger_than_one_byte_is_split_and_still_arrives() -> None:
    start, steps = encode([(10.0, 10.0), (170.0, 150.0)])
    assert len(steps) >= 2 and all(abs(x) <= MAX_DELTA for s in steps for x in s)
    assert decode(start, steps)[-1] == pytest.approx((170.0, 150.0), abs=0.05)


def test_steps_that_do_not_move_the_arm_are_dropped() -> None:
    _, steps = encode([(50.0, 50.0), (50.0, 50.0), (50.01, 50.0), (51.0, 50.0)])
    assert steps == [(10, 0)]


def test_store_then_run_reaches_the_drawings_last_point() -> None:
    board = FakeBoard()
    link = _link(board, "store")
    try:
        pts = [(60.0 + 0.5 * i, 100.0 - 0.3 * i) for i in range(100)]
        n = link.store_program(pts)
        assert board.prog is not None and len(board.prog[2]) == n
        assert link.run_program(1) == n and board.playing
        assert board.s == pytest.approx(pts[-1], abs=0.05)
    finally:
        link.close()


def test_a_drawing_larger_than_the_board_is_refused_before_anything_is_written() -> None:
    board = FakeBoard()
    board.prog_max = 10
    link = _link(board, "big")
    try:
        with pytest.raises(ValueError, match="keeps 10"):
            link.store_program([(60.0 + i, 100.0) for i in range(50)])
        assert not any(c.startswith("PB") for c in board.commands)
    finally:
        link.close()


def test_a_half_written_drawing_is_not_playable() -> None:
    board = FakeBoard()
    link = _link(board, "half")
    try:
        link._cmd("PB 900 900 3")
        link._cmd("PD 0 5 5")
        with pytest.raises(RuntimeError, match="incomplete"):
            link._cmd("PE")
        with pytest.raises(RuntimeError, match="noprog"):
            link.run_program(1)
    finally:
        link.close()


def test_arm_stores_a_drawing_with_the_coarsest_step_that_fits() -> None:
    board = FakeBoard()
    board.prog_max = 60
    link = _link(board, "arm")
    try:
        arm = Arm(ArmConfig(), link)
        info = arm.store_strokes([rect_points(10.0, 10.0, 30.0, 20.0)])
        assert int(str(info["steps"])) <= 60 and float(str(info["step_mm"])) >= 1.0 and board.prog is not None
        with pytest.raises(Unreachable, match="too long"):
            board.prog_max = 5
            arm.store_strokes([rect_points(10.0, 10.0, 30.0, 20.0)])
    finally:
        link.close()


def test_a_stored_drawing_starts_at_its_own_first_point_not_where_the_arm_was() -> None:
    board = FakeBoard()
    link = _link(board, "start")
    try:
        arm = Arm(ArmConfig(), link)
        c = arm.canvas
        arm.draw_strokes([[(5.0, 5.0), (20.0, 5.0)]])  # the arm now rests away from the drawing below
        first = (c.w / 2, c.h / 2)
        arm.store_strokes([[first, (first[0] + 20.0, first[1]), (first[0] + 20.0, first[1] + 10.0)]])
        assert board.prog is not None
        a, b = page_to_servos(arm.cfg, *c.to_page(*first))
        assert (board.prog[0], board.prog[1]) == (round(a * 10), round(b * 10))  # every lap returns here
    finally:
        link.close()
