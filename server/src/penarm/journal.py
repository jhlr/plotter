"""What the arm was drawing and how far it got, kept on disk so an interrupted drawing can be resumed after the host
process died (the board forgets its queue on every reset, the host's memory dies with the process)."""
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .shapes import Stroke

SAVE_EVERY_S = 0.5


@dataclass(frozen=True)
class Entry:
    strokes: list[Stroke]
    orientation: str
    progress: int  # waypoints of the drawing (not counting the approach to its start) the arm had reached


class Journal:
    """path=None keeps it in memory only (simulator, tests)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._mem: dict[str, object] | None = None
        self._saved_at = 0.0

    def begin(self, strokes: list[Stroke], orientation: str) -> None:
        self._write({"strokes": strokes, "orientation": orientation, "progress": 0})

    def update(self, progress: int, force: bool = False) -> None:
        data = self._read()
        if data is None or (not force and time.monotonic() - self._saved_at < SAVE_EVERY_S):
            return
        data["progress"] = progress
        self._write(data)

    def finish(self) -> None:
        """The drawing is complete: nothing left to resume."""
        self._mem = None
        if self.path is not None:
            self.path.unlink(missing_ok=True)

    def load(self) -> Entry | None:
        data = self._read()
        if data is None:
            return None
        strokes = [[(float(x), float(y)) for x, y in s] for s in data["strokes"]]  # type: ignore[attr-defined]
        return Entry(strokes, str(data["orientation"]), int(data["progress"]))  # type: ignore[call-overload]

    def _read(self) -> dict[str, object] | None:
        if self.path is None:
            return self._mem
        try:
            loaded: dict[str, object] = json.loads(self.path.read_text())
            return loaded
        except (OSError, ValueError):
            return None

    def _write(self, data: dict[str, object]) -> None:
        self._saved_at = time.monotonic()
        if self.path is None:
            self._mem = data
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        os.replace(tmp, self.path)  # atomic: a crash mid-write never leaves half a journal
