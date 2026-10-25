"""Transports to the board: real serial (with port lock, retries, reset detection) and an in-memory simulator."""
import os
import re
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO, Protocol

from .errors import Cancelled

import serial

try:
    import fcntl
except ImportError:  # Windows: no advisory file locks
    fcntl = None  # type: ignore[assignment]


class Link(Protocol):
    resets: int  # incremented whenever the board is seen to have restarted

    def move(self, s1: float, s2: float) -> None: ...
    def set_speed(self, dps: float) -> None: ...
    def read(self) -> tuple[int, int, float, float]: ...
    def set_idle_release(self, seconds: float) -> None: ...
    def run_path(
        self, points: list[tuple[float, float]], should_cancel: Callable[[], bool] | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> None: ...


_LOST_QUEUE = "the board lost its queue (it restarted?): the arm may be anywhere, check get_state and redraw"


class SerialLike(Protocol):
    """The slice of pyserial's Serial that SerialLink uses (so tests can inject a fake board)."""

    def write(self, data: bytes) -> int | None: ...
    def readline(self) -> bytes: ...
    def reset_input_buffer(self) -> None: ...
    def close(self) -> None: ...


def _acquire_port_lock(port: str) -> IO[str] | None:
    """One penarm server per serial port: two processes on the same port interleave bytes and move the arm at random."""
    if fcntl is None:
        return None
    path = Path(tempfile.gettempdir()) / f"penarm-{re.sub(r'[^A-Za-z0-9_.-]', '_', Path(port).name)}.lock"
    fh = path.open("a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.seek(0)
        owner = fh.read().strip() or "unknown"
        fh.close()
        raise RuntimeError(f"{port} is already in use by another penarm server (pid {owner}): stop it first") from None
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def _open_serial(port: str, baud: int) -> SerialLike:
    # The Windows CH340 driver (3.9) fails SetCommState ("device not functioning") when the port is
    # configured at the baud it already has, e.g. reopening at the last session's baud. Open at a different
    # baud and switch. Any later reconfigure fails the same way, so the port settings (timeout included)
    # must not be touched after this.
    detour = 9600 if baud != 9600 else 19200
    ser = serial.Serial(port, detour, timeout=0.1)
    ser.baudrate = baud
    return ser


class SerialLink:
    def __init__(
        self, port: str, baud: int = 57600, retries: int = 3, opener: Callable[[str, int], SerialLike] | None = None,
        boot_wait: float = 2.0, time_scale: float = 1.0,
    ) -> None:
        self.port, self.baud, self.retries = port, baud, retries
        self._opener = opener or _open_serial
        self._boot_wait, self._scale = boot_wait, time_scale  # time_scale < 1 only speeds up tests
        self._lock = _acquire_port_lock(port)
        self.dps = 60.0  # firmware default until set_speed
        self.target: tuple[float, float] | None = None  # last acknowledged servo target
        self.resets = 0
        self.boot_id: str | None = None
        self._suspect = False  # a command needed a retry: re-check the boot id afterwards
        self.ser = self._opener(port, baud)
        self._settle()

    def close(self) -> None:
        self.ser.close()
        if self._lock is not None:
            self._lock.close()
            self._lock = None

    def _settle(self) -> None:
        time.sleep(self._boot_wait * self._scale)  # opening the port resets the Uno (DTR); the bootloader eats bytes
        self.ser.reset_input_buffer()
        self._probe()

    def _probe(self) -> None:
        """Ask the firmware for its boot id; a different id than before means the board restarted."""
        try:
            reply = self._cmd("?", retry_probe=False, reconnect=False)  # no reconnect: _settle() calls us
        except (TimeoutError, RuntimeError):
            return  # older firmware or a dead board: the next real command will say
        m = re.search(r"boot=(\w+)", reply)
        if not m:
            return
        if self.boot_id is not None and m.group(1) != self.boot_id:
            self.resets += 1
            self.target = None
        self.boot_id = m.group(1)

    def _reconnect(self) -> None:
        try:
            self.ser.close()
        except Exception:  # the port may already be gone
            pass
        self.ser = self._opener(self.port, self.baud)
        self._settle()

    def _reply(self, wait: float) -> str | None:
        """Next protocol line (OK/ERR/R) within `wait` s; other or mangled lines are skipped."""
        deadline = time.monotonic() + wait * self._scale
        buf = b""
        while time.monotonic() < deadline:
            buf += self.ser.readline()  # partial line on the short port timeout, keep accumulating
            if buf.endswith(b"\n"):
                line, buf = buf.decode(errors="replace").strip(), b""
                if line.startswith(("OK", "ERR", "R ", "S ", "FULL")):
                    return line
        return None

    def _try(self, text: str, wait: float) -> str | None:
        for attempt in range(self.retries):
            self.ser.write((text + "\n").encode())
            reply = self._reply(wait)
            if reply is not None:
                if attempt:
                    self._suspect = True
                return reply
            self._suspect = True
            self.ser.write(b"\n")  # terminate any half-received line on the board, then drop its ERR
            time.sleep(0.1 * self._scale)
            self.ser.reset_input_buffer()
        return None

    def _cmd(self, text: str, wait: float = 2.0, retry_probe: bool = True, reconnect: bool = True) -> str:
        """Send a command and return its reply. Every command is idempotent (absolute targets), so a byte lost on
        the wire costs one short timeout and a resend; if resends fail the port is reopened once."""
        reply = self._try(text, wait)
        if reply is None and reconnect:
            self._reconnect()
            reply = self._try(text, wait)
        if reply is None:
            raise TimeoutError(f"no reply to {text!r} after {self.retries} tries" + (" and a reconnect" if reconnect else ""))
        if reply.startswith("ERR"):
            raise RuntimeError(f"{text!r}: {reply}")
        if self._suspect and retry_probe:
            self._suspect = False
            self._probe()
        return reply

    def move(self, s1: float, s2: float) -> None:
        # "OK" only comes on arrival: wait for the ramp (unknown start = worst case) plus a margin
        travel = max(abs(s1 - self.target[0]), abs(s2 - self.target[1])) if self.target else 180.0
        self._cmd(f"A {s1:.2f} {s2:.2f}", wait=travel / self.dps + 1.0)
        self.target = (s1, s2)

    def set_speed(self, dps: float) -> None:
        self._cmd(f"V {dps:.1f}")
        self.dps = dps

    def read(self) -> tuple[int, int, float, float]:
        _, a, b, c, d = self._cmd("R").split()
        return int(a), int(b), float(c), float(d)

    def _status(self) -> tuple[int, int, int, int, bool]:
        """(next_seq, executed, queued, free, moving) from the board's execution queue."""
        parts = self._cmd("S").split()
        return int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]), parts[5] == "1"

    def abort(self) -> None:
        """Clear the board's queue; it holds the pose it is in."""
        self._cmd("X")
        self.target = None

    def run_path(
        self, points: list[tuple[float, float]], should_cancel: Callable[[], bool] | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """Hand servo waypoints to the board's queue and stay ahead of it. The board keeps moving on its own: a slow or
        briefly lost link only risks the queue running dry, not the arm stalling at every millimetre. Waypoints carry
        sequence numbers, so a resend after a lost reply is never queued twice."""
        if not points:
            return
        seq, executed0, queued, free, _ = self._status()
        if queued:
            self.abort()
            seq, executed0, queued, free, _ = self._status()
        total, sent = len(points), 0
        while True:
            if should_cancel and should_cancel():
                self.abort()
                raise Cancelled()
            while sent < total and free > 0:
                a, b = points[sent]
                try:
                    reply = self._cmd(f"Q {seq} {a:.2f} {b:.2f}")
                except RuntimeError as exc:
                    if "ERR seq" in str(exc):  # its counter is not ours: it restarted and lost the queue
                        raise RuntimeError(_LOST_QUEUE) from exc
                    raise
                if reply.startswith("FULL"):
                    free = 0
                    break
                free = int(reply.split()[1])
                seq = (seq + 1) & 0xFFFF
                sent += 1
            nxt, executed, queued, free, moving = self._status()
            if nxt != seq:  # the board's counter is not where ours is: it restarted and lost the queue
                raise RuntimeError(_LOST_QUEUE)
            if progress:
                progress(min(total, (executed - executed0) & 0xFFFF), total)
            if sent == total and queued == 0 and not moving:
                break
            if free == 0 or sent == total:
                time.sleep(0.02 * self._scale)
        self.target = points[-1]

    def set_idle_release(self, seconds: float) -> None:
        """Ask the board to release the servos after `seconds` of silence (0 = never). Older firmware says ERR."""
        try:
            self._cmd(f"W {int(seconds)}")
        except RuntimeError:
            pass


class SimLink:
    """Records servo targets so tools run without hardware."""

    def __init__(self) -> None:
        self.pos = (90.0, 90.0)
        self.history: list[tuple[float, float]] = []
        self.resets = 0

    def move(self, s1: float, s2: float) -> None:
        self.pos = (s1, s2)
        self.history.append(self.pos)

    def set_speed(self, dps: float) -> None:
        pass

    def read(self) -> tuple[int, int, float, float]:
        return 0, 0, self.pos[0], self.pos[1]

    def set_idle_release(self, seconds: float) -> None:
        pass

    def run_path(
        self, points: list[tuple[float, float]], should_cancel: Callable[[], bool] | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        for i, (a, b) in enumerate(points, 1):
            if should_cancel and should_cancel():
                raise Cancelled()
            self.move(a, b)
            if progress:
                progress(i, len(points))
