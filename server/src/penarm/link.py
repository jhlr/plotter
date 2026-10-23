"""Transports to the ESP32: real serial and an in-memory simulator."""
import time
from typing import Protocol

import serial


class Link(Protocol):
    def move(self, s1: float, s2: float) -> None: ...
    def set_speed(self, dps: float) -> None: ...
    def read(self) -> tuple[int, int, float, float]: ...


class SerialLink:
    def __init__(self, port: str, baud: int = 57600, retries: int = 3) -> None:
        self.ser = self._open(port, baud)
        self.retries = retries
        self.dps = 60.0  # firmware default until set_speed
        self.target: tuple[float, float] | None = None  # last acknowledged servo target
        time.sleep(2.0)  # opening the port resets the Uno (DTR); commands sent during the bootloader are lost
        self.ser.reset_input_buffer()

    @staticmethod
    def _open(port: str, baud: int) -> serial.Serial:
        # The Windows CH340 driver (3.9) fails SetCommState ("device not functioning") when the port is
        # configured at the baud it already has, e.g. reopening at the last session's baud. Open at a different
        # baud and switch. Any later reconfigure fails the same way, so the port settings (timeout included)
        # must not be touched after this.
        detour = 9600 if baud != 9600 else 19200
        ser = serial.Serial(port, detour, timeout=0.1)
        ser.baudrate = baud
        return ser

    def _reply(self, wait: float) -> str | None:
        """Next protocol line (OK/ERR/R) within `wait` s; other or mangled lines are skipped."""
        deadline = time.monotonic() + wait
        buf = b""
        while time.monotonic() < deadline:
            buf += self.ser.readline()  # partial line on the short port timeout, keep accumulating
            if buf.endswith(b"\n"):
                line, buf = buf.decode(errors="replace").strip(), b""
                if line.startswith(("OK", "ERR", "R ")):
                    return line
        return None

    def _cmd(self, text: str, wait: float = 2.0) -> str:
        """Send a command and return its reply. Every command is idempotent (absolute targets), so a byte
        lost on the wire (no reply, or a mangled one that gets skipped) costs one short timeout and a resend."""
        for _ in range(self.retries):
            self.ser.write((text + "\n").encode())
            reply = self._reply(wait)
            if reply is not None:
                if reply.startswith("ERR"):
                    raise RuntimeError(f"{text!r}: {reply}")
                return reply
            self.ser.write(b"\n")  # terminate any half-received line on the board, then drop its ERR
            time.sleep(0.1)
            self.ser.reset_input_buffer()
        raise TimeoutError(f"no reply to {text!r} after {self.retries} tries")

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


class SimLink:
    """Records servo targets so tools run without hardware."""

    def __init__(self) -> None:
        self.pos = (90.0, 90.0)
        self.history: list[tuple[float, float]] = []

    def move(self, s1: float, s2: float) -> None:
        self.pos = (s1, s2)
        self.history.append(self.pos)

    def set_speed(self, dps: float) -> None:
        pass

    def read(self) -> tuple[int, int, float, float]:
        return 0, 0, self.pos[0], self.pos[1]
