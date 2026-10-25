"""Owner of the draw cycle: canvas path -> Cartesian interpolation -> IK -> link. Everything else is a primitive."""
from collections.abc import Callable

from .canvas import Canvas, portrait_canvas, safe_canvas
from .config import ArmConfig
from .errors import Cancelled, Unreachable
from .kinematics import fk, interpolate, joints_to_servos, page_to_servos, servos_to_joints
from .link import Link
from .shapes import Stroke


class Arm:
    """Drawing coordinates are CANVAS mm (origin bottom-left of the reachable canvas); page mm stay internal."""

    def __init__(self, cfg: ArmConfig, link: Link) -> None:
        self.link = link
        self.pos: tuple[float, float] | None = None  # last commanded position, PAGE mm
        self.set_config(cfg)
        self._generation = getattr(link, "resets", 0)
        self._resync()

    def _resync(self) -> None:
        """(Re)send the speed and take the tip from the board's real pose, so the next stroke starts from where the
        arm is: after boot, and after the board resets under us (brown-out, cable bump)."""
        self.link.set_speed(self.cfg.speed_dps)
        self.link.set_idle_release(self.cfg.idle_release_s)
        self.pos = None
        try:  # first stroke starts from the boot pose in a straight line, not a joint-space swing off the page
            home = self.tip_fk()
            page_to_servos(self.cfg, *home)
            self.pos = home
        except Unreachable:
            pass

    def set_config(self, cfg: ArmConfig) -> None:
        """Swap geometry/calibration (e.g. after a fit) and recompute the canvas."""
        self.cfg = cfg
        self.orientation = getattr(self, "orientation", "landscape")
        if self.orientation.startswith("portrait"):
            side = self.orientation.removeprefix("portrait").lstrip("_") or None
            self.canvas: Canvas = portrait_canvas(cfg, side=side)
        else:
            self.canvas = safe_canvas(cfg)

    def set_orientation(self, orientation: str) -> None:
        """'landscape' = the wide band (default); 'portrait' = tall rectangle; '_left'/'_right' pick a side area."""
        if orientation not in ("landscape", "portrait", "portrait_left", "portrait_right"):
            raise ValueError("orientation must be 'landscape', 'portrait', 'portrait_left' or 'portrait_right'")
        self.orientation = orientation
        self.set_config(self.cfg)

    def _page_point(self, x: float, y: float) -> tuple[float, float]:
        if not self.canvas.contains(x, y):
            raise Unreachable(
                f"({x:.1f},{y:.1f}) outside the canvas ({self.canvas.w:.0f} x {self.canvas.h:.0f} mm, origin bottom-left)"
            )
        return self.canvas.to_page(x, y)

    def plan(self, strokes: list[Stroke]) -> list[Stroke]:
        """Canvas strokes -> page strokes, every point and every interpolated step validated (travel from the current
        position included). Raises before anything moves."""
        if not strokes or any(not s for s in strokes):
            raise ValueError("empty path")
        pages = [[self._page_point(*p) for p in s] for s in strokes]
        prev = self.pos
        for s in pages:
            for p in s:
                for q in interpolate(prev or p, p, self.cfg.seg_mm):
                    page_to_servos(self.cfg, *q)
                prev = p
        return pages

    def _servo_waypoints(self, pages: list[Stroke]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        prev = self.pos
        for stroke in pages:
            for p in stroke:
                out += [page_to_servos(self.cfg, *q) for q in interpolate(prev or p, p, self.cfg.seg_mm)]
                prev = p
        return out

    def _pos_from_board(self) -> None:
        """After a cancel or a failure the arm is wherever the board says: take it from there, not from the plan."""
        try:
            self.pos = self.tip_fk()
            page_to_servos(self.cfg, *self.pos)
        except (Unreachable, TimeoutError, RuntimeError, ValueError):
            self.pos = None

    def draw_strokes(
        self, strokes: list[Stroke], should_cancel: Callable[[], bool] | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """Draw canvas strokes in order. The waypoints go to the board's execution queue (see Link.run_path), so the
        arm keeps moving even if the host link hiccups. With no pen-up the tip travels between strokes touching the paper."""
        pages = self.plan(strokes)
        if getattr(self.link, "resets", 0) != self._generation:
            self._generation = getattr(self.link, "resets", 0)
            self._resync()
            pages = self.plan(strokes)  # the start pose changed: re-validate the travel
        waypoints = self._servo_waypoints(pages)
        try:
            self.link.run_path(waypoints, should_cancel, progress)
        except BaseException:
            self._pos_from_board()
            raise
        self.pos = pages[-1][-1]

    def move_to(self, x: float, y: float) -> None:
        self.draw_strokes([[(x, y)]])

    def draw_polyline(self, points: list[tuple[float, float]]) -> None:
        self.draw_strokes([points])

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
