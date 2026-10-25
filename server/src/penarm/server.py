"""MCP server exposing the arm to an LLM.
PENARM_PORT=/dev/cu.usbserial-XXXX for hardware (omit = simulator), PENARM_CAMERA=<index|url> for the vision tool,
PENARM_MODE=calibrate to expose the calibration tools, PENARM_SYNC_WAIT=<s> (default 20) for how long a drawing
call waits for its job before returning a job id to poll."""
import functools
import math
import os
from collections.abc import Callable
from typing import Annotated, ParamSpec, TypeVar

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from .arm import Arm
from .calibration import CalibrationStore, Observation, corner_sanity, paper_point_from_photo, suggest_poses
from .config import DEFAULT
from .errors import Busy, Unreachable, VisionError
from .jobs import JobRunner
from .link import Link, SerialLink, SimLink
from .paths import Fit, Op, Transform, apply_transform_fit, strokes_from_ops, svg_to_strokes
from .preview import describe
from .shapes import (Stroke, arc_points, bbox, bezier_points, ellipse_points, fit_strokes, heart_points, hatch_points,
                     polygon_points, rect_points, spiral_points, star_points, transform_strokes, wave_points)

P = ParamSpec("P")
R = TypeVar("R")
XY = tuple[float, float]


def llm_readable_errors(fn: Callable[P, R]) -> Callable[P, R]:
    """Unreachable/bad-argument/hardware errors reach the LLM with their message so it can adapt the drawing."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except (Unreachable, VisionError, Busy, ValueError, TimeoutError, RuntimeError) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


mcp = MCPServer("penarm")
_port = os.environ.get("PENARM_PORT")
_link: Link = SerialLink(_port) if _port else SimLink()
_store = CalibrationStore()
_arm = Arm(_store.apply(DEFAULT), _link)
_jobs = JobRunner()
_sync_wait = float(os.environ.get("PENARM_SYNC_WAIT", "20"))
_camera = os.environ.get("PENARM_CAMERA")  # device index or stream URL; unset = no vision
_locator = None
if _camera:
    from .vision import Camera, PencilLocator  # opencv is an optional extra: only imported when used

    _locator = PencilLocator(_arm.cfg, Camera(_camera))


def _round(p: XY) -> XY:
    return round(p[0], 1), round(p[1], 1)


def _submit(strokes: list[Stroke], label: str, dry_run: bool) -> dict[str, object]:
    """Single entry of every drawing tool: validate the whole drawing, then preview it or run it as a job."""
    x0, y0, x1, y1 = bbox(strokes)
    c = _arm.canvas
    if not (c.contains(x0, y0) and c.contains(x1, y1)):
        raise Unreachable(
            f"the drawing's bounding box ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f}) mm does not fit the canvas "
            f"({c.w:.0f} x {c.h:.0f} mm, origin bottom-left): shrink it, move it, or use draw_path with `fit`"
        )
    _arm.plan(strokes)  # raises Unreachable if a step along the way is not reachable; nothing has moved yet
    travel_from = _arm.canvas.from_page(*_arm.pos) if _arm.pos else None
    info = describe(strokes, _arm.canvas, travel_from)
    if dry_run:
        return {"dry_run": True, **info}
    job = _jobs.submit(label, lambda cancel, progress: _arm.draw_strokes(strokes, cancel, progress))
    _jobs.wait(job, _sync_wait)
    summary: dict[str, object] = dict(job.summary())
    summary.update({k: info[k] for k in ("bbox_mm", "length_mm", "travel_marks_mm", "est_seconds")})
    if job.status == "running":
        summary["hint"] = "still drawing: poll job_status(job_id), or call stop() to cancel"
    return summary


# ---- the canvas: every coordinate below is canvas mm (origin bottom-left, x right, y up) ----


@mcp.tool()
def canvas_info() -> dict[str, object]:
    """START HERE. The drawing canvas: a rectangle the arm can fully reach, in mm, origin at its bottom-left corner,
    x right, y up. Every drawing tool takes coordinates in this frame; points outside are rejected. The pencil has
    no pen-up yet, so a drawing is one continuous trace (travel between strokes marks the paper)."""
    c = _arm.canvas
    return {"width_mm": round(c.w, 1), "height_mm": round(c.h, 1), "orientation": _arm.orientation, "pen_up": False,
            "calibrated": bool(_store.params), "simulated": _port is None, "busy": _busy()}


def _busy() -> bool:
    try:
        return _jobs.get().status == "running"
    except ValueError:
        return False


@mcp.tool()
@llm_readable_errors
def set_canvas(orientation: str) -> dict[str, object]:
    """Choose the drawing area: 'landscape' (default) is a wide, short band; 'portrait' is a tall, narrow rectangle;
    'portrait_left' / 'portrait_right' put the tall rectangle in the left/right side area of the paper, away from
    the central band. Coordinates of later drawing tools are in the new canvas."""
    if _busy():
        raise Busy("a drawing job is running: wait for it or call stop() before changing the canvas")
    _arm.set_orientation(orientation)
    return canvas_info()


# ---- trajectories: all of these build strokes and go through the same _submit (jobs, dry_run, validation) ----


@mcp.tool()
@llm_readable_errors
def draw_path(
    ops: list[Op], transform: Transform | None = None, fit: Fit | None = None, dry_run: bool = False
) -> dict[str, object]:
    """THE GENERAL TOOL. Draw a path made of operations: {"op":"move","to":[x,y]} starts a stroke, then "line",
    "arc" (center, radius, start_deg, end_deg), "bezier" (c1, c2, to), "quad" (c, to), "close". Optional
    `transform` (mirror, scale, rotate about a point, translate) and `fit` (scale the whole drawing into a box,
    centered) are applied after the ops, so you can design in any units and let `fit` place it on the canvas.
    dry_run=true plans only and returns bbox, length, estimated time, an ASCII thumbnail and an SVG."""
    strokes = apply_transform_fit(strokes_from_ops(ops, _arm.cfg.seg_mm), transform, fit)
    return _submit(strokes, "draw_path", dry_run)


@mcp.tool()
@llm_readable_errors
def draw_svg_path(
    d: str, x: float, y: float, width: float, height: float | None = None, margin: float = 0.0, dry_run: bool = False
) -> dict[str, object]:
    """Draw an SVG path (the `d` attribute: M L H V C S Q T A Z, absolute or relative). Its bounding box is scaled
    to `width` mm (and `height` if given, otherwise keeping the aspect) and placed with the bottom-left corner at
    (x, y) on the canvas. SVG's y axis points down; it is flipped for you. Subpaths are joined by straight lines
    (no pen-up yet)."""
    raw = svg_to_strokes(d, 1.0)
    flipped = [[(px, -py) for px, py in s] for s in raw]
    x0, y0, x1, y1 = bbox(flipped)
    h = height if height is not None else width * (y1 - y0) / max(x1 - x0, 1e-9)
    strokes = fit_strokes(flipped, x, y, width, h, margin, keep_aspect=height is None)
    return _submit(strokes, "draw_svg_path", dry_run)


@mcp.tool()
@llm_readable_errors
def draw_shape(
    kind: str, cx: float, cy: float, size: float, size2: float | None = None, sides: int = 5, turns: float = 3.0,
    rotation_deg: float = 0.0, dry_run: bool = False,
) -> dict[str, object]:
    """Draw a named shape centered at (cx, cy). kind: circle (size = diameter), ellipse (size = width, size2 = height),
    rectangle (size = width, size2 = height), square (size = side), polygon (size = diameter, sides), triangle (size =
    diameter), star (size = outer diameter, sides = tips), spiral (size = outer diameter, turns), heart (size = width),
    hatch (size = width, size2 = height: back-and-forth fill), wave (size = length, size2 = amplitude, turns = cycles).
    rotation_deg rotates it about its center (counter-clockwise)."""
    r = size / 2
    h2 = size2 if size2 is not None else size
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
        "wave": lambda: wave_points((cx - size / 2, cy), (cx + size / 2, cy), h2 if size2 is not None else size / 8, turns),
    }
    if kind not in builders:
        raise ValueError(f"unknown shape '{kind}'; choose one of {sorted(builders)}")
    strokes = [builders[kind]()]
    if rotation_deg:
        strokes = transform_strokes(strokes, rotate_deg=rotation_deg, about=(cx, cy))
    return _submit(strokes, f"draw_shape:{kind}", dry_run)


@mcp.tool()
@llm_readable_errors
def draw_polyline(points: list[XY], dry_run: bool = False) -> dict[str, object]:
    """Draw connected straight segments through points [(x, y), ...]. Prefer draw_path / draw_shape / draw_svg_path
    for anything that is not a plain polyline."""
    return _submit([list(points)], "draw_polyline", dry_run)


@mcp.tool()
@llm_readable_errors
def draw_line(x1: float, y1: float, x2: float, y2: float, dry_run: bool = False) -> dict[str, object]:
    """Draw a straight line from (x1, y1) to (x2, y2). With no pen-up, the tip first travels to (x1, y1) touching."""
    return _submit([[(x1, y1), (x2, y2)]], "draw_line", dry_run)


@mcp.tool()
@llm_readable_errors
def draw_bezier(p0: XY, p1: XY, p2: XY, p3: XY, dry_run: bool = False) -> dict[str, object]:
    """Draw a cubic Bezier curve from p0 to p3 with control points p1 and p2."""
    return _submit([bezier_points(p0, p1, p2, p3, _arm.cfg.seg_mm)], "draw_bezier", dry_run)


@mcp.tool()
@llm_readable_errors
def move_to(x: float, y: float) -> dict[str, object]:
    """Draw a straight line from the current tip position to (x, y). There is no pen-up: the pencil always touches."""
    return _submit([[(x, y)]], "move_to", False)


# ---- jobs, state, vision ----


@mcp.tool()
@llm_readable_errors
def job_status(job_id: str | None = None) -> dict[str, object]:
    """Status of a drawing job (the latest if job_id is omitted): running | done | cancelled | error, progress, seconds."""
    return _jobs.get(job_id).summary()


@mcp.tool()
def stop() -> dict[str, object]:
    """Emergency stop: cancel the running drawing job; the arm halts within a millimetre and stays where it is."""
    job = _jobs.stop()
    return job.summary() if job else {"status": "idle"}


@mcp.tool()
def get_state() -> dict[str, object]:
    """Servo angles, raw pot readings, and the estimated tip position (canvas and page mm)."""
    return _arm.state()


@mcp.tool()
@llm_readable_errors
def locate_pencil() -> dict[str, object]:
    """Where the pencil tip is according to the overhead camera (canvas mm), as numbers only. error_mm is the
    distance to the kinematic estimate: large = the arm is not where it was commanded (slip, flex, bad calibration)."""
    if _locator is None:
        raise ToolError("no camera configured (set PENARM_CAMERA)")
    fix = _locator.locate()
    fk_page = _arm.tip_fk()
    cx, cy = _arm.canvas.from_page(fix.x_mm, fix.y_mm)
    return {"x_mm": round(cx, 1), "y_mm": round(cy, 1), "in_page": fix.in_page,
            "frames_seen": f"{fix.seen}/{fix.frames}", "spread_mm": fix.spread_mm,
            "fk_estimate_mm": _round(_arm.canvas.from_page(*fk_page)),
            "error_mm": round(math.dist((fix.x_mm, fix.y_mm), fk_page), 1)}


# ---- calibration (PENARM_MODE=calibrate): the LLM delimits the paper in photos, the server fits the arm to it ----

if os.environ.get("PENARM_MODE") == "calibrate":

    class PaperCorners(BaseModel):
        """Pixel positions of the paper's four corners in the photo, named from the ARM's point of view: 'near' is the
        edge closest to the arm's base, 'left'/'right' as seen standing at the base looking toward the far edge."""
        near_left: XY
        near_right: XY
        far_right: XY
        far_left: XY

    @mcp.tool()
    @llm_readable_errors
    def set_paper(width_mm: float, height_mm: float) -> dict[str, object]:
        """Real size of the sheet (width = the near edge, height = the side going away from the base). Default 200 x 275."""
        if width_mm < 50 or height_mm < 50:
            raise ValueError("paper size looks wrong (mm)")
        _store.params.update({"page_w": width_mm, "page_h": height_mm})
        _store.save()
        _arm.set_config(_store.apply(_arm.cfg))
        return {"paper_mm": (width_mm, height_mm)}

    @mcp.tool()
    @llm_readable_errors
    def record_photo_observation(
        corners: PaperCorners, point_px: XY, note: str = ""
    ) -> dict[str, object]:
        """Register where the tip is on the paper from ONE photo: give the paper's four corners and the pixel of the
        tip's contact point on the PAPER (an ink dot or the pen tip touching it; not the pen top or the holder, which
        sit above the paper and shift with perspective). Uses the servo angles the board reports now. Take several
        photos at different poses (goto_servos), then call fit_calibration."""
        cs: dict[str, XY] = {k: (v[0], v[1]) for k, v in corners.model_dump().items()}
        warn = corner_sanity(cs)
        w, h = _arm.cfg.page_w, _arm.cfg.page_h
        x, y = paper_point_from_photo(cs, point_px, w, h)
        _, _, s1, s2 = _link.read()
        _store.add_point(Observation(s1, s2, x, y))
        return {"tip_paper_mm": _round((x, y)), "servo_deg": (s1, s2), "estimated_by_current_model_mm": _round(_arm.tip_fk()),
                "points": len(_store.points), "warnings": warn, "note": note}

    @mcp.tool()
    def calibration_poses() -> list[XY]:
        """Servo poses (s1, s2) to visit for calibration, spread over the workspace."""
        return suggest_poses(_arm.cfg)

    @mcp.tool()
    @llm_readable_errors
    def goto_servos(s1: float, s2: float) -> dict[str, object]:
        """Move both servos straight to angles (degrees, within the servo limits). Not interpolated: keep the pen
        clear of anything it should not mark. Returns the tip position estimated by the CURRENT calibration."""
        _arm.goto_servos(s1, s2)
        return {"servo_deg": (s1, s2), "estimated_tip_page_mm": _round(_arm.tip_fk())}

    @mcp.tool()
    @llm_readable_errors
    def record_calibration_point(x_mm: float, y_mm: float) -> str:
        """Record that, at the CURRENT servo angles, the tip was measured (ruler) at (x_mm, y_mm) in PAPER mm (origin
        = the near-left corner of the sheet, x along the near edge, y toward the far edge)."""
        _, _, s1, s2 = _link.read()
        _store.add_point(Observation(s1, s2, x_mm, y_mm))
        return f"{len(_store.points)} points recorded"

    @mcp.tool()
    @llm_readable_errors
    def fit_calibration(scope: str = "pose", last: int | None = None) -> dict[str, object]:
        """Fit the recorded points. scope: 'base' (the PAPER MOVED: only the base position, needs >= 1 point, use
        last=N for the newest photos), 'pose' (offsets, signs and base, >= 4 points), 'full' (also link lengths, >= 7).
        Saves calibration.json and applies it; returns the residual in mm per point."""
        res = _store.fit(_arm.cfg, scope, last)
        _arm.set_config(res.cfg)
        c = _arm.canvas
        return {"rmse_mm": round(res.rmse_mm, 2), "points": res.n, "canvas_mm": (round(c.w), round(c.h)),
                "offset1": round(res.cfg.offset1, 1), "offset2": round(res.cfg.offset2, 1),
                "sign1": res.cfg.sign1, "sign2": res.cfg.sign2, "base_paper_mm": _round((res.cfg.base_x, res.cfg.base_y))}

    @mcp.tool()
    def clear_calibration_points() -> str:
        """Forget the recorded calibration points (keeps the last fitted parameters)."""
        _store.clear_points()
        return "cleared"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
