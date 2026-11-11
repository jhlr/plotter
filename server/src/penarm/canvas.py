"""The drawing canvas: the largest axis-aligned rectangle the arm can fully reach, in its own mm frame."""
import math
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


def safe_canvas(cfg: ArmConfig, step: float = 2.0) -> Canvas:
    """The canvas set by cfg.canvas_*_mm edges, after checking that every point of the rectangle is reachable."""
    x0, y0, x1, y1 = cfg.canvas_left_mm, cfg.canvas_bottom_mm, cfg.canvas_right_mm, cfg.canvas_top_mm
    if not (0.0 <= x0 < x1 <= cfg.page_w and 0.0 <= y0 < y1 <= cfg.page_h):
        raise Unreachable(f"canvas edges x {x0:g}..{x1:g}, y {y0:g}..{y1:g} are not inside the {cfg.page_w:g} x {cfg.page_h:g} mm page")
    for i in range(math.ceil((x1 - x0) / step) + 1):
        for j in range(math.ceil((y1 - y0) / step) + 1):
            x, y = min(x0 + i * step, x1), min(y0 + j * step, y1)
            try:
                page_to_servos(cfg, x, y)
            except Unreachable:
                raise Unreachable(
                    f"the canvas point ({x:.0f},{y:.0f}) mm is not reachable: move the canvas edges (canvas_left/bottom/right/top_mm "
                    "in calibration.json) or check the angles. The elbow always bends to the board's left (joint 2 < 0): if the "
                    "horn is mounted for the right side, remount it and redo the angles (skill calibrate-angles)."
                ) from None
    return Canvas(x0, y0, x1 - x0, y1 - y0)
