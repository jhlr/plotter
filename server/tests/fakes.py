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
        self.next_seq, self.executed = 0, 0

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
            _, seq, a, b = cmd.split()
            if int(seq) == (self.next_seq - 1) & 0xFFFF:  # resend of the last accepted one
                self._say(f"OK {self.queue_size - len(self.queue)}")
            elif int(seq) != self.next_seq:
                self._say(f"ERR seq {self.next_seq}")
            elif len(self.queue) >= self.queue_size:
                self._say("FULL")
            else:
                self.queue.append((float(a), float(b)))
                self.accepted.append((float(a), float(b)))
                self.next_seq = (self.next_seq + 1) & 0xFFFF
                self._say(f"OK {self.queue_size - len(self.queue)}")
        elif cmd == "S":
            for _ in range(min(self.exec_per_status, len(self.queue))):
                self.s = self.queue.pop(0)
                self.executed = (self.executed + 1) & 0xFFFF
            self._say(f"S {self.next_seq} {self.executed} {len(self.queue)} {self.queue_size - len(self.queue)} 0")
        elif cmd == "X":
            self.queue.clear()
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
