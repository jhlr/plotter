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
   tool uses canvas coordinates; points outside the canvas are rejected. The canvas can be a wide, short band:
   plan the drawing to fit its real width and height.
2. The pencil has no pen-up: it touches the paper on every move, including the travel to the first point. So
   draw ONE continuous stroke per drawing; avoid designs that need lifted travel moves (separate letters, dots).
3. Prefer the high-level tools: draw_line, draw_rectangle, draw_circle, draw_arc, draw_bezier (smooth curves,
   loops). Use draw_polyline only for shapes they cannot express.
4. Stay at least 5 mm inside the canvas edges. If a tool reports a point as unreachable, shrink or shift the
   drawing instead of retrying the same coordinates.
5. Before drawing, say in one sentence what you will draw and where. After, confirm what was drawn.
6. If locate_pencil is available, call it after a stroke to verify the tip ended where intended. It returns
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
