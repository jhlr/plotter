# Pen plotter (LLM -> MCP -> ESP32 -> servos), 2026-10-21

Code: ``. 2-link planar arm, 2 SG90 servos + 2 feedback pots, pencil in a clamp (no pen-up yet).

## Layout
- `firmware` (PlatformIO, esp32dev): line protocol `?`, `V`, `A s1 s2` (OK on arrival), `R`. Servos GPIO18/19, pots GPIO34/35. Builds clean.
- `server` (uv): `config.py` = geometry + calibration (single source), `kinematics.py` = IK/FK, `arm.py` = owner of the draw cycle, `server.py` = MCP tools (`page_info`, `move_to`, `draw_polyline`, `get_state`). `PENARM_PORT` unset = simulator.

## Run
    cd server && uv run pytest && PENARM_PORT=/dev/cu.usbserial-XXXX uv run penarm-mcp
MCP client entry: command `uv`, args `["--directory", ".../server", "run", "penarm-mcp"]`.

## Agent (Google ADK)
`agent/` is a separate uv project (ADK pins `mcp<2`, the server uses mcp 2.x). `penarm_agent/agent.py` defines `root_agent` (Gemini, model via `PENARM_MODEL`), which spawns the MCP server over stdio and uses its tools.

    cd agent && export GOOGLE_API_KEY=...   # simulator unless PENARM_PORT is set
    uv run penarm-chat                      # terminal loop
    uv run adk web .                        # ADK dev UI

## TODO
1. Measure real link lengths, base position, page placement -> `config.py` (current values are placeholders).
2. Calibrate sign/offset per servo (servo angle vs real joint angle); then pot raw -> angle.
3. Pen lift (3rd servo) -> `pen_up`/`pen_down` tools. Stiffen link 2 (flexes).
4. Closed loop with pots; optional camera feedback loop.
