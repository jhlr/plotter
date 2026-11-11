"""calibration.json: per-arm parameters (offsets, gains, base, link lengths, canvas edges) kept out of the code.
`penarm-calibrate fit` writes them; you can also edit the file by hand. Only the fields in SAVED_FIELDS are read."""
import json
import os
from dataclasses import asdict
from pathlib import Path

from .config import ArmConfig

SAVED_FIELDS = ("offset1", "offset2", "base_x", "base_y", "l1", "l2", "page_w", "page_h", "sign1", "sign2",
                "canvas_left_mm", "canvas_bottom_mm", "canvas_right_mm", "canvas_top_mm")


class CalibrationStore:
    """Reads calibration.json (path: PENARM_CALIBRATION, default ~/.penarm/calibration.json: the same file whatever folder you run from): `params` override ArmConfig fields."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(os.environ.get("PENARM_CALIBRATION") or Path.home() / ".penarm" / "calibration.json")
        self.params: dict[str, float] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self.params = {k: float(v) for k, v in data.get("params", {}).items() if k in SAVED_FIELDS}

    def apply(self, cfg: ArmConfig) -> ArmConfig:
        return ArmConfig(**{**asdict(cfg), **self.params})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"params": self.params}, indent=2))
