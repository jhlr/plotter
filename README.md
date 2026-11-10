# Pen plotter you drive with any LLM agent (MCP)

A 2-link planar arm (two SG90 servos, 3D-printed parts, an Arduino Uno) that draws what an AI agent asks for. The brain is an **MCP server** (`server/`): any agent that speaks MCP can connect and call tools like `draw_shape`, `draw_arc` or `draw_svg_path`. It works with **any pen, pencil or marker**: nothing in the software depends on the ink.

    agent (any MCP client)  --MCP/stdio-->  server/ (Python: shapes, IK, jobs)  --serial-->  firmware/ (Uno)  -->  2 servos

The arm has **no pen lift**: travel moves mark the paper, so each drawing starts on a clean sheet and is one continuous trace.

> **Handing this repo to an AI agent?** Point it at [`AGENTS.md`](AGENTS.md): it is the step-by-step runbook an agent can follow, and says which steps need a human (wiring, flashing, swapping the sheet, taking a photo).

## 0. Try it in 2 minutes, no hardware

You need [uv](https://docs.astral.sh/uv/) and Python >= 3.11. The simulator is built in; it draws nothing physical but runs every tool.

    git clone https://github.com/jhlr/plotter && cd plotter
    make setup                      # or: cd server && uv sync --all-extras && uv run pytest

Then connect your agent. The server is a plain **stdio MCP server**, so every client needs the same three things:

| | |
|---|---|
| command | `uv` |
| args | `["--directory", "/ABSOLUTE/PATH/plotter/server", "run", "penarm-mcp"]` |
| env | `PENARM_PORT=<serial port>` for the real arm, **leave it unset for the simulator** |

- **Claude Code**, from inside the cloned repo: it picks up the committed [`.mcp.json`](.mcp.json) on its own (approve it when asked). Or add it anywhere with `claude mcp add penarm -e PENARM_PORT=/dev/cu.usbserial-XXXX -- uv --directory /ABSOLUTE/PATH/plotter/server run penarm-mcp` (drop `-e ...` for the simulator, add `-s user` for every project).
- **Claude Desktop** and most other clients (Cursor, Windsurf, Cline, ...) use the same JSON shape in their MCP settings file (Claude Desktop: Settings -> Developer -> Edit Config):

        {
          "mcpServers": {
            "penarm": {
              "command": "uv",
              "args": ["--directory", "/ABSOLUTE/PATH/plotter/server", "run", "penarm-mcp"],
              "env": { "PENARM_PORT": "/dev/cu.usbserial-XXXX" }
            }
          }
        }

  If the app cannot find `uv`, put its full path (`which uv`) in `command`. Restart the client after editing.
- **Your own agent or script**: any MCP SDK client works (`StdioServerParameters(command="uv", args=[...])`).
- **Without a client**: `make sim`, or `PENARM_PORT=... uv run penarm-mcp`.
- **No LLM at all, plain Python**: the MCP tools are just the methods of one class, `Plotter`. See `examples/hello.py`:

        from penarm import Plotter
        p = Plotter()                                    # no port = simulator; Plotter("/dev/cu.usbserial-10") = the arm
        p.draw_shape("heart", cx=80, cy=30, size=30)   # blocks until drawn; dry_run=True only previews

  Run it from any folder with `uv run examples/hello.py` (it installs `penarm` itself). The methods are `draw_shape`, `draw_line`, `draw_arc`, `draw_polyline`, `draw_bezier` and `draw_svg_path`. `p.canvas.w` / `p.canvas.h` give the size. See `examples/manual_vs_llm.md` for the same drawing by hand and by prompt. Whatever the LLM can do through MCP, you can do by hand with the same names and arguments; that is the point of the course: write the 3 lines yourself, then ask the LLM to do the creative part.

Then ask the agent: *"call `canvas_info`, then draw a heart with `dry_run=true`"*. The server ships its own usage guide (MCP `instructions`), so the agent needs no other prompt. Only one process can hold the serial port at a time.

When you move to hardware, follow sections 1-3 and 5-6 below.

## 1. What you need

| Item | Notes |
|---|---|
| Arduino Uno (or clone) | CH340 clones work; USB cable |
| 2 x SG90 servos | |
| 5 V supply, >= 2 A | **Servos never run from the Uno's 5 V pin.** Tie the supply GND to the Uno GND |
| 3D-printed parts | `pecas_impressao/`: `BASE.stl`, `ELO_1.stl`, `ELO_2.stl`, `SUPORTE_LAPIS.stl`, and `engrenagem_trilho.scad` / `.stl` (gear + servo coupling, one print) |
| A pen | Any pen or marker, see section 4 |
| A clipboard / flat board | Ours is 230 x 330 mm; the arm's base sits at its bottom edge. Any flat, rigid board works if you measure it |
| Paper, ruler, a phone | The phone photographs the calibration rectangle |
| Optional | 2 potentiometers on A0/A1 (not wired on our arm; not needed) |

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

    make setup          # uv sync --all-extras && uv run pytest in server/; all pass

**3.4 Find the serial port:** macOS `ls /dev/cu.usbserial*`, Linux `ls /dev/ttyUSB*`, Windows Device Manager (`COM3`). Opening the port resets the Uno (DTR): the first command takes ~2 s and any drawing stored on the board stops. Only one process may hold the port; the server takes a lock.

**3.5 Connect your agent** exactly as in section 0, now with `PENARM_PORT` set to the port from 3.4 (on Windows `COM3`). Ask for `canvas_info`: `"simulated": false` confirms it is talking to the board.

**3.6 Calibrate your arm (required: `calibration.json` is yours alone).** The defaults in `config.py` describe *our* arm. Your servo horns, base position and board differ, so a drawing without calibration will be the wrong size and shape. `server/calibration.json` is git-ignored. Do these two stages in order:

1. **Arm parameters** (section 5): set the board size, base position and servo offsets by hand.
2. **Rectangle calibration** (section 6): draws a rectangle, measures it from a photo and builds a correction mesh. Repeat 2-3 times.

**3.7 Draw.** Put a **clean sheet** under the pen, ask for `canvas_info` first (every tool draws inside that canvas), then try `dry_run=true` on anything new. The first real drawing should be small and well inside the sheet. Do not touch the arm while it draws.

## 4. Any pen works

Ballpoint, felt-tip, gel, pencil, a dry-erase marker on a whiteboard: the arm only needs something that marks the surface. The pen holder (`SUPORTE_LAPIS.stl`) has an **11.4 mm** hole: wrap thinner pens in tape or paper until they sit tight, and the tip must just touch the paper with the arm at rest.

The **rectangle calibration** (section 6) reads the line from a photo, and that reader is colour-agnostic: by default (`--ink auto`) anything clearly darker or more coloured than the paper around it counts as ink, so shadows and uneven light are ignored. It does not matter whether the pen is black, blue, red or green. What does matter:
- **Contrast.** A pale pen (yellow highlighter, light pencil on cream paper) can fall below the threshold. Use a pen that is clearly visible in the photo; the tool tells you when it finds too little.
- **A sharp, evenly lit full-resolution photo**, taken close, with no shadow of your hand. Thin ballpoint lines need this more than a felt-tip.
- **Always open the `--overlay` image** and check that the ink was picked up (ink in green, plan in red *in the overlay*; that colour is the debug drawing, not your pen). Hide anything that is not the drawing (the pen barrel, the arm) with `--mask x0,y0,x1,y1` (pixels, repeatable).
- If `auto` picks up the wrong things, name a colour with `--ink green|blue|red|brown|dark` (`dark` = black or very dark ink, judged against the photo's own paper brightness).

A ballpoint needs more downward force than a felt-tip, which adds friction and makes the arm lag: draw slowly (30-45 mm/s) and expect a bigger initial error than ours (we calibrated with a felt-tip).

## 5. Arm angles: nothing to calibrate if you assemble at the assembly pose

The defaults in `server/src/penarm/config.py` describe the reference kit and hold for any kit built like it. Do not measure anything: send the servos to the assembly pose and mount the horns there.

    cd server
    uv run penarm-assemble --port /dev/cu.usbserial-XXXX

The servos go to the angles where the arm must be **straight** (link 1 along the board's centre line, away from the servos; link 2 aligned with it). Mount both horns that way and tighten. The elbow always bends to the board's left, away from the electronics. Then go straight to section 6 (the rectangle).

Only if the drawing is clearly rotated or scaled after the rectangle, override a number in `server/calibration.json` (git-ignored): `{"params": {"offset2": 133.0}}`. Fields: `page_w`, `page_h`, `base_x`, `base_y`, `offset1`, `offset2`, `sign1`, `sign2`, `l1`, `l2`, `canvas_left_mm`, `canvas_bottom_mm`, `canvas_right_mm`, `canvas_top_mm` (the four edges of the drawing rectangle in board mm; you place them, the code checks they are reachable) (`joint = sign * (servo - offset)`). Re-deriving them from photos is the skill `calibrate-angles`, a last resort. Whatever error is left (a few mm that repeat) is what section 6 corrects.

## 6. Rectangle calibration (`penarm-inkcal`)

The fit leaves a position error of a few mm that **repeats** from drawing to drawing, so it can be corrected with a mesh (`penarm/mesh.py`) measured from a drawn rectangle. One iteration, on a **fresh sheet**:

    cd server
    uv run penarm-inkcal draw --port /dev/cu.usbserial-XXXX

It draws the canvas rectangle at 30 mm/s with the current mesh and parks the arm at the bottom middle (so it does not cover a corner).

1. Photograph the **whole board** from above, four corners in view, nobody touching the arm. Any orientation works.
2. Open the **full-resolution** photo in an image viewer and note the pixel `x,y` of the four corners of the **board** (not the paper), named by what they are in the board frame: BL = the corner nearest the servos on the left, BR, TR, TL going round. Do not name them by where they land in the photo.
3. Measure:

        uv run penarm-inkcal measure photo.jpg --corners "BLx,BLy BRx,BRy TRx,TRy TLx,TLy" --overlay check.png

   It prints the planned rectangle, the rms and max edge error in mm, and how many positions on each edge were read. **Open `check.png`.** If pieces of the ink are missing or it picked up the pen or the arm, fix it with `--mask` (or name the colour with `--ink`) first.
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
| Drawing is mirrored, rotated, or the arm goes elsewhere | Servos swapped (`config.h`) or wrong signs: flip `sign1`/`sign2` (section 5) |
| Half the replies are lost | Baud. We run 57600; at 115200 a CH340 clone dropped ~40%. The Windows CH340 driver (3.9) refuses to configure a port at the baud it already has, so `SerialLink` opens at 9600, switches once, never reconfigures |
| First command takes ~2 s / stored drawing stopped | Opening the serial port resets the Uno |
| "port busy" | Another server holds the lock (one per serial port) |
| Drawings come out small and wobbly | Pen friction makes the joints lag; draw slower (30-45 mm/s was more accurate than 100 for long runs), calibrate with the mesh |
| Servo loses steps in a long run | Lower the speed; 100 mm/s once dropped the USB in an infinite loop |

## 8. Using it

### Canvas and tools
The server computes a **canvas**: the largest rectangle the arm can fully reach (grid scan of the IK), in its own mm frame (origin bottom-left). Drawing tools take canvas coordinates only, so the LLM never sees page or servo geometry. All of them build **strokes** and go through one entry that validates the whole drawing before anything moves:
- `draw_svg_path` (SVG `d` strings, scaled into a box you give), `draw_shape` (circle, ellipse, rectangle, square, polygon, triangle, star, spiral, heart, hatch, wave), `draw_polyline`, `draw_line`, `draw_arc`, `draw_bezier`.
- `dry_run=true` on any of them returns bbox, length, estimated time, an ASCII thumbnail and an SVG, and moves nothing.
- Drawings run as **jobs**: a call waits `PENARM_SYNC_WAIT` s (default 20), then returns a `job_id` to poll with `job_status`; `stop()` cancels within a millimetre. One job at a time.
- Also `canvas_info` and `get_state`.

### Environment variables
`PENARM_PORT` (unset = simulator), `PENARM_SYNC_WAIT` (default 20), `PENARM_CALIBRATION` (path, default `calibration.json` in the working directory).

## 9. How it is built

- `firmware/` (PlatformIO). Line protocol over serial at 57600: `?`, `V`, `A s1 s2`, `R`, `W <s>` (release servos after that idle time, default 120 s), timed segments `Q seq a b [ms]` with status `S` and abort `X`, EEPROM program `PB/PD/PE/PI/G` (still in the firmware, no longer used by the server). Envs: `uno`, `esp32` (main firmware), `servotest`, `servotest_uno` (serial test), `servoloop_uno` (no computer: both servos sweep by themselves in a loop; `make servoloop PORT=...`), `idle_uno` (never drives the servos: use it to stop the arm safely). Boot starts with servos released so a reset never moves the arm.
- `server/src/penarm/`: `config.py` geometry (single source of truth), `kinematics.py` IK/FK, `arm.py` owner of the draw cycle, `plotter.py` the one class that draws (use it from Python), `server.py` registers its methods as MCP tools, `calibration.py` (calibration.json), `mesh.py`, `inkcal.py`, `profile.py` (speed profile: 100 mm/s, 600 mm/s^2, 180 deg/s defaults), `jobs.py`, `link.py`.
- **Robustness:** one server per port (lock file); every command is idempotent and retried; automatic reconnect when the board goes silent. The board reports a `boot=<id>` that changes on every restart, so the server notices a reset (brown-out, cable bump), re-syncs the real pose and re-validates the stroke. The host stays ahead of the board's queue (64 waypoints on the Uno, 512 on the ESP32); a resent waypoint is never queued twice. Tests run against a fake board that loses 40% of replies like the CH340 clone (`tests/fakes.py`).
- **Portable tool schemas:** no `$ref`, unions, consts or tuples; optional arguments use defaults, never null. `tests/test_schema_portability.py` guards it, and the server carries its own provider-neutral usage guide (MCP `instructions`).

## 10. Known limits / TODO
1. Error dominates at the small scale: SG90 dead band + pen friction + the thin end of link 2 flexing. Large drawings come out more faithful than small ones (the error is roughly constant). Stiffen link 2.
2. Pots are not wired, so there is no closed loop. Wiring them (A0/A1) is the biggest accuracy gain left.
3. Pen lift (3rd servo) -> `pen_up`/`pen_down` tools.
4. The kinematic ink fit used to get the offsets/gains was done with scratch scripts, not a packaged command; new arms set the parameters by hand (section 5) plus the mesh (section 6).

## 11. License
GNU GPL v3 or later (`LICENSE`), a copyleft license: you can use, study, change and share this project, but anything you distribute that is based on it must stay under the same terms with its source available. It covers the code, the firmware, the docs, and the printable parts in `pecas_impressao/`.
