"""MCP server exposing the arm to an LLM.
PENARM_PORT=/dev/cu.usbserial-XXXX for hardware (omit = simulator), PENARM_CAMERA=<index|url> for vision,
PENARM_MODE=calibrate to expose the calibration tools instead of keeping them out of the drawing agent's way."""
import functools
import math
import os
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .arm import Arm
from .calibration import CalibrationStore, Observation, suggest_poses
from .config import DEFAULT
from .errors import Unreachable, VisionError
from .link import Link, SerialLink, SimLink
from .shapes import arc_points, bezier_points, rect_points

P = ParamSpec("P")
R = TypeVar("R")


def llm_readable_errors(fn: Callable[P, R]) -> Callable[P, R]:
    """Unreachable/bad-argument/hardware errors reach the LLM with their message so it can adapt the drawing."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except (Unreachable, VisionError, ValueError, TimeoutError, RuntimeError) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


mcp = MCPServer("penarm")
_port = os.environ.get("PENARM_PORT")
_link: Link = SerialLink(_port) if _port else SimLink()
_store = CalibrationStore()
_arm = Arm(_store.apply(DEFAULT), _link)
_camera = os.environ.get("PENARM_CAMERA")  # device index or stream URL; unset = no vision
_locator = None
if _camera:
    from .vision import Camera, PencilLocator  # opencv is an optional extra: only imported when used

    _locator = PencilLocator(_arm.cfg, Camera(_camera))


def _round(p: tuple[float, float]) -> tuple[float, float]:
    return round(p[0], 1), round(p[1], 1)


# ---- drawing: every coordinate is canvas mm (origin bottom-left, x right, y up) ----


@mcp.tool()
def canvas_info() -> dict[str, object]:
    """START HERE. The drawing canvas: a rectangle the arm can fully reach, in mm, origin at its bottom-left corner,
    x right, y up. Every drawing tool takes coordinates in this frame; points outside are rejected."""
    c = _arm.canvas
    return {"width_mm": round(c.w, 1), "height_mm": round(c.h, 1), "orientation": _arm.orientation, "pen_up": False,
            "calibrated": bool(_store.params), "simulated": _port is None}


@mcp.tool()
@llm_readable_errors
def set_canvas(orientation: str) -> dict[str, object]:
    """Choose the drawing area: 'landscape' (default) is a wide, short band; 'portrait' is a tall, narrow rectangle;
    'portrait_left' / 'portrait_right' put the tall rectangle in the left/right side area of the paper, away from
    the central band. Coordinates of later drawing tools are in the new canvas. The tip travels to
    the new area on the next drawing call, touching the paper on the way (no pen-up)."""
    _arm.set_orientation(orientation)
    return canvas_info()


@mcp.tool()
@llm_readable_errors
def draw_line(x1: float, y1: float, x2: float, y2: float) -> str:
    """Draw a straight line from (x1, y1) to (x2, y2). With no pen-up, the tip first travels to (x1, y1) touching."""
    _arm.draw_polyline([(x1, y1), (x2, y2)])
    return f"line ({x1:.1f},{y1:.1f}) -> ({x2:.1f},{y2:.1f})"


@mcp.tool()
@llm_readable_errors
def draw_polyline(points: list[tuple[float, float]]) -> str:
    """Draw connected straight segments through points [(x, y), ...]. Approximate curves with many points."""
    _arm.draw_polyline(points)
    return f"drew {len(points)} points"


@mcp.tool()
@llm_readable_errors
def draw_rectangle(x: float, y: float, width: float, height: float) -> str:
    """Draw a closed rectangle with bottom-left corner (x, y), counter-clockwise (width/height in mm, > 0)."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be > 0")
    _arm.draw_polyline(rect_points(x, y, width, height))
    return f"rectangle {width:.1f} x {height:.1f} at ({x:.1f},{y:.1f})"


