"""MCP server exposing the arm to an LLM. Set PENARM_PORT=/dev/cu.usbserial-XXXX, or omit for simulator."""
import functools
import os
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .arm import Arm
from .config import DEFAULT
from .shapes import arc_points
from .kinematics import Unreachable
from .link import Link, SerialLink, SimLink

P = ParamSpec("P")
R = TypeVar("R")


def llm_readable_errors(fn: Callable[P, R]) -> Callable[P, R]:
    """Unreachable/bad-argument errors reach the LLM with their message so it can adapt the drawing."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except (Unreachable, ValueError) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


mcp = MCPServer("penarm")
_port = os.environ.get("PENARM_PORT")
_link: Link = SerialLink(_port) if _port else SimLink()
_arm = Arm(DEFAULT, _link)


@mcp.tool()
def page_info() -> dict[str, object]:
    """Drawing area. Origin bottom-left, x right, y up, in mm. Points outside are rejected."""
    return {"width_mm": DEFAULT.page_w, "height_mm": DEFAULT.page_h, "simulated": _port is None}


@mcp.tool()
@llm_readable_errors
def move_to(x: float, y: float) -> str:
    """Draw a straight line from the current tip position to (x, y) mm. There is no pen-up: the pencil always touches."""
    _arm.move_to(x, y)
    return f"at ({x:.1f}, {y:.1f})"


@mcp.tool()
@llm_readable_errors
def draw_polyline(points: list[tuple[float, float]]) -> str:
    """Draw connected straight segments through points [(x, y), ...] in mm. Approximate curves with many points."""
    _arm.draw_polyline(points)
    return f"drew {len(points)} points"


@mcp.tool()
@llm_readable_errors
def draw_arc(cx: float, cy: float, r: float, start_deg: float, end_deg: float) -> str:
    """Draw a circular arc (mm, degrees from +x axis). Counter-clockwise if end_deg > start_deg, else clockwise.
    The tip first travels in a straight line to the arc start (no pen-up, so that line marks the paper)."""
    _arm.draw_polyline(arc_points(cx, cy, r, start_deg, end_deg))
    return f"arc r={r} from {start_deg} to {end_deg} deg"


@mcp.tool()
@llm_readable_errors
def draw_circle(cx: float, cy: float, r: float) -> str:
    """Draw a full circle of radius r centered at (cx, cy), starting at its rightmost point, counter-clockwise."""
    _arm.draw_polyline(arc_points(cx, cy, r, 0.0, 360.0))
    return f"circle r={r} at ({cx}, {cy})"


@mcp.tool()
def get_state() -> dict[str, object]:
    """Servo angles, raw pot readings, and estimated tip position."""
    return _arm.state()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
