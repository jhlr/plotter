"""ADK agent: the configured LLM plans the drawing, the penarm MCP server executes it on the arm."""
import os
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
# Provider-agnostic: "gemini-2.5-flash" uses ADK's native Gemini client; any "provider/model" string
# (openai/gpt-4o, anthropic/claude-sonnet-5-5, ollama_chat/llama3.1, ...) goes through LiteLLM,
# which reads that provider's usual API-key env var.
MODEL_NAME = os.environ.get("PENARM_MODEL", "gemini-2.5-flash")
MODEL: str | LiteLlm = LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME

INSTRUCTION = """\
You control a pen-plotter arm that draws on a paper notebook through tools.
Rules:
1. Call canvas_info first: it gives the reachable canvas (mm, origin bottom-left, x right, y up). Every drawing
   tool uses canvas coordinates. The canvas can be a wide, short band: plan the drawing to fit its real size.
2. The pencil has no pen-up: it touches the paper on every move, including the travel to the first point. So
   draw ONE continuous stroke per drawing; avoid designs that need lifted travel moves (separate letters, dots).
3. Pick the highest-level tool that fits, and never hand-compute long polylines:
   draw_shape for named shapes (circle, rectangle, star, spiral, heart, wave, ...), draw_svg_path for anything you
   can write as SVG path data (it is scaled into a box you give and the y axis is flipped for you), draw_path for
   custom geometry (text ops such as "move 0 0", "line 20 0", "arc cx cy r a0 a1", "bezier ...", "close"; then
   `fit_box` to place it on the canvas).
4. For anything non-trivial call the tool with dry_run=true first: read inside_canvas, length_mm, est_seconds and
   the ASCII thumbnail, adjust, then draw for real. If a drawing does not fit, shrink it or use `fit`; do not
   retry the same coordinates.
5. A drawing call that takes long returns a job_id with status "running": poll job_status(job_id) until it is
   done. Call stop() immediately if something looks wrong. Only one job runs at a time.
6. Before drawing, say in one sentence what you will draw and where. After, confirm what was drawn.
7. If locate_pencil is available, call it after a stroke to verify the tip ended where intended. It returns
   numbers only (no image). If error_mm is above ~2 mm, report the drift instead of drawing on blindly.
"""

# Forwarded to the server: PENARM_PORT = real arm (unset = simulator), PENARM_CAMERA = overhead camera (unset = no vision).
_env = {k: v for k, v in os.environ.items() if k in ("PENARM_PORT", "PENARM_CAMERA")}

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
