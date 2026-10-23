"""The drawing canvas: the largest axis-aligned rectangle the arm can fully reach, in its own mm frame."""
from dataclasses import dataclass

from .config import ArmConfig
from .errors import Unreachable
from .kinematics import page_to_servos


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


def _reachable(cfg: ArmConfig, x: float, y: float) -> bool:
    try:
        page_to_servos(cfg, x, y)
    except Unreachable:
        return False
    return True


def safe_canvas(cfg: ArmConfig, step: float = 2.0, margin: float = 3.0) -> Canvas:
    """Largest-area rectangle whose grid points are all reachable, shrunk by `margin` mm on every side."""
    cols, rows = int(cfg.page_w / step) + 1, int(cfg.page_h / step) + 1
    ok = [[_reachable(cfg, c * step, r * step) for c in range(cols)] for r in range(rows)]
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
