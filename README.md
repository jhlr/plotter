# Pen plotter: LLM -> MCP -> Arduino -> 2 servos

A 2-link planar arm (two SG90 servos, 3D-printed parts) that draws what an LLM asks for. A Python server exposes drawing tools over MCP (Claude Desktop/Code, or any client that speaks MCP; there is also a Google ADK agent). The server turns shapes into servo angles and streams them to firmware on an Arduino Uno (ESP32 also supported). A phone photo of a drawn rectangle is used to correct the arm's position error.

    LLM  --MCP-->  server/ (Python: shapes, IK, calibration, jobs)  --serial-->  firmware/ (Uno)  -->  2 servos

The arm has **no pen lift**: travel moves mark the paper, so every drawing starts on a clean sheet and is one continuous trace.

## 1. What you need

| Item | Notes |
|---|---|
| Arduino Uno (or clone) | CH340 clones work; USB cable |
| 2 x SG90 servos | |
| 5 V supply, >= 2 A | **Servos never run from the Uno's 5 V pin.** Tie the supply GND to the Uno GND |
| 3D-printed parts | `pecas_impressao/`: `BASE.stl`, `ELO_1.stl`, `ELO_2.stl`, `SUPORTE_LAPIS.stl`, and `engrenagem_trilho.scad` / `.stl` (gear + servo coupling, one print) |
| A pen | Felt-tip or **ballpoint**, see "Choosing the pen" |
| A clipboard / flat board | Ours is 230 x 330 mm; the arm's base sits at its bottom edge. Any flat, rigid board works if you measure it |
| Paper, ruler, a phone | The phone photographs the calibration rectangle |
| Optional | 2 potentiometers on A0/A1 (not wired on our arm; not needed), a webcam for `locate_pencil` |

Software: [PlatformIO](https://platformio.org/install/cli) (`pio`) and [uv](https://docs.astral.sh/uv/) (Python >= 3.11). macOS, Linux and Windows.

Link lengths come from the CAD: shoulder axis to elbow axis 108.1 mm, elbow axis to pen hole 114.2 mm (a ruler gave 105 / 115 on the printed arm). If you scale or edit the parts, change `l1`/`l2` in `server/src/penarm/config.py`.

## 2. Wiring

| Signal | Uno pin |
|---|---|
| Proximal servo (shoulder, servo 1) | **D9** |
| Distal servo (elbow, servo 2) | **D8** |
| Pots (optional) | A0, A1 |

Pins live in one place, `firmware/src/config.h` (it also holds the ESP32 pins: servos GPIO18/19, pots GPIO34/35). If your servos are swapped the arm still moves but never matches the drawing; swap the two numbers in `config.h` or the cables.

## 3. Bring-up, in this order

**3.1 Test the servos alone, before any of our software.**

    cd firmware
    pio run -e servotest_uno -t upload
    pio device monitor -b 57600          # type: 1 60  |  2 120  |  s (sweep)  |  c (centre)

If a servo does not move here it is wiring or power, not software.

**3.2 Flash the real firmware.**

    pio run -e uno -t upload

Wait for **"verified"** at the end. A flash whose verify step fails (`avr_read(): error reading ...`) can leave a firmware that answers `OK` but never drives the servos. Flash again until it verifies.

**3.3 Run the tests (no hardware needed).**

    cd ../server
    uv sync --all-extras && uv run pytest        # all pass

**3.4 Find the serial port:** macOS `ls /dev/cu.usbserial*`, Linux `ls /dev/ttyUSB*`, Windows Device Manager (`COM3`). Opening the port resets the Uno (DTR): the first command takes ~2 s and any drawing stored on the board stops. Only one process may hold the port; the server takes a lock.

**3.5 Connect an MCP client.** Leave `PENARM_PORT` out to use the built-in simulator (no hardware, good for a first look).

Run `uv sync --all-extras` in `server/` once, then pick one:

**Claude Code (one line, from anywhere):**

    claude mcp add penarm -e PENARM_PORT=/dev/cu.usbserial-XXXX -- uv --directory /ABSOLUTE/PATH/plotter/server run penarm-mcp

(simulator: drop the `-e ...` part; Windows port: `COM3`). Check with `claude mcp list`, or `/mcp` inside a session. Add `-s user` to make it available in every project.

**Claude Desktop:** Settings -> Developer -> Edit Config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows), add, then restart the app:

    {
      "mcpServers": {
        "penarm": {
          "command": "uv",
          "args": ["--directory", "/ABSOLUTE/PATH/plotter/server", "run", "penarm-mcp"],
          "env": { "PENARM_PORT": "/dev/cu.usbserial-XXXX" }
        }
      }
    }

