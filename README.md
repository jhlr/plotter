# Pen plotter (LLM -> MCP -> ESP32 -> servos), 2026-10-21

Code: ``. 2-link planar arm, 2 SG90 servos + 2 feedback pots, pencil in a clamp (no pen-up yet).

## Layout
- `firmware` (PlatformIO, esp32dev): line protocol `?`, `V`, `A s1 s2` (OK on arrival), `R`. Servos GPIO18/19, pots GPIO34/35. Builds clean.
- `server` (uv): `config.py` = geometry + calibration (single source), `kinematics.py` = IK/FK, `arm.py` = owner of the draw cycle, `server.py` = MCP tools (`page_info`, `move_to`, `draw_polyline`, `get_state`). `PENARM_PORT` unset = simulator.

## Run
    cd server && uv run pytest && PENARM_PORT=/dev/cu.usbserial-XXXX uv run penarm-mcp
MCP client entry: command `uv`, args `["--directory", ".../server", "run", "penarm-mcp"]`.

## Vision (optional)
Overhead camera, OpenCV runs in the server: the LLM gets `locate_pencil` numbers (x/y mm, frames seen, spread, error vs kinematic estimate), never frames.
1. `uv sync --all-extras && uv run penarm-markers` writes `markers/marker_{0..3}.png`; print at 20 mm and stick the centers at the page positions in `VisionConfig` (homography is re-learned every frame, so a bumped camera self-corrects).
2. Pencil tag = green blob (eraser end) by default; tune `hsv_lo/hsv_hi` in `config.py`. Parallax from a tall tag is not corrected yet.
3. `PENARM_CAMERA=0` (device index or stream URL) enables the tool. Tested on a synthetic perspective scene (< 1 mm), not on a real camera yet.

## Agent (Google ADK)
`agent/` is a separate uv project (ADK pins `mcp<2`, the server uses mcp 2.x). `penarm_agent/agent.py` defines `root_agent` (any LLM via `PENARM_MODEL`: plain `gemini-*` is native, `provider/model` goes through LiteLLM, e.g. `openai/gpt-4o`, `anthropic/claude-sonnet-5-5`, `ollama_chat/llama3.1`), which spawns the MCP server over stdio and uses its tools.

    cd agent && export PENARM_MODEL=anthropic/claude-sonnet-5-5 ANTHROPIC_API_KEY=...  # or GOOGLE_API_KEY with the default; simulator unless PENARM_PORT is set
    uv run penarm-chat                      # terminal loop
    uv run adk web .                        # ADK dev UI

## TODO
1. Measure real link lengths, base position, page placement -> `config.py` (current values are placeholders).
2. Calibrate sign/offset per servo (servo angle vs real joint angle); then pot raw -> angle.
3. Pen lift (3rd servo) -> `pen_up`/`pen_down` tools. Stiffen link 2 (flexes).
4. Closed loop with pots; optional camera feedback loop.
