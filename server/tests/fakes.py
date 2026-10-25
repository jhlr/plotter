"""A fake board speaking the penarm line protocol over a pyserial-like object, with lossy replies and resets."""
import collections
import random
import time


class FakeBoard:
    def __init__(self, drop: float = 0.0, seed: int = 1, boot_id: str = "a1") -> None:
        self.rng = random.Random(seed)
        self.drop, self.boot_id = drop, boot_id
        self.s = (90.0, 90.0)
        self.mute = False
        self.out: collections.deque[bytes] = collections.deque()
        self.buf = b""
        self.closed = False
        self.commands: list[str] = []

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
        self.out.clear()

    def close(self) -> None:
        self.closed = True
