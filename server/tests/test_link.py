import os

import pytest

from penarm.link import SerialLink
from tests.fakes import FakeBoard


def _link(board: FakeBoard, port: str, **kw: object) -> SerialLink:
    return SerialLink(port, opener=lambda p, b: board, boot_wait=0.0, time_scale=0.01, **kw)  # type: ignore[arg-type]


def _port(name: str) -> str:
    return f"/dev/fake-{os.getpid()}-{name}"


def test_moves_survive_40_percent_lost_replies() -> None:
    board = FakeBoard(drop=0.4)
    link = _link(board, _port("drop"), retries=8)
    try:
        for i in range(40):
            link.move(60.0 + i, 100.0 - i)
        assert board.s == (99.0, 61.0)
        assert link.read()[2:] == (99.0, 61.0)
    finally:
        link.close()


def test_reset_is_detected_from_the_boot_id() -> None:
    board = FakeBoard()
    link = _link(board, _port("reset"))
    try:
        link.move(120.0, 40.0)
        assert link.resets == 0 and link.boot_id == "a1"
        board.reset("b2")
        link._probe()
        assert link.resets == 1 and link.boot_id == "b2" and link.target is None
    finally:
        link.close()


def test_reconnects_when_the_board_goes_silent() -> None:
    board = FakeBoard()
    opens: list[int] = []

    def opener(port: str, baud: int) -> FakeBoard:
        opens.append(1)
        board.mute = False  # reopening wakes it up
        return board

    link = SerialLink(_port("silent"), opener=opener, boot_wait=0.0, time_scale=0.01)
    try:
        board.mute = True
        link.move(70.0, 70.0)
        assert len(opens) == 2 and board.s == (70.0, 70.0)
    finally:
        link.close()


def test_gives_up_when_the_board_never_answers() -> None:
    board = FakeBoard()
    link = _link(board, _port("dead"))
    try:
        board.mute = True
        board.mute = True
        link._opener = lambda p, b: board  # reopening does not help
        with pytest.raises(TimeoutError):
            link.move(70.0, 70.0)
    finally:
        link.close()


def test_second_server_on_the_same_port_is_refused() -> None:
    port = _port("lock")
    first = _link(FakeBoard(), port)
    try:
        with pytest.raises(RuntimeError, match="already in use"):
            _link(FakeBoard(), port)
    finally:
        first.close()
    _link(FakeBoard(), port).close()  # released after close


def test_idle_release_is_sent_and_tolerated_on_old_firmware() -> None:
    board = FakeBoard()
    link = _link(board, _port("idle"))
    try:
        link.set_idle_release(90)
        assert "W 90" in board.commands
        board._handle = lambda cmd: board._say("ERR unknown")  # type: ignore[method-assign]
        link.set_idle_release(90)  # must not raise
    finally:
        link.close()
