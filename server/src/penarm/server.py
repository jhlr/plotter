"""MCP server: exposes `Plotter` (plotter.py) to an LLM. All behaviour lives there; this file only registers the
methods as tools and turns their errors into messages the LLM can read.
PENARM_PORT=/dev/cu.usbserial-XXXX for hardware (omit or empty = simulator), PENARM_SYNC_WAIT=<s> (default 20) for how long a drawing call waits for its job before
returning a job id to poll."""
import functools
import os
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .errors import Busy, Unreachable
from .plotter import Plotter

P = ParamSpec("P")
R = TypeVar("R")


def llm_readable_errors(fn: Callable[P, R]) -> Callable[P, R]:
    """Unreachable/bad-argument/hardware errors reach the LLM with their message so it can adapt the drawing."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except (Unreachable, Busy, ValueError, TimeoutError, RuntimeError) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


GUIDE = """\
A two-servo pen-plotter arm. Provider-neutral usage guide:
1. Call canvas_info first: the reachable canvas in mm (origin bottom-left, x right, y up). All drawing tools use it.
2. The pencil has no pen-up: draw one continuous trace; travel between strokes marks the paper.
3. Prefer the highest-level tool: draw_shape (named shapes), draw_svg_path (SVG path data fitted into a box),
   then draw_polyline / draw_line / draw_arc / draw_bezier.
4. For anything non-trivial call the tool with dry_run=true first (bbox, length, time, ASCII thumbnail, SVG), then draw.
5. A drawing returns a job_id if it takes long: poll job_status; call stop() to cancel. One job at a time.
6. Points are plain [x, y] arrays; optional arguments use defaults (0, empty list, empty string), never null.
"""

plotter = Plotter(os.environ.get("PENARM_PORT") or None, wait_s=float(os.environ.get("PENARM_SYNC_WAIT", "20")))
mcp = MCPServer("penarm", instructions=GUIDE)

TOOLS = ("canvas_info", "draw_svg_path", "draw_shape", "draw_polyline", "draw_line",
         "draw_arc", "draw_bezier", "job_status", "stop", "get_state")
for _name in TOOLS:
    mcp.tool()(llm_readable_errors(getattr(plotter, _name)))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
