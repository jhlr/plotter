"""Transports to the ESP32: real serial and an in-memory simulator."""
import time
from typing import Protocol

import serial


class Link(Protocol):
    def move(self, s1: float, s2: float) -> None: ...
    def set_speed(self, dps: float) -> None: ...
    def read(self) -> tuple[int, int, float, float]: ...


class SerialLink:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 15.0, boot_wait: float = 2.0) -> None:
        self.ser = serial.Serial(port, baud, timeout=timeout)
        time.sleep(boot_wait)  # opening the port resets an Uno (DTR); commands sent during the bootloader are lost
        self.ser.reset_input_buffer()

    def _cmd(self, text: str) -> str:
        self.ser.write((text + "\n").encode())
        while True:
            reply = self.ser.readline().decode().strip()
            if not reply:
                raise TimeoutError(f"no reply to {text!r}")
            if reply.startswith(("OK", "ERR", "R ")):
                break
        if reply.startswith("ERR"):
            raise RuntimeError(f"{text!r}: {reply}")
        return reply

    def move(self, s1: float, s2: float) -> None:
        self._cmd(f"A {s1:.2f} {s2:.2f}")

    def set_speed(self, dps: float) -> None:
        self._cmd(f"V {dps:.1f}")

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
