"""Owner of the draw cycle: canvas path -> Cartesian interpolation -> IK -> link. Everything else is a primitive."""
from .canvas import Canvas, safe_canvas
from .config import ArmConfig
from .errors import Unreachable
from .kinematics import fk, interpolate, joints_to_servos, page_to_servos, servos_to_joints
from .link import Link


class Arm:
    """Drawing coordinates are CANVAS mm (origin bottom-left of the reachable canvas); page mm stay internal."""

    def __init__(self, cfg: ArmConfig, link: Link) -> None:
        self.link = link
        self.pos: tuple[float, float] | None = None  # last commanded position, PAGE mm
        self.set_config(cfg)
        link.set_speed(cfg.speed_dps)
        try:  # first stroke starts from the boot pose in a straight line, not a joint-space swing off the page
            home = self.tip_fk()
            page_to_servos(cfg, *home)
            self.pos = home
        except Unreachable:
            pass

    def set_config(self, cfg: ArmConfig) -> None:
        """Swap geometry/calibration (e.g. after a fit) and recompute the canvas."""
        self.cfg = cfg
        self.canvas: Canvas = safe_canvas(cfg)

    def _page_point(self, x: float, y: float) -> tuple[float, float]:
        if not self.canvas.contains(x, y):
            raise Unreachable(
                f"({x:.1f},{y:.1f}) outside the canvas ({self.canvas.w:.0f} x {self.canvas.h:.0f} mm, origin bottom-left)"
            )
        return self.canvas.to_page(x, y)

    def _line_servos(self, target: tuple[float, float]) -> list[tuple[float, float]]:
        pts = interpolate(self.pos, target, self.cfg.seg_mm) if self.pos else [target]
        return [page_to_servos(self.cfg, px, py) for px, py in pts]

    def move_to(self, x: float, y: float) -> None:
        """Straight line from the current position to canvas (x, y); validated fully before moving."""
        target = self._page_point(x, y)
        servos = self._line_servos(target)  # raises before any motion
        for s1, s2 in servos:
            self.link.move(s1, s2)
        self.pos = target

    def draw_polyline(self, points: list[tuple[float, float]]) -> None:
        if not points:
            raise ValueError("empty path")
        pages = [self._page_point(*p) for p in points]  # whole path validated up front: no half-drawn strokes
        start = self.pos
        for a, b in zip([start or pages[0], *pages], pages):
            for px, py in interpolate(a, b, self.cfg.seg_mm):
                page_to_servos(self.cfg, px, py)
        for x, y in points:
            self.move_to(x, y)

    def goto_servos(self, s1: float, s2: float) -> None:
        """Raw servo move (calibration). Limits enforced; not interpolated, so keep the pen clear of anything."""
        joints_to_servos(self.cfg, *servos_to_joints(self.cfg, s1, s2))  # range check
        self.link.move(s1, s2)
        self.pos = None  # unknown to the Cartesian planner until the next explicit move

    def tip_fk(self) -> tuple[float, float]:
        """Tip position (page mm) from the servo angles the firmware reports (kinematic estimate)."""
        _, _, s1, s2 = self.link.read()
        return fk(self.cfg, *servos_to_joints(self.cfg, s1, s2))

    def state(self) -> dict[str, object]:
        adc1, adc2, s1, s2 = self.link.read()
        tip = fk(self.cfg, *servos_to_joints(self.cfg, s1, s2))
        return {"servo_deg": (s1, s2), "pot_raw": (adc1, adc2), "tip_page_mm": tip,
                "tip_canvas_mm": self.canvas.from_page(*tip),
                "last_commanded_canvas_mm": self.canvas.from_page(*self.pos) if self.pos else None}


__all__ = ["Arm", "Unreachable"]
