"""calibration.json: per-arm parameters (offsets, base, link lengths, paper size, the correction mesh) kept out of the
code. Edit it by hand, or let `penarm-inkcal measure --update-mesh` write the mesh. Also the pixel -> mm homography."""
import json
import os
from dataclasses import asdict
from pathlib import Path

from .config import ArmConfig
from .mesh import CorrectionMesh

SAVED_FIELDS = ("offset1", "offset2", "base_x", "base_y", "l1", "l2", "page_w", "page_h", "sign1", "sign2", "canvas_left_mm", "canvas_bottom_mm", "canvas_right_mm", "canvas_top_mm")


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(m[r][i]))
        m[i], m[p] = m[p], m[i]
        if abs(m[i][i]) < 1e-12:
            raise ValueError("the four points are degenerate (collinear?)")
        for r in range(i + 1, n):
            f = m[r][i] / m[i][i]
            m[r] = [x - f * y for x, y in zip(m[r], m[i])]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


def homography(src: list[tuple[float, float]], dst: list[tuple[float, float]]) -> list[list[float]]:
    """3x3 projective map taking the 4 src points to the 4 dst points (h33 = 1)."""
    if len(src) != 4 or len(dst) != 4:
        raise ValueError("a homography needs exactly 4 point pairs")
    a: list[list[float]] = []
    b: list[float] = []
    for (x, y), (u, v) in zip(src, dst):
        a += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        b += [u, v]
    h = _solve(a, b)
    return [h[0:3], h[3:6], [h[6], h[7], 1.0]]


def apply_homography(h: list[list[float]], p: tuple[float, float]) -> tuple[float, float]:
    w = h[2][0] * p[0] + h[2][1] * p[1] + h[2][2]
    return (h[0][0] * p[0] + h[0][1] * p[1] + h[0][2]) / w, (h[1][0] * p[0] + h[1][1] * p[1] + h[1][2]) / w


class CalibrationStore:
    """Reads calibration.json (path: PENARM_CALIBRATION, default ./calibration.json): `params` override ArmConfig
    fields, `mesh` is the measured position-error correction."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(os.environ.get("PENARM_CALIBRATION", "calibration.json"))
        self.params: dict[str, float] = {}
        self.mesh: CorrectionMesh | None = None
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self.params = {k: float(v) for k, v in data.get("params", {}).items() if k in SAVED_FIELDS}
            self.mesh = CorrectionMesh.from_json(data["mesh"]) if data.get("mesh") else None

    def apply(self, cfg: ArmConfig) -> ArmConfig:
        return ArmConfig(**{**asdict(cfg), **self.params})

    def save(self) -> None:
        data: dict[str, object] = {"params": self.params}
        if self.mesh:
            data["mesh"] = self.mesh.to_json()
        self.path.write_text(json.dumps(data, indent=2))
