# Pen plotter (LLM -> MCP -> ESP32 -> servos), 2026-10-21

Code: ``. 2-link planar arm, 2 SG90 servos + 2 feedback pots, pencil in a clamp (no pen-up yet).

## Layout
- `firmware` (PlatformIO, esp32dev): line protocol `?`, `V`, `A s1 s2` (OK on arrival), `R`. Servos GPIO18/19, pots GPIO34/35. Builds clean.
- `server` (uv): `config.py` = geometry + calibration (single source), `kinematics.py` = IK/FK, `arm.py` = owner of the draw cycle, `server.py` = MCP tools (`page_info`, `move_to`, `draw_polyline`, `get_state`). `PENARM_PORT` unset = simulator.

## Boards (ESP32 or Arduino Uno)
`firmware/src/config.h` is the only board-specific file (pins, servo lib, ADC range). Envs: `esp32`, `uno` (main firmware) and `servotest`, `servotest_uno` (standalone serial servo test: `1 90`, `2 90`, `c`, `s`, `r`).
Uno pins: proximal servo (1) D10, distal servo (2) D9, pots A0/A1 (10-bit ADC, 0..1023 vs ESP32's 0..4095; `?` reports `adcmax`). ESP32: servos GPIO18/19, pots GPIO34/35.

    cd firmware && pio run -e uno -t upload        # or -e esp32 / -e servotest_uno

Power the servos from an external 5 V supply with common GND on either board.

Serial runs at 57600 baud (`PENARM_BAUD` in `config.h`, matched by `SerialLink`): at 115200 a CH340 Uno clone dropped ~40% of reply lines. The Windows CH340 driver (3.9) also refuses to configure a port at the baud it already has, so `SerialLink` opens at 9600, switches once and never reconfigures.

## Run
    cd server && uv run pytest && PENARM_PORT=/dev/cu.usbserial-XXXX uv run penarm-mcp   # Windows: PENARM_PORT=COM3
MCP client entry: command `uv`, args `["--directory", ".../server", "run", "penarm-mcp"]`.

## Canvas and tools
The server computes a **canvas**: the largest rectangle the arm can fully reach (grid scan of the IK), in its own mm frame (origin bottom-left); `set_canvas` switches to a tall `portrait` / `portrait_left` / `portrait_right` area. Drawing tools take canvas coordinates only, so the LLM never sees page or servo geometry. All of them build **strokes** and go through one entry that validates the whole drawing before anything moves:
- `draw_path` (typed ops: move/line/arc/bezier/quad/close, plus `transform` and `fit` to place it), `draw_svg_path` (SVG `d` strings, scaled into a box, y flipped), `draw_shape` (circle, ellipse, rectangle, square, polygon, triangle, star, spiral, heart, hatch, wave), `draw_polyline`, `draw_line`, `draw_bezier`, `move_to`.
- `dry_run=true` on any of them returns bbox, length, estimated time, an ASCII thumbnail and an SVG, and moves nothing.
- Drawings run as **jobs**: a call waits `PENARM_SYNC_WAIT` s (default 20), then returns a `job_id` to poll with `job_status`; `stop()` cancels within a millimetre. One job at a time.
- Also `canvas_info`, `get_state`, `locate_pencil` (camera).

## Robustness
- One server per serial port (lock file); retries with a resend (every command is idempotent); automatic reconnect when the board goes silent.
- The firmware reports a `boot=<id>` that changes on every restart: the server notices a reset (brown-out, cable bump), re-syncs the arm's real pose and re-validates the stroke instead of drawing from a stale position.
- `W <s>` makes the board release the servos after that long without commands (`idle_release_s`, default 120 s), so a dead host never leaves the pen pressing the paper.
- Tests run against a fake board that loses 40% of the replies like the CH340 clone (`tests/fakes.py`); the retry test goes red with `retries=1`.

## Calibration (`PENARM_MODE=calibrate`): the LLM delimits the paper
Offsets, signs and base are fitted from observations instead of being edited in code (`calibration.json`, git-ignored, applied on startup). The LLM does the measuring from ordinary photos:
1. `set_paper(width, height)` (default 200 x 275 mm).
2. For each pose (`calibration_poses`, `goto_servos`): take a photo, read the **four paper corners** and the **pen tip's contact point on the paper** in pixels, and call `record_photo_observation(corners, point_px)`. Corners are named from the arm's point of view (`near_left`, `near_right`, `far_right`, `far_left`, near = closest to the base); a homography maps pixels to paper mm, so a hand-held camera is fine. Use an ink dot or the pen touching the paper, not the holder (it sits above the paper and shifts with perspective).
3. `fit_calibration(scope)`: `base` (the paper moved: one photo re-registers it; offsets and lengths stay), `pose` (offsets, signs, base; >= 4 points), `full` (also link lengths; >= 7). It tries all sign combinations, reports the rmse in mm, saves and applies it, and the canvas is recomputed.
Ruler measurements still work (`record_calibration_point`). The fitter is pure-Python Levenberg-Marquardt, tested on synthetic perspective photos (recovers offsets < 0.2 deg, base < 0.5 mm, one-photo base re-registration exact).

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
1. Link lengths measured (105/115 mm); base position and page placement are rough (ruler + photos) -> refine in `config.py`.
2. Servo signs tested, offsets estimated from photos (a 60 mm square draws square but ~50 mm: pen friction lag). Pots are not wired yet; then pot raw -> angle.
3. Pen lift (3rd servo) -> `pen_up`/`pen_down` tools. Stiffen link 2 (flexes).
4. Closed loop with pots; optional camera feedback loop.