If the app cannot find `uv`, use its full path in `command` (`which uv`). Add `"PENARM_MODE": "calibrate"` to `env` for the pose calibration in section 5. Then ask: "call canvas_info". Only one client can hold the serial port at a time.

Without a client: `PENARM_PORT=/dev/cu.usbserial-XXXX uv run penarm-mcp`.

**3.6 Calibrate your arm (required: `calibration.json` is yours alone).** The defaults in `config.py` describe *our* arm. Your servo horns, base position and board differ, so a drawing without calibration will be the wrong size and shape. `server/calibration.json` is git-ignored and created by the steps below. Do these two stages in order:

1. **Pose calibration** (section 5): fits servo offsets/signs, the base position and the board size from a few photos.
2. **Rectangle calibration** (section 6): draws a rectangle, measures it from a photo and builds a correction mesh. Repeat 2-3 times.

**3.7 Draw.** Put a **clean sheet** under the pen, ask for `canvas_info` first (every tool draws inside that canvas), then try `dry_run=true` on anything new. The first real drawing should be small and well inside the sheet. Do not touch the arm while it draws.

## 4. Choosing the pen

Anything that marks the paper works for drawing. For the **rectangle calibration** the photo is read by colour, so tell the tool which ink it is:

| Pen | `penarm-inkcal measure ... --ink` |
|---|---|
| green felt-tip (what we used, the default) | `green` |
| blue ballpoint | `blue` |
| red | `red` |
| black / very dark blue | `dark` |

A ballpoint line is thinner and paler than a felt-tip: photograph close and sharp (full-resolution file), under even light with no shadow of the arm or your hand, and always open the `--overlay` image to confirm the ink was picked up (ink in green, plan in red) before trusting a number. A `dark` ink is judged against the photo's own paper brightness, so shadows and a dark board edge count as ink: use `--mask x0,y0,x1,y1` (pixels, repeatable) to hide the pen barrel, the arm, or anything else that is not the drawing. A ballpoint needs more downward force than a felt-tip, which adds friction and makes the arm lag; draw slowly (30-45 mm/s) and expect a bigger initial error than ours.

## 5. Pose calibration (`PENARM_MODE=calibrate`)

Start the server with `PENARM_MODE=calibrate` so the extra tools appear. The LLM does the measuring from ordinary photos, no markers.

1. `set_paper(width, height)`: your board in mm (ours: 230 x 330; the default is 200 x 275).
2. For each pose in `calibration_poses` (`goto_servos`): take a photo with the pen touching the paper, read the **four paper corners** and the **pen contact point** in pixels, and call `record_photo_observation(corners, point_px)`. Corners are named from the arm's point of view (`near_left`, `near_right`, `far_right`, `far_left`; near = closest to the base). A homography maps pixels to paper mm, so a hand-held camera is fine. Use an ink dot or the pen touching the paper, not the holder (it sits ~4-5 cm above the paper and shifts with perspective).
3. `fit_calibration(scope)`: `base` (the paper moved: one photo re-registers it), `pose` (offsets, signs, base; needs >= 4 points), `full` (also link lengths; >= 7). It tries all sign combinations, reports the rmse in mm, saves and applies it. The canvas is recomputed.

**Remove the pen for this stage** if you can: a calibration pose that drags a pen across your desk is a bad way to find out the mapping is wrong. Order: no pen -> validate the mapping -> small drawing inside the sheet.

Automatic reading of hand-held photos (`analyze_photo`, `record_photo_observation_auto`, needs the `vision` extra) finds the ruled block, pen holder and shoulder on its own. It is conservative: of 9 real phone photos it accepted the one clean, flat sheet and refused the other 8 with a reason, because a wrong quadrilateral is worse than none. When it refuses, the LLM reads the corners itself with `record_photo_observation`. Ruler measurements work too (`record_calibration_point`). The fitter is pure-Python Levenberg-Marquardt, tested on synthetic perspective photos (offsets < 0.2 deg, base < 0.5 mm).

