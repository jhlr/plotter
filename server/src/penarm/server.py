"""MCP server exposing the arm to an LLM. Set PENARM_PORT=/dev/cu.usbserial-XXXX, or omit for simulator."""
import os

from mcp.server import MCPServer

from .arm import Arm
from .config import DEFAULT
from .link import Link, SerialLink, SimLink

mcp = MCPServer("penarm")
_port = os.environ.get("PENARM_PORT")
_link: Link = SerialLink(_port) if _port else SimLink()
_arm = Arm(DEFAULT, _link)


@mcp.tool()
def page_info() -> dict[str, object]:
    """Drawing area. Origin bottom-left, x right, y up, in mm. Points outside are rejected."""
    return {"width_mm": DEFAULT.page_w, "height_mm": DEFAULT.page_h, "simulated": _port is None}


@mcp.tool()
def move_to(x: float, y: float) -> str:
    """Move the pencil tip in a straight line to (x, y) mm. There is no pen-up: the pencil always touches."""
    _arm.move_to(x, y)
    return f"at ({x:.1f}, {y:.1f})"


@mcp.tool()
def draw_polyline(points: list[tuple[float, float]]) -> str:
    """Draw connected straight segments through points [(x, y), ...] in mm. Approximate curves with many points."""
    _arm.draw_polyline(points)
    return f"drew {len(points)} points"


@mcp.tool()
def get_state() -> dict[str, object]:
    """Servo angles, raw pot readings, and estimated tip position."""
    return _arm.state()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
