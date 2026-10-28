"""The drawing canvas: the largest axis-aligned rectangle the arm can fully reach, in its own mm frame."""
from dataclasses import dataclass

from .config import ArmConfig
from .errors import Unreachable
from .kinematics import page_to_servos
from .mesh import CorrectionMesh


@dataclass(frozen=True)
class Canvas:
    """x0/y0 = canvas bottom-left in page mm; w/h = size in mm. The LLM draws in canvas coordinates."""

    x0: float
    y0: float
    w: float
    h: float

    def to_page(self, x: float, y: float) -> tuple[float, float]:
        return self.x0 + x, self.y0 + y

    def from_page(self, x: float, y: float) -> tuple[float, float]:
        return x - self.x0, y - self.y0

    def contains(self, x: float, y: float, eps: float = 1e-6) -> bool:
        return -eps <= x <= self.w + eps and -eps <= y <= self.h + eps


def _reachable(cfg: ArmConfig, x: float, y: float, mesh: CorrectionMesh | None = None) -> bool:
    m = cfg.edge_margin_mm
    if not (m <= x <= cfg.page_w - cfg.edge_margin_right_mm and m <= y <= cfg.page_h - m):
        return False
    try:
        page_to_servos(cfg, *(mesh.corrected(x, y) if mesh else (x, y)))  # the arm aims where the mesh says
    except Unreachable:
        return False
    return True


def _grid(cfg: ArmConfig, step: float, mesh: CorrectionMesh | None = None) -> list[list[bool]]:
    cols, rows = int(cfg.page_w / step) + 1, int(cfg.page_h / step) + 1
    return [[_reachable(cfg, c * step, r * step, mesh) for c in range(cols)] for r in range(rows)]


def portrait_canvas(
    cfg: ArmConfig, step: float = 2.0, margin: float = 3.0, aspect: float = 1.5, side: str | None = None,
    mesh: CorrectionMesh | None = None,
) -> Canvas:
    """Largest-area reachable rectangle at least `aspect` times taller than wide. side='left'/'right' keeps it in
    that fifth of the page (the arm's side 'wings', away from the central band)."""
    ok = _grid(cfg, step, mesh)
    rows, cols = len(ok), len(ok[0])
    best = (0, 0, 0, 0, 0)  # area, left col, bottom row, width cols, height rows
    for wc in range(3, cols):
        # run[r][c]: rows of consecutive reachable cells ending at r, across columns c..c+wc-1
        run = [0] * (cols - wc + 1)
        for r in range(rows):
            run = [run[c] + 1 if all(ok[r][c : c + wc]) else 0 for c in range(cols - wc + 1)]
            for c, hr in enumerate(run):
                x_mid = (c + wc / 2) * step
                if side == "left" and x_mid > cfg.page_w / 5 or side == "right" and x_mid < 4 * cfg.page_w / 5:
                    continue
                if hr >= aspect * wc and hr * wc > best[0]:
                    best = (hr * wc, c, r - hr + 1, wc, hr)
    _, left, bottom, wc, hr = best
    width_mm, height_mm = (wc - 1) * step - 2 * margin, (hr - 1) * step - 2 * margin
    if wc == 0 or width_mm <= 0 or height_mm <= 0:
        raise Unreachable("no portrait area is reachable: check calibration")
    return Canvas(left * step + margin, bottom * step + margin, width_mm, height_mm)


def safe_canvas(cfg: ArmConfig, step: float = 2.0, margin: float = 3.0, mesh: CorrectionMesh | None = None) -> Canvas:
    """Largest-area rectangle whose grid points are all reachable, shrunk by `margin` mm on every side."""
    ok = _grid(cfg, step, mesh)
    cols, rows = len(ok[0]), len(ok)
    heights = [0] * cols
    best = (0, 0, 0, 0, 0)  # area, left col, bottom row, width cols, height rows
    for r in range(rows):
        heights = [h + 1 if ok[r][c] else 0 for c, h in enumerate(heights)]
        stack: list[int] = []  # largest rectangle in histogram, columns with increasing heights
        for c in range(cols + 1):
            cur = heights[c] if c < cols else 0
            while stack and heights[stack[-1]] >= cur:
                h = heights[stack.pop()]
                left = stack[-1] + 1 if stack else 0
                width = c - left
                if h * width > best[0]:
                    best = (h * width, left, r - h + 1, width, h)
            stack.append(c)
    _, left, bottom, wc, hr = best
    if wc < 2 or hr < 2:
        raise Unreachable("no reachable area on the page: check calibration (offsets, base, signs)")
    width_mm, height_mm = (wc - 1) * step - 2 * margin, (hr - 1) * step - 2 * margin
    if width_mm <= 0 or height_mm <= 0:
        raise Unreachable("reachable area smaller than the safety margin: check calibration")
    return Canvas(left * step + margin, bottom * step + margin, width_mm, height_mm)
