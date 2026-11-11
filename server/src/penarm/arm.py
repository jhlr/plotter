"""Owner of the draw cycle: canvas path -> Cartesian interpolation -> IK -> link. Everything else is a primitive."""
from collections.abc import Callable

from .canvas import Canvas, safe_canvas
from .config import ArmConfig
from .errors import Unreachable
from .kinematics import fk, interpolate, joints_to_servos, page_to_servos, servos_to_joints
from .link import Link, Waypoint
from .profile import step_times
from .shapes import Stroke

XY = tuple[float, float]


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
        self.canvas: Canvas = safe_canvas(cfg)

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

    def _samples(self, pages: list[Stroke], start: XY | None) -> list[XY]:
        """Cartesian samples (page mm) along the strokes, at most seg_mm apart, after travelling from `start`."""
        out: list[XY] = []
        prev = start
        for stroke in pages:
            for p in stroke:
                out += interpolate(prev or p, p, self.cfg.seg_mm)
                prev = p
        return out

    def _timed(self, origin: XY, samples: list[XY]) -> list[Waypoint]:
        """Servo targets for the samples, each timed by the speed profile (soft start/stop, braking at corners)."""
        times = step_times([origin, *samples], self.cfg.feed_mm_s, self.cfg.accel_mm_s2, self.cfg.corner_mm_s)
        return [Waypoint(*page_to_servos(self.cfg, *q), ms=t) for q, t in zip(samples, times, strict=True)]

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
        first = pages[0][0]
        samples = self._samples(pages, first)  # the drawing itself, from its own first point
        body = self._timed(first, samples)
        origin = self.pos or first
        # Get from where the arm is to the drawing's first point, then draw it.
        lead = self._timed(origin, interpolate(origin, samples[0], self.cfg.seg_mm))
        try:
            self.link.run_path(lead + body, should_cancel, progress)
        except BaseException:
            self._pos_from_board()
            raise
        self.pos = pages[-1][-1]

    def stop(self) -> None:
        """Halt the arm where it is."""
        self.link.abort()
        self._pos_from_board()

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
