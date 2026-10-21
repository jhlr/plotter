"""ADK agent: Gemini plans the drawing, the penarm MCP server executes it on the arm."""
import os
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
MODEL = os.environ.get("PENARM_MODEL", "gemini-2.5-flash")

INSTRUCTION = """\
You control a pen-plotter arm that draws on a paper notebook through tools.
Rules:
1. Call page_info first to learn the drawing area (mm, origin bottom-left, y up).
2. The pencil has no pen-up: it touches the paper on every move, including the move to the first
   point. So draw ONE continuous stroke per drawing; avoid designs that need lifted travel moves.
3. Draw with draw_polyline. Approximate curves with many points (a circle needs >= 40).
4. Keep every point at least 10 mm inside the page edges. If a tool reports a point as unreachable,
   shrink or shift the drawing instead of retrying the same coordinates.
5. Before drawing, say in one sentence what you will draw and where. After, confirm what was drawn.
"""

# PENARM_PORT is forwarded to the server: set it for real hardware, leave it unset for the simulator.
_env = {k: v for k, v in os.environ.items() if k == "PENARM_PORT"}

root_agent = LlmAgent(
    name="penarm_artist",
    model=MODEL,
    description="Draws shapes and figures on paper with a 2-servo pencil arm.",
    instruction=INSTRUCTION,
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="uv",
                    args=["--directory", str(SERVER_DIR), "run", "penarm-mcp"],
                    env=_env or None,
                ),
                timeout=30.0,
            )
        )
    ],
)
