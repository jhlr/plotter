"""The plotter, as one plain Python object. This is the ONE place that knows how to draw: the MCP server
(`server.py`) only exposes these methods to an LLM, and you can call the very same ones from a script:

    from penarm import Plotter

    p = Plotter()                      # no port = simulator; Plotter("/dev/cu.usbserial-10") = the real arm
    print(p.canvas_info())             # reachable area in mm, origin bottom-left, x right, y up
    p.draw_shape("heart", cx=80, cy=30, size=30, dry_run=True)   # preview only: nothing moves
    p.draw_shape("heart", cx=80, cy=30, size=30)                 # draw it

Every drawing method takes `dry_run=True` to get bbox, length, time, an ASCII thumbnail and an SVG without moving.
Coordinates are canvas mm. The pen has no lift: a drawing is one continuous trace."""
from collections.abc import Callable

from .arm import Arm
from .canvas import Canvas
from .calibration import CalibrationStore
from .config import DEFAULT
from .errors import Unreachable
from .jobs import JobRunner
from .link import Link, SerialLink, SimLink
from .preview import describe
from .shapes import (Stroke, arc_points, point, svg_to_strokes, bbox, bezier_points, ellipse_points, fit_strokes, heart_points, hatch_points,
                     polygon_points, rect_points, spiral_points, star_points, transform_strokes, wave_points)

XY = tuple[float, float]
Pt = list[float]  # a point as [x, y]: plain arrays keep every provider's function-calling schema valid

def _round(p: XY) -> XY:
    return round(p[0], 1), round(p[1], 1)