@mcp.tool()
@llm_readable_errors
def draw_circle(cx: float, cy: float, r: float) -> str:
    """Draw a full circle of radius r centered at (cx, cy), starting at its rightmost point, counter-clockwise."""
    _arm.draw_polyline(arc_points(cx, cy, r, 0.0, 360.0))
    return f"circle r={r} at ({cx}, {cy})"


@mcp.tool()
@llm_readable_errors
def draw_arc(cx: float, cy: float, r: float, start_deg: float, end_deg: float) -> str:
    """Draw a circular arc (degrees from +x). Counter-clockwise if end_deg > start_deg, else clockwise.
    The tip first travels in a straight line to the arc start (no pen-up, so that line marks the paper)."""
    _arm.draw_polyline(arc_points(cx, cy, r, start_deg, end_deg))
    return f"arc r={r} from {start_deg} to {end_deg} deg"


@mcp.tool()
@llm_readable_errors
def draw_bezier(p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float]) -> str:
    """Draw a cubic Bezier curve from p0 to p3 with control points p1 and p2 (smooth curves, letters, loops)."""
    _arm.draw_polyline(bezier_points(p0, p1, p2, p3))
    return f"bezier from {p0} to {p3}"


@mcp.tool()
@llm_readable_errors
def move_to(x: float, y: float) -> str:
    """Draw a straight line from the current tip position to (x, y). There is no pen-up: the pencil always touches."""
    _arm.move_to(x, y)
    return f"at ({x:.1f}, {y:.1f})"


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
    return {"x_mm": _round(_arm.canvas.from_page(fix.x_mm, fix.y_mm))[0],
            "y_mm": _round(_arm.canvas.from_page(fix.x_mm, fix.y_mm))[1],
            "in_page": fix.in_page, "frames_seen": f"{fix.seen}/{fix.frames}", "spread_mm": fix.spread_mm,
            "fk_estimate_mm": _round(_arm.canvas.from_page(*fk_page)),
            "error_mm": round(math.dist((fix.x_mm, fix.y_mm), fk_page), 1)}


# ---- calibration (PENARM_MODE=calibrate): drive known servo poses, record where the tip really is, fit ----

if os.environ.get("PENARM_MODE") == "calibrate":

    @mcp.tool()
    def calibration_poses() -> list[tuple[float, float]]:
        """Servo poses (s1, s2) to visit for calibration, spread over the workspace. For each: goto_servos, wait for
        the arm to settle, have the tip position measured on the sheet (page mm, origin bottom-left corner of the
        sheet, ruler), then record_calibration_point."""
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
        """Record that, at the CURRENT servo angles, the tip was measured at (x_mm, y_mm) in PAGE mm (origin =
        bottom-left corner of the sheet, x right, y up)."""
        _, _, s1, s2 = _link.read()
        _store.add_point(Observation(s1, s2, x_mm, y_mm))
        return f"{len(_store.points)} points recorded"

    @mcp.tool()
    @llm_readable_errors
    def fit_calibration(fit_lengths: bool = False) -> dict[str, object]:
        """Fit servo offsets, signs and the base position (and link lengths if fit_lengths, needs >= 7 points) to the
        recorded points, save calibration.json and apply it. Returns the residual error in mm per point."""
        res = _store.fit(_arm.cfg, fit_lengths)
        _arm.set_config(res.cfg)
        c = _arm.canvas
        return {"rmse_mm": round(res.rmse_mm, 2), "points": res.n, "canvas_mm": (round(c.w), round(c.h)),
                "offset1": round(res.cfg.offset1, 1), "offset2": round(res.cfg.offset2, 1),
                "sign1": res.cfg.sign1, "sign2": res.cfg.sign2,
                "base_page_mm": _round((res.cfg.base_x, res.cfg.base_y))}

    @mcp.tool()
    def clear_calibration_points() -> str:
        """Forget the recorded calibration points (keeps the last fitted parameters)."""
        _store.clear_points()
        return "cleared"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
