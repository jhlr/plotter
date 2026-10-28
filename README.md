# Pen plotter (LLM -> MCP -> ESP32 -> servos), 2026-10-21

Code: ``. 2-link planar arm, 2 SG90 servos + 2 feedback pots, pencil in a clamp (no pen-up yet).

## Quick start (new machine, Arduino Uno)
**Hardware:** Uno, 2 SG90 servos (proximal on **D9**, distal on **D8**), external **5 V supply for the servos** (>= 2 A) with its GND tied to the Uno's GND, USB cable to the computer. Never power the servos from the Uno's 5 V pin.

**Install:** [PlatformIO](https://platformio.org/install/cli) (`pio`) and [uv](https://docs.astral.sh/uv/) (Python >= 3.11). macOS/Linux/Windows.

**1. Flash the firmware and test the servos (before anything else):**

    cd firmware
    pio run -e servotest_uno -t upload      # standalone test: both servos go to 90 deg
    pio device monitor -b 57600             # type: 1 60  |  2 120  |  s (sweep)  |  c (centre)

If a servo does not move here, it is wiring or power, not software. Then flash the real firmware:

    pio run -e uno -t upload

Watch for **"verified"** at the end of the upload. A flash whose verify step fails (`avr_read(): error reading ...`) can leave a firmware that answers `OK` but never drives the servos: flash again until it verifies.

**2. Find the serial port:** macOS `ls /dev/cu.usbserial*`, Linux `ls /dev/ttyUSB*`, Windows Device Manager (`COM3`).

**3. Run the server (simulator needs no hardware, drop `PENARM_PORT`):**

    cd server
    uv sync && uv run pytest                                  # all tests should pass
    PENARM_PORT=/dev/cu.usbserial-XXXX uv run penarm-mcp      # Windows: PENARM_PORT=COM3

Opening the serial port **resets the Uno** (DTR), so the first command takes ~2 s and any drawing stored on the board stops. Only one process may hold the port at a time.

**4. Use it from an MCP client** (Claude Desktop/Code, etc.): command `uv`, args `["--directory", "/path/to/plotter/server", "run", "penarm-mcp"]`, env `PENARM_PORT=...`. Ask for `canvas_info` first; every tool draws in that canvas.

**5. Before drawing, calibrate:** `server/calibration.json` is git-ignored and **specific to one arm**: without it the server uses the defaults in `config.py` (sheet 200 x 275 mm, servo range 0-180), and your geometry will differ. See *Calibration* below. Check that the arm really moves with the servo test before blaming the software, and put the pen over a sheet only after a dry run (`dry_run=true`).

**Other things to know:** the pen has no lift (travel marks the paper), so give it a clean sheet; 30-45 mm/s is more accurate than 100 mm/s for long runs; do not touch the arm while it draws.

### Drawing that survives a disconnect, and resuming
- `set_output("board")`, draw as usual (it is stored in the Uno's EEPROM, nothing moves), then `run_on_board(loops)` (0 = forever). The board plays it alone: close the host and it keeps going. It stops when the port is opened again or on power loss. About 490 steps fit. Run it slower (30-40 mm/s) if the servos lose steps.
- `resume_drawing()` continues a cancelled or interrupted drawing from where the arm stands (the journal is `~/.penarm/journal.json`; it refuses if the arm was moved off the drawing's path).

### Rectangle calibration (how we ran it)
The kinematic fit leaves a position error of a few mm that **repeats** from drawing to drawing, so it can be corrected with a mesh (`penarm/mesh.py`) measured from a drawn rectangle. One iteration, on a **fresh sheet** (the pen has no lift, old ink confuses the reading):

    cd server && uv sync --all-extras
    uv run penarm-inkcal draw --port /dev/cu.usbserial-XXXX            # draws the canvas rectangle at 30 mm/s with the current mesh, parks the arm at the bottom middle

1. Photograph the **whole clipboard** from above, four corners in view, arm out of the way and nobody touching it. Any orientation works.
2. Open the **full-resolution** photo in an image viewer and note the pixel `x,y` of the four corners of the **clipboard board** (not the paper), labelled by what they are in the board frame: bottom = the edge nearest the servos, left/right as seen from the arm base looking away from it.
3. Measure (add `--mask x0,y0,x1,y1` in pixels for anything green that is not the drawing, e.g. the pen barrel; repeatable):

        uv run penarm-inkcal measure photo.jpg --corners "BLx,BLy BRx,BRy TRx,TRy TLx,TLy" --overlay check.png

   It prints the rectangle that was planned, the rms and max edge error in mm and how many positions on each edge were actually read. **Open `check.png`** (ink green, plan red): if the ink is missing pieces or picks up the pen, fix it with `--mask` before trusting any number.
4. If it looks right, run the same command with `--update-mesh` (folds the leftover error into `calibration.json`, gain 0.8), then `draw` again on a new sheet and repeat until the error stops shrinking (2-3 rounds).

The ink is read in Lab colour (the `a` channel drops below ~115 on green ink), not HSV saturation, which loses thin strokes. The correction only holds inside the measured rectangle, and the mesh belongs to the calibration it was measured with: after changing offsets/gains/lengths, delete the `mesh` key and start again. Do not measure the rectangle at the very edge of the reach (the arm saturates there and the mesh would extrapolate a limit, not an error). What did and did not work is in `docs/2026-10-28-movement-and-ink-calibration.md`.

## Layout
- `firmware` (PlatformIO, esp32dev): line protocol `?`, `V`, `A s1 s2` (OK on arrival), `R`. Servos GPIO18/19, pots GPIO34/35. Builds clean.
- `server` (uv): `config.py` = geometry + calibration (single source), `kinematics.py` = IK/FK, `arm.py` = owner of the draw cycle, `server.py` = MCP tools (`page_info`, `move_to`, `draw_polyline`, `get_state`). `PENARM_PORT` unset = simulator.

## Boards (ESP32 or Arduino Uno)
`firmware/src/config.h` is the only board-specific file (pins, servo lib, ADC range). Envs: `esp32`, `uno` (main firmware) and `servotest`, `servotest_uno` (standalone serial servo test: `1 90`, `2 90`, `c`, `s`, `r`).
Uno pins: proximal servo (1) D9, distal servo (2) D8, pots A0/A1 (10-bit ADC, 0..1023 vs ESP32's 0..4095; `?` reports `adcmax`). ESP32: servos GPIO18/19, pots GPIO34/35.

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
- Also `canvas_info`, `get_state`, `locate_pencil` (camera), `set_output` / `run_on_board` (drawing kept on the board), `resume_drawing`.

## Robustness
- One server per serial port (lock file); retries with a resend (every command is idempotent); automatic reconnect when the board goes silent.
- The firmware reports a `boot=<id>` that changes on every restart: the server notices a reset (brown-out, cable bump), re-syncs the arm's real pose and re-validates the stroke instead of drawing from a stale position.
- **Execution queue on the board:** the host streams sequence-numbered waypoints (`Q seq a b`) and stays ahead of the board (`S` status, `X` abort). The arm keeps moving through a slow or briefly lost link; a resent waypoint is never queued twice; a restart is detected from the sequence counter and reported instead of drawing from a stale pose. 64 waypoints on the Uno, 512 on the ESP32.
- `W <s>` makes the board release the servos after that long without commands (`idle_release_s`, default 120 s), so a dead host never leaves the pen pressing the paper.
- Tool schemas stay in the subset every provider's function calling accepts (no `$ref`, unions, consts or tuples; optional arguments use defaults, never null): `tests/test_schema_portability.py` guards it, and the server carries its own provider-neutral usage guide (MCP `instructions`).
- Tests run against a fake board that loses 40% of the replies like the CH340 clone (`tests/fakes.py`); the retry test goes red with `retries=1`.

## Calibration (`PENARM_MODE=calibrate`): the LLM delimits the paper
Offsets, signs and base are fitted from observations instead of being edited in code (`calibration.json`, git-ignored, applied on startup). The LLM does the measuring from ordinary photos:
1. `set_paper(width, height)` (default 200 x 275 mm).
2. For each pose (`calibration_poses`, `goto_servos`): take a photo, read the **four paper corners** and the **pen tip's contact point on the paper** in pixels, and call `record_photo_observation(corners, point_px)`. Corners are named from the arm's point of view (`near_left`, `near_right`, `far_right`, `far_left`, near = closest to the base); a homography maps pixels to paper mm, so a hand-held camera is fine. Use an ink dot or the pen touching the paper, not the holder (it sits above the paper and shifts with perspective).
3. `fit_calibration(scope)`: `base` (the paper moved: one photo re-registers it; offsets and lengths stay), `pose` (offsets, signs, base; >= 4 points), `full` (also link lengths; >= 7). It tries all sign combinations, reports the rmse in mm, saves and applies it, and the canvas is recomputed.
**Automatic reading of hand-held photos** (`analyze_photo`, `record_photo_observation_auto`; needs the `vision` extra, no markers, no fixed camera): the ruled block is found from the sheet's own ruled lines (dominant direction, the periodic run of lines, robust fits through the line ends), the pen holder is the circular hole in the blue plastic farthest from the servo cases, the shoulder is the servo farthest from it, and near/far/left/right come from where the arm is, so a rotated photo needs no help. The holder sits ~4-5 cm above the paper, so its pixel is pulled toward the image centre by the ratio between the hole's known diameter (11.4 mm) and the paper's local scale (the perspective factor `k`, ~1.3-1.5). A debug overlay PNG shows what was detected: look at it. In this mode the "paper size" is the size of the **ruled block** (measure it with a ruler), not of the sheet.
Honest limits, measured on 9 real phone photos of this arm: it accepted the 1 clean, flat sheet and got it right (corners, hole, shoulder); it refused the other 8 with a reason (heavy ink, a sheet torn in two halves, too oblique, too few visible lines), because a wrong quad is worse than none. On synthetic scenes it is within 1-3 px at any rotation; if the arm hides the extreme ruled line the block ends one line (~7 mm) short on that side. For the refused photos the LLM still reads the corners itself (`record_photo_observation`). A sturdier version would use the rigid clipboard as the reference frame and find the paper in the rectified image.
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