class Plotter:
    """`port=None` is the simulator. `wait_s` is how long a drawing call blocks before handing back a job id to poll
    (None = until it is done, the right choice for scripts; the MCP server uses a short wait so the LLM can poll)."""

    def __init__(self, port: str | None = None, wait_s: float | None = None) -> None:
        self.port = port or None
        self.link: Link = SerialLink(self.port) if self.port else SimLink()
        self.store = CalibrationStore()
        self.arm = Arm(self.store.apply(DEFAULT), self.link, self.store.mesh)
        self.jobs = JobRunner()
        self.wait_s = wait_s

    def close(self) -> None:
        if isinstance(self.link, SerialLink):
            self.link.close()

    def __enter__(self) -> "Plotter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ---- the canvas: every coordinate is canvas mm (origin bottom-left, x right, y up) ----

    def canvas_info(self) -> dict[str, object]:
        """START HERE. The drawing canvas: a rectangle the arm can fully reach, in mm, origin at its bottom-left corner,
        x right, y up. Every drawing tool takes coordinates in this frame; points outside are rejected. The pencil has
        no pen-up yet, so a drawing is one continuous trace (travel between strokes marks the paper)."""
        c = self.arm.canvas
        return {"width_mm": round(c.w, 1), "height_mm": round(c.h, 1), "pen_up": False, "calibrated": bool(self.store.mesh), "simulated": self.port is None, "busy": self.busy()}

    @property
    def canvas(self) -> Canvas:
        """The same canvas as canvas_info, as an object: `p.canvas.w`, `p.canvas.h` (mm)."""
        return self.arm.canvas

    def busy(self) -> bool:
        try:
            return self.jobs.get().status == "running"
        except ValueError:
            return False

    # ---- drawing: every method builds strokes and goes through _submit (validation, dry_run, jobs) ----

    def _submit(self, strokes: list[Stroke], label: str, dry_run: bool) -> dict[str, object]:
        x0, y0, x1, y1 = bbox(strokes)
        c = self.arm.canvas
        if not (c.contains(x0, y0) and c.contains(x1, y1)):
            raise Unreachable(
                f"the drawing's bounding box ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f}) mm does not fit the canvas "
                f"({c.w:.0f} x {c.h:.0f} mm, origin bottom-left): shrink it or move it"
            )
        self.arm.plan(strokes)  # raises Unreachable if a step along the way is not reachable; nothing has moved yet
        travel_from = c.from_page(*self.arm.pos) if self.arm.pos else None
        info = describe(strokes, c, travel_from)
        if dry_run:
            return {"dry_run": True, **info}
        return self._run_job(label, lambda cancel, progress: self.arm.draw_strokes(strokes, cancel, progress), info)

    def _run_job(
        self, label: str, work: Callable[[Callable[[], bool], Callable[[int, int], None]], None], info: dict[str, object]
    ) -> dict[str, object]:
        job = self.jobs.submit(label, work)
        self.jobs.wait(job, self.wait_s)
        summary: dict[str, object] = dict(job.summary())
        summary.update({k: info[k] for k in ("bbox_mm", "length_mm", "travel_marks_mm", "est_seconds") if k in info})
        if job.status == "running":
            summary["hint"] = "still drawing: poll job_status(job_id), or call stop() to cancel"
        return summary

    def draw_svg_path(
        self, d: str, x: float, y: float, width: float, height: float = 0.0, margin: float = 0.0, dry_run: bool = False
    ) -> dict[str, object]:
        """Draw an SVG path (the `d` attribute: M L H V C S Q T A Z, absolute or relative). Its bounding box is scaled
        to `width` mm (and `height` if > 0, otherwise keeping the aspect) and placed with the bottom-left corner at
        (x, y) on the canvas. SVG's y axis points down; it is flipped for you. Subpaths are joined by straight lines
        (no pen-up yet)."""
        flipped = [[(px, -py) for px, py in s] for s in svg_to_strokes(d, 1.0)]
        x0, y0, x1, y1 = bbox(flipped)
        h = height if height > 0 else max(width * (y1 - y0) / max(x1 - x0, 1e-9), 1.0)  # a flat path still gets a box
        strokes = fit_strokes(flipped, x, y, width, h, margin, keep_aspect=height <= 0)
        return self._submit(strokes, "draw_svg_path", dry_run)

    def draw_shape(
        self, kind: str, cx: float, cy: float, size: float, size2: float = 0.0, sides: int = 5, turns: float = 3.0,
        rotation_deg: float = 0.0, dry_run: bool = False,
    ) -> dict[str, object]:
        """Draw a named shape centered at (cx, cy). kind: circle (size = diameter), ellipse (size = width, size2 = height),
        rectangle (size = width, size2 = height), square (size = side), polygon (size = diameter, sides), triangle (size =
        diameter), star (size = outer diameter, sides = tips), spiral (size = outer diameter, turns), heart (size = width),
        hatch (size = width, size2 = height: back-and-forth fill), wave (size = length, size2 = amplitude, turns = cycles).
        size2 = 0 means "same as size" (or the default amplitude for wave).
        rotation_deg rotates it about its center (counter-clockwise)."""
        r = size / 2
        h2 = size2 if size2 > 0 else size
        builders: dict[str, Callable[[], Stroke]] = {
            "circle": lambda: arc_points(cx, cy, r, 0.0, 360.0),
            "ellipse": lambda: ellipse_points(cx, cy, size / 2, h2 / 2),
            "rectangle": lambda: rect_points(cx - size / 2, cy - h2 / 2, size, h2),
            "square": lambda: rect_points(cx - size / 2, cy - size / 2, size, size),
            "polygon": lambda: polygon_points(cx, cy, r, sides),
            "triangle": lambda: polygon_points(cx, cy, r, 3, 90.0),
            "star": lambda: star_points(cx, cy, r, r * 0.4, max(sides, 3)),
            "spiral": lambda: spiral_points(cx, cy, 0.5, r, turns),
            "heart": lambda: heart_points(cx, cy, size),
            "hatch": lambda: hatch_points(cx - size / 2, cy - h2 / 2, size, h2, 2.0),
            "wave": lambda: wave_points((cx - size / 2, cy), (cx + size / 2, cy), h2 if size2 > 0 else size / 8, turns),
        }
        if kind not in builders:
            raise ValueError(f"unknown shape '{kind}'; choose one of {sorted(builders)}")
        strokes = [builders[kind]()]
        if rotation_deg:
            strokes = transform_strokes(strokes, rotate_deg=rotation_deg, about=(cx, cy))
        return self._submit(strokes, f"draw_shape:{kind}", dry_run)

    def draw_polyline(self, points: list[Pt], dry_run: bool = False) -> dict[str, object]:
        """Draw connected straight segments through points [[x, y], ...]. Prefer draw_shape / draw_svg_path
        for anything that is not a plain polyline."""
        return self._submit([[point(p) for p in points]], "draw_polyline", dry_run)

    def draw_line(self, x1: float, y1: float, x2: float, y2: float, dry_run: bool = False) -> dict[str, object]:
        """Draw a straight line from (x1, y1) to (x2, y2). With no pen-up, the tip first travels to (x1, y1) touching."""
        return self._submit([[(x1, y1), (x2, y2)]], "draw_line", dry_run)

    def draw_arc(
        self, cx: float, cy: float, radius: float, start_deg: float, end_deg: float, dry_run: bool = False
    ) -> dict[str, object]:
        """Draw a circular arc of `radius` mm around (cx, cy), from start_deg to end_deg (degrees from +x; counter-clockwise
        if end_deg > start_deg, clockwise otherwise). 0 to 180 is the top half, 0 to 360 a full circle."""
        return self._submit([arc_points(cx, cy, radius, start_deg, end_deg)], "draw_arc", dry_run)

    def draw_bezier(self, p0: Pt, p1: Pt, p2: Pt, p3: Pt, dry_run: bool = False) -> dict[str, object]:
        """Draw a cubic Bezier curve from p0 to p3 with control points p1 and p2 (each point is [x, y])."""
        stroke = bezier_points(point(p0, "p0"), point(p1, "p1"), point(p2, "p2"), point(p3, "p3"), self.arm.cfg.seg_mm)
        return self._submit([stroke], "draw_bezier", dry_run)

    # ---- jobs and state ----

    def job_status(self, job_id: str = "") -> dict[str, object]:
        """Status of a drawing job (the latest if job_id is empty): running | done | cancelled | error, progress, seconds."""
        return self.jobs.get(job_id or None).summary()

    def stop(self) -> dict[str, object]:
        """Emergency stop: cancel the running drawing job or the drawing playing on the board; the arm halts and stays where it is."""
        job = self.jobs.stop()
        if job is None:
            self.arm.stop()  # nothing live is running: a stored drawing may be (X on the board is harmless otherwise)
        return job.summary() if job else {"status": "idle"}

    def get_state(self) -> dict[str, object]:
        """Servo angles, raw pot readings, and the estimated tip position (canvas and page mm)."""
        return self.arm.state()


__all__ = ["Plotter"]