## 6. Rectangle calibration (`penarm-inkcal`)

The fit leaves a position error of a few mm that **repeats** from drawing to drawing, so it can be corrected with a mesh (`penarm/mesh.py`) measured from a drawn rectangle. One iteration, on a **fresh sheet**:

    cd server
    uv run penarm-inkcal draw --port /dev/cu.usbserial-XXXX

It draws the canvas rectangle at 30 mm/s with the current mesh and parks the arm at the bottom middle (so it does not cover a corner).

1. Photograph the **whole board** from above, four corners in view, nobody touching the arm. Any orientation works.
2. Open the **full-resolution** photo in an image viewer and note the pixel `x,y` of the four corners of the **board** (not the paper), named by what they are in the board frame: BL = the corner nearest the servos on the left, BR, TR, TL going round. Do not name them by where they land in the photo.
3. Measure:

        uv run penarm-inkcal measure photo.jpg --corners "BLx,BLy BRx,BRy TRx,TRy TLx,TLy" --ink green --overlay check.png

   It prints the planned rectangle, the rms and max edge error in mm, and how many positions on each edge were read. **Open `check.png`.** If pieces of the ink are missing or it picked up the pen, fix it with `--mask` or `--ink` first.
4. If it looks right, run the same command with `--update-mesh` (folds the leftover error into `calibration.json`, gain 0.8). Draw again on a **new** sheet and repeat until the error stops shrinking (2-3 rounds). Our rms went from ~11 mm to 4-7 mm and the median to ~2.4-3.6 mm.

Rules that cost us rounds:
- The mesh only holds inside the measured rectangle, and it belongs to the calibration it was measured with. After changing offsets, gains or lengths, delete the `mesh` key and start again.
- Do not measure at the very edge of the reach: the arm saturates there and the mesh would extrapolate a limit, not an error.
- Old ink confuses the reading, and the back of a sheet shows through: use a fresh sheet every round.
- Always confirm with a human that the arm actually moved before saying "drawn": the board can answer `OK` without moving the servos (see Troubleshooting).

What worked and what did not (curves per servo, backlash, free link lengths: none generalised) is in `docs/2026-10-28-movement-and-ink-calibration.md`.

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Board answers `OK`, servos do not move | Bad flash. Reflash `-e uno` until avrdude prints "verified" |
| Servo twitches or the Uno resets | Servos powered from the Uno, or no common GND |
| Drawing is mirrored, rotated, or the arm goes elsewhere | Servos swapped (`config.h`) or wrong signs: redo pose calibration |
| Half the replies are lost | Baud. We run 57600; at 115200 a CH340 clone dropped ~40%. The Windows CH340 driver (3.9) refuses to configure a port at the baud it already has, so `SerialLink` opens at 9600, switches once, never reconfigures |
| First command takes ~2 s / stored drawing stopped | Opening the serial port resets the Uno |
| "port busy" | Another server holds the lock (one per serial port) |
| Drawings come out small and wobbly | Pen friction makes the joints lag; draw slower (30-45 mm/s was more accurate than 100 for long runs), calibrate with the mesh |
| Servo loses steps in a long run | Lower the speed; 100 mm/s once dropped the USB in an infinite loop |
| `resume_drawing` refuses | The arm was moved off the drawing's path |

## 8. Using it

### Canvas and tools
The server computes a **canvas**: the largest rectangle the arm can fully reach (grid scan of the IK), in its own mm frame (origin bottom-left). `set_canvas` switches to a tall `portrait` / `portrait_left` / `portrait_right` area. Drawing tools take canvas coordinates only, so the LLM never sees page or servo geometry. All of them build **strokes** and go through one entry that validates the whole drawing before anything moves:
- `draw_path` (move/line/arc/bezier/quad/close, plus `transform` and `fit`), `draw_svg_path` (SVG `d` strings), `draw_shape` (circle, ellipse, rectangle, square, polygon, triangle, star, spiral, heart, hatch, wave), `draw_polyline`, `draw_line`, `draw_bezier`, `move_to`.
- `dry_run=true` on any of them returns bbox, length, estimated time, an ASCII thumbnail and an SVG, and moves nothing.
- Drawings run as **jobs**: a call waits `PENARM_SYNC_WAIT` s (default 20), then returns a `job_id` to poll with `job_status`; `stop()` cancels within a millimetre. One job at a time.
- Also `canvas_info`, `get_state`, `locate_pencil` (camera), `set_output` / `run_on_board`, `resume_drawing`.

