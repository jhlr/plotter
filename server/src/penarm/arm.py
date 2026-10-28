"""Owner of the draw cycle: canvas path -> Cartesian interpolation -> IK -> link. Everything else is a primitive."""
import math
from collections.abc import Callable

from .canvas import Canvas, portrait_canvas, safe_canvas
from .config import ArmConfig
from .errors import Cancelled, Unreachable
from .journal import Journal
from .mesh import CorrectionMesh
from .kinematics import fk, interpolate, joints_to_servos, page_to_servos, servos_to_joints
from .link import Link, Waypoint
from .profile import step_times
from .program import encode
from .shapes import Stroke

MAX_STORE_SEG_MM = 6.0
RESUME_TOLERANCE_DEG = 3.0
XY = tuple[float, float]


class Arm:
    """Drawing coordinates are CANVAS mm (origin bottom-left of the reachable canvas); page mm stay internal."""

    def __init__(
        self, cfg: ArmConfig, link: Link, journal: Journal | None = None, mesh: CorrectionMesh | None = None
    ) -> None:
        self.link = link
        self.journal = journal or Journal()
        self.mesh = mesh  # residual position error measured from a drawn rectangle: aim against it
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
            self.canvas: Canvas = portrait_canvas(cfg, side=side, mesh=self.mesh)
        else:
            self.canvas = safe_canvas(cfg, mesh=self.mesh)

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
                    page_to_servos(self.cfg, *self._aim(q))
                prev = p
        return pages

    def _aim(self, q: XY) -> XY:
        """Where to point the arm so the pen lands on page point q (the model's target shifted against the mesh error)."""
        return self.mesh.corrected(*q) if self.mesh else q

    def _samples(self, pages: list[Stroke], start: XY | None, seg_mm: float | None = None) -> list[XY]:
        """Cartesian samples (page mm) along the strokes, at most seg_mm apart, after travelling from `start`."""
        out: list[XY] = []
        prev = start
        for stroke in pages:
            for p in stroke:
                out += interpolate(prev or p, p, seg_mm or self.cfg.seg_mm)
                prev = p
        return out

    def _timed(self, origin: XY, samples: list[XY]) -> list[Waypoint]:
        """Servo targets for the samples, each timed by the speed profile (soft start/stop, braking at corners)."""
        times = step_times([origin, *samples], self.cfg.feed_mm_s, self.cfg.accel_mm_s2, self.cfg.corner_mm_s)
        return [Waypoint(*page_to_servos(self.cfg, *self._aim(q)), ms=t) for q, t in zip(samples, times, strict=True)]

    def _pos_from_board(self) -> None:
        """After a cancel or a failure the arm is wherever the board says: take it from there, not from the plan."""
        try:
            self.pos = self.tip_fk()
            page_to_servos(self.cfg, *self.pos)
        except (Unreachable, TimeoutError, RuntimeError, ValueError):
            self.pos = None

    def draw_strokes(
        self, strokes: list[Stroke], should_cancel: Callable[[], bool] | None = None,
        progress: Callable[[int, int], None] | None = None, resume: bool = False,
    ) -> None:
        """Draw canvas strokes in order. The waypoints go to the board's execution queue (see Link.run_path), so the
        arm keeps moving even if the host link hiccups. With no pen-up the tip travels between strokes touching the paper.
        resume=True continues a drawing that was interrupted: instead of going back to its start, the arm carries on from
        where it stands, found on the drawing's path (see _resume_from)."""
        pages = self.plan(strokes)
        if getattr(self.link, "resets", 0) != self._generation:
            self._generation = getattr(self.link, "resets", 0)
            self._resync()
            pages = self.plan(strokes)  # the start pose changed: re-validate the travel
        first = pages[0][0]
        samples = self._samples(pages, first)  # the drawing itself, from its own first point
        body = self._timed(first, samples)
        if resume:
            done = self._resume_from(body)
            origin = self.tip_fk()
        else:
            done = 0
            origin = self.pos or first
            self.journal.begin(strokes, self.orientation)
        # Get from where the arm is to the point the drawing continues from (its start, or where it was interrupted).
        lead = self._timed(origin, interpolate(origin, samples[done], self.cfg.seg_mm))
        waypoints = lead + body[done:]

        def track(executed: int, total: int) -> None:
            self.journal.update(done + max(0, executed - len(lead)))
            if progress:
                progress(executed, total)

        try:
            self.link.run_path(waypoints, should_cancel, track)
        except BaseException:
            self._pos_from_board()
            raise
        self.journal.finish()
        self.pos = pages[-1][-1]

    def _resume_from(self, body: list[Waypoint]) -> int:
        """Index in `body` of the point the arm is at (the board's real pose, which survives a host crash). Only the
        stretch around the journal's last progress is searched: a closed drawing passes its start again at the end."""
        entry = self.journal.load()
        if entry is None:
            raise ValueError("nothing to resume: no interrupted drawing")
        if entry.progress == 0:  # interrupted while still travelling to the start: nothing drawn, go on from here
            return 0
        _, _, s1, s2 = self.link.read()
        lo, hi = max(0, entry.progress - 20), min(len(body), entry.progress + 200)  # the board ran ahead of the journal
        k = min(range(lo, hi), key=lambda i: max(abs(body[i].a - s1), abs(body[i].b - s2)), default=None)
        if k is None or max(abs(body[k].a - s1), abs(body[k].b - s2)) > RESUME_TOLERANCE_DEG:
            raise ValueError("the arm is not on the interrupted drawing's path (it was moved): draw again from the start")
        return k

    def store_strokes(self, strokes: list[Stroke]) -> dict[str, object]:
        """Same plan as draw_strokes, but written into the board's EEPROM instead of played: it starts only with
        run_stored and keeps going if the host disconnects. The board's few hundred steps are spent by coarsening the
        Cartesian step (1 mm up to MAX_STORE_SEG_MM): straight lines lose nothing, curves only get fewer chords."""
        pages = self.plan(strokes)
        cap = self.link.program_capacity()
        if not cap:
            raise RuntimeError("this board cannot store a drawing (Uno firmware with the program commands needed)")
        needed = 0
        seg = self.cfg.seg_mm
        while seg <= MAX_STORE_SEG_MM:
            # The program starts at the drawing's own first point, not at wherever the arm is now: every lap goes back
            # to the start of the program, and that must be the start of the drawing.
            points = [page_to_servos(self.cfg, *self._aim(q)) for q in self._samples(pages, pages[0][0], seg)]
            needed = len(encode(points)[1])
            if needed <= cap:
                steps = self.link.store_program(points, step_ms=round(seg / self.cfg.feed_mm_s * 1000))
                self.pos = None  # the arm is where it was; the board moves it to the start of the drawing when it runs
                return {"steps": steps, "capacity": cap, "step_mm": seg}
            seg += 1.0
        raise Unreachable(f"too long for the board: {needed} steps at {MAX_STORE_SEG_MM:.0f} mm, it keeps {cap}")

    def run_stored(self, loops: int = 1) -> int:
        """Start the stored drawing. The board plays it on its own, so the host may disconnect."""
        self.pos = None
        return self.link.run_program(loops)

    def stop(self) -> None:
        """Stop a stored drawing (the arm holds where it is)."""
        self.link.abort()
        self._pos_from_board()

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
