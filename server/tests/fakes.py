"""A fake board speaking the penarm line protocol over a pyserial-like object, with lossy replies and resets."""
import collections
import random
import time


class FakeBoard:
    def __init__(self, drop: float = 0.0, seed: int = 1, boot_id: str = "a1", queue_size: int = 16,
                 exec_per_status: int = 4) -> None:
        self.rng = random.Random(seed)
        self.drop, self.boot_id = drop, boot_id
        self.s = (90.0, 90.0)
        self.mute = False
        self.out: collections.deque[bytes] = collections.deque()
        self.buf = b""
        self.closed = False
        self.commands: list[str] = []
        # execution queue, like the firmware's: waypoints are consumed a few per status poll
        self.queue_size, self.exec_per_status = queue_size, exec_per_status
        self.queue: list[tuple[float, float]] = []
        self.accepted: list[tuple[float, float]] = []  # every waypoint ever queued (duplicates would show here)
        self.accepted_ms: list[int] = []
        self.accepted_ms_pending = 0
        self.prog_ms = 0
        self.garble_status = False  # the next S reply carries a wrong sequence number (a digit lost on the wire)
        self.next_seq, self.executed = 0, 0
        # EEPROM drawing, like the firmware's: committed only by PE
        self.prog_max = 492
        self.prog: tuple[int, int, list[tuple[int, int]]] | None = None  # committed (startA, startB, steps)
        self.prog_wip: list[tuple[int, int]] | None = None
        self.prog_declared = 0
        self.prog_start = (0, 0)
        self.playing = False
        self.loops = 0

    def write(self, data: bytes) -> int:
        self.buf += data
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            if line.strip():
                self._handle(line.decode().strip())
        return len(data)

    def _say(self, text: str) -> None:
        if not self.mute and self.rng.random() >= self.drop:
            self.out.append((text + "\n").encode())

    def _handle(self, cmd: str) -> None:
        self.commands.append(cmd)
        if cmd == "?":
            self._say(f"OK penarm 1 adcmax=1023 boot={self.boot_id}")
        elif cmd.startswith(("V ", "W ")):
            self._say("OK")
        elif cmd.startswith("A "):
            _, a, b = cmd.split()
            self.s = (float(a), float(b))
            self._say("OK")
        elif cmd.startswith("Q "):
            seq, a, b, *rest = cmd.split()[1:]
            self.accepted_ms_pending = int(rest[0]) if rest else 0
            if int(seq) == (self.next_seq - 1) & 0xFFFF:  # resend of the last accepted one
                self._say(f"OK {self.queue_size - len(self.queue)}")
            elif int(seq) != self.next_seq:
                self._say(f"ERR seq {self.next_seq}")
            elif len(self.queue) >= self.queue_size:
                self._say("FULL")
            else:
                self.queue.append((float(a), float(b)))
                self.accepted.append((float(a), float(b)))
                self.accepted_ms.append(self.accepted_ms_pending)
                self.next_seq = (self.next_seq + 1) & 0xFFFF
                self._say(f"OK {self.queue_size - len(self.queue)}")
        elif cmd == "PI":
            count, sa, sb = (len(self.prog[2]), self.prog[0], self.prog[1]) if self.prog else (0, 0, 0)
            self._say(f"P {count} {sa} {sb} {self.prog_max} {self.prog_ms}")
        elif cmd.startswith("PB "):
            a, b, n, *rest = cmd.split()[1:]
            self.prog_ms = int(rest[0]) if rest else 0
            if int(n) > self.prog_max:
                self._say(f"ERR size {self.prog_max}")
            else:
                self.prog = None  # invalid until PE
                self.prog_wip, self.prog_declared, self.prog_start = [], int(n), (int(a), int(b))
                self._say(f"OK {self.prog_max}")
        elif cmd.startswith("PD "):
            parts = [int(x) for x in cmd.split()[1:]]
            idx, nums = parts[0], parts[1:]
            if self.prog_wip is None or idx > len(self.prog_wip):
                self._say(f"ERR idx {len(self.prog_wip or [])}")
            else:
                pairs = list(zip(nums[0::2], nums[1::2], strict=True))
                self.prog_wip[idx : idx + len(pairs)] = pairs
                self._say(f"OK {len(self.prog_wip)}")
        elif cmd == "PE":
            if self.prog_wip is None and self.prog:
                self._say(f"OK {len(self.prog[2])}")
            elif self.prog_wip is None or len(self.prog_wip) != self.prog_declared:
                self._say(f"ERR incomplete {len(self.prog_wip or [])}")
            else:
                self.prog = (*self.prog_start, self.prog_wip)
                self.prog_wip = None
                self._say(f"OK {len(self.prog[2])}")
        elif cmd.startswith("G"):
            if not self.prog:
                self._say("ERR noprog")
            else:
                pa, pb, steps = self.prog
                self.playing, self.loops = True, int(cmd.split()[1]) if " " in cmd else 1
                for da, db in steps:
                    pa, pb = pa + da, pb + db
                self.s = (pa / 10.0, pb / 10.0)  # the played drawing ends at its last point
                self._say(f"OK {len(steps)}")
        elif cmd == "S":
            garbled, self.garble_status = self.garble_status, False
            for _ in range(min(self.exec_per_status, len(self.queue))):
                self.s = self.queue.pop(0)
                self.executed = (self.executed + 1) & 0xFFFF
            self._say(f"S {self.next_seq + 100 if garbled else self.next_seq} {self.executed} {len(self.queue)} {self.queue_size - len(self.queue)} 0")
        elif cmd == "X":
            self.queue.clear()
            self.playing = False
            self._say(f"OK {self.next_seq}")
        elif cmd == "R":
            self._say(f"R 0 0 {self.s[0]:.1f} {self.s[1]:.1f}")
        else:
            self._say("ERR unknown")

    def readline(self) -> bytes:
        if self.out:
            return self.out.popleft()
        time.sleep(0.0005)
        return b""

    def reset_input_buffer(self) -> None:
        self.out.clear()

    def reset(self, boot_id: str) -> None:
        """The board restarted: new boot id, servos back to the default pose."""
        self.boot_id, self.s = boot_id, (90.0, 90.0)
        self.queue.clear()
        self.next_seq, self.executed = 0, 0
        self.out.clear()

    def close(self) -> None:
        self.closed = True