### Drawing that survives a disconnect, and resuming
- `set_output("board")`, draw as usual (it is stored in the Uno's EEPROM, nothing moves), then `run_on_board(loops)` (0 = forever). The board plays it alone. It stops when the port is opened again or on power loss. About 490 steps fit. Run it at 30-40 mm/s if the servos lose steps.
- `resume_drawing()` continues a cancelled or interrupted drawing from where the arm stands (journal at `~/.penarm/journal.json`).

### Environment variables
`PENARM_PORT` (unset = simulator), `PENARM_MODE=calibrate`, `PENARM_SYNC_WAIT` (default 20), `PENARM_CAMERA` (device index or stream URL), `PENARM_CALIBRATION` (path, default `calibration.json` in the working directory), `PENARM_JOURNAL`.

## 9. How it is built

- `firmware/` (PlatformIO). Line protocol over serial at 57600: `?`, `V`, `A s1 s2`, `R`, `W <s>` (release servos after that idle time, default 120 s), timed segments `Q seq a b [ms]` with status `S` and abort `X`, EEPROM program `PB/PD/PE/PI/G`. Envs: `uno`, `esp32` (main firmware), `servotest`, `servotest_uno` (standalone test), `idle_uno` (never drives the servos: use it to stop the arm safely). Boot starts with servos released so a reset never moves the arm.
- `server/src/penarm/`: `config.py` geometry + calibration (single source of truth), `kinematics.py` IK/FK, `arm.py` owner of the draw cycle, `server.py` MCP tools, `calibration.py`, `mesh.py`, `inkcal.py`, `photocv.py`, `profile.py` (speed profile: 100 mm/s, 600 mm/s^2, 180 deg/s defaults), `journal.py`, `jobs.py`, `link.py`.
- **Robustness:** one server per port (lock file); every command is idempotent and retried; automatic reconnect when the board goes silent. The board reports a `boot=<id>` that changes on every restart, so the server notices a reset (brown-out, cable bump), re-syncs the real pose and re-validates the stroke. The host stays ahead of the board's queue (64 waypoints on the Uno, 512 on the ESP32); a resent waypoint is never queued twice. Tests run against a fake board that loses 40% of replies like the CH340 clone (`tests/fakes.py`).
- **Portable tool schemas:** no `$ref`, unions, consts or tuples; optional arguments use defaults, never null. `tests/test_schema_portability.py` guards it, and the server carries its own provider-neutral usage guide (MCP `instructions`).

### Vision (optional)
An overhead camera gives the LLM `locate_pencil` numbers (x/y mm, frames seen, spread, error vs the kinematic estimate), never frames. `uv run penarm-markers` writes `markers/marker_{0..3}.png`; print them at 20 mm and stick them where `VisionConfig` says. The pencil tag is a green blob (tune `hsv_lo/hsv_hi`). Set `PENARM_CAMERA=0` to enable. Tested only on a synthetic perspective scene (< 1 mm), not on a real camera.

### Agent (Google ADK)
`agent/` is a separate uv project (ADK pins `mcp<2`, the server uses mcp 2.x). `root_agent` runs any LLM via `PENARM_MODEL` (`gemini-*` native; `provider/model` goes through LiteLLM, e.g. `anthropic/claude-sonnet-5-5`, `openai/gpt-4o`, `ollama_chat/llama3.1`) and spawns the MCP server over stdio.

    cd agent && export PENARM_MODEL=anthropic/claude-sonnet-5-5 ANTHROPIC_API_KEY=...
    uv run penarm-chat          # terminal loop
    uv run adk web .            # ADK dev UI

## 10. Known limits / TODO
1. Error dominates at the small scale: SG90 dead band + pen friction + the thin end of link 2 flexing. Large drawings come out more faithful than small ones (the error is roughly constant). Stiffen link 2.
2. Pots are not wired, so there is no closed loop. Wiring them (A0/A1) is the biggest accuracy gain left.
3. Pen lift (3rd servo) -> `pen_up`/`pen_down` tools.
4. The kinematic ink fit used to get the offsets/gains was done with scratch scripts, not a packaged command; new arms use the photo pose fit (section 5) plus the mesh (section 6).
