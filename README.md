# Pen plotter you drive with any LLM agent (MCP)

A 2-link planar arm (two SG90 servos, 3D-printed parts, an Arduino Uno) that draws what an AI agent asks for. The brain is an **MCP server** (`server/`): any agent that speaks MCP can connect and call tools like `draw_shape`, `draw_arc` or `draw_svg_path`. It works with **any pen, pencil or marker**: nothing in the software depends on the ink.

    agent (any MCP client)  --MCP/stdio-->  server/ (Python: shapes, IK, jobs)  --serial-->  firmware/ (Uno)  -->  2 servos

The arm has **no pen lift**: travel moves mark the paper, so each drawing starts on a clean sheet and is one continuous trace.

> **Handing this repo to an AI agent?** For the **workshop**, [`AGENTS.md`](AGENTS.md) holds the rules and the current stage (SETUP, FASE 2 no abstraction, FASE 3 with MCP); `python fase.py setup|2|3` switches it, from `workshop/agents.md`. For **flashing and calibrating**, [`docs/runbook-hardware.md`](docs/runbook-hardware.md) is the step-by-step runbook, and says which steps need a human (wiring, flashing, swapping the sheet, taking the calibration photo).

## 0. Try it in 2 minutes, no hardware

You need Python >= 3.11. Everything lives in one virtual environment, `.venv/`, at the repo root. The simulator is built in; it draws nothing physical but runs every tool.

    git clone https://github.com/jhlr/plotter && cd plotter
    python setup.py                 # any OS (Windows: py setup.py): creates .venv, installs penarm, finds the board's USB port, checks the simulator
    source .venv/bin/activate       # Windows: .venv\Scripts\activate; after this `python` and `penarm-*` use the venv
    make setup                      # optional, macOS/Linux: the same plus the full test suite

> **`make` is for macOS and Linux only.** Windows has no `make`: use `py setup.py`, activate with `.venv\Scripts\activate`, and run the commands directly (`penarm-mcp` instead of `make sim`, `pytest` from `server/` instead of `make check`, and for flashing `pio run -d firmware -e uno -t upload --upload-port COM3`).

Then connect your agent. The server is a plain **stdio MCP server**, so every client needs the same three things:

| | |
|---|---|
| command | `/ABSOLUTE/PATH/plotter/.venv/bin/penarm-mcp` (Windows: `...\.venv\Scripts\penarm-mcp.exe`) |
| args | none |
| env | `PENARM_PORT=<serial port>` for the real arm, **leave it unset for the simulator** |

- **Claude Code**, from inside the cloned repo: it picks up the committed [`.mcp.json`](.mcp.json) on its own (approve it when asked). Or add it anywhere with `claude mcp add penarm -e PENARM_PORT=/dev/cu.usbserial-XXXX -- /ABSOLUTE/PATH/plotter/.venv/bin/penarm-mcp` (drop `-e ...` for the simulator, add `-s user` for every project).
- **opencode**, from inside the repo with `.venv` active: it reads the committed [`opencode.json`](opencode.json) (the server and the workshop's model provider). `python setup.py` writes the board's port into it.
- **Claude Desktop** and most other clients (Cursor, Windsurf, Cline, ...) use the same JSON shape in their MCP settings file (Claude Desktop: Settings -> Developer -> Edit Config):

        {
          "mcpServers": {
            "penarm": {
              "command": "/ABSOLUTE/PATH/plotter/.venv/bin/penarm-mcp",
              "env": { "PENARM_PORT": "/dev/cu.usbserial-XXXX" }
            }
          }
        }

  Use the full path to the venv's `penarm-mcp`, so the app needs no PATH. Restart the client after editing.
- **Your own agent or script**: any MCP SDK client works (`StdioServerParameters(command=".venv/bin/penarm-mcp")`).
- **Without a client**: `penarm-mcp` (simulator), or `PENARM_PORT=... penarm-mcp` for the real arm. `make sim` does the first one on macOS/Linux.
- **No LLM at all, plain Python**: the MCP tools are just the methods of one class, `Plotter`. See `examples/hello.py` (or `examples/phase1.py`, which finds the board's port by itself with `find_port()`):

        from penarm import Plotter
        p = Plotter()                                    # no port = simulator; Plotter("/dev/cu.usbserial-10") = the arm
        p.draw_shape("heart", cx=80, cy=30, size=30)   # blocks until drawn; dry_run=True only previews

  Run it from any folder with `python examples/hello.py` (it installs `penarm` itself). The methods are `draw_shape`, `draw_line`, `draw_arc`, `draw_polyline`, `draw_bezier` and `draw_svg_path`. `p.canvas.w` / `p.canvas.h` give the size. See `examples/manual_vs_llm.md` for the same drawing by hand and by prompt. Whatever the LLM can do through MCP, you can do by hand with the same names and arguments; that is the point of the course: write the 3 lines yourself, then ask the LLM to do the creative part.

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
| Paper, a phone | The phone photographs the calibration rectangle |
| Optional | 2 potentiometers on A0/A1 (not wired on our arm; not needed) |

Software: [PlatformIO](https://platformio.org/install/cli) (`pio`) and Python >= 3.11 with `venv`. macOS, Linux and Windows.

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

    make setup          # macOS/Linux. python -m venv .venv, pip install -e server[dev], pytest; all pass. On Windows: py setup.py, then pytest in server/

**3.4 Find the serial port:** macOS `ls /dev/cu.usbserial*`, Linux `ls /dev/ttyUSB*`, Windows Device Manager (`COM3`). Opening the port resets the Uno (DTR): the first command takes ~2 s and any drawing stored on the board stops. Only one process may hold the port; the server takes a lock.

**3.5 Connect your agent** exactly as in section 0, now with `PENARM_PORT` set to the port from 3.4 (on Windows `COM3`). Ask for `canvas_info`: `"simulated": false` confirms it is talking to the board.

**3.6 Calibrate your arm (about 10 minutes, `calibration.json` is yours alone).** The defaults in `config.py` describe *our* arm; yours differs by a few degrees. Two steps, in this order (section 5): **assemble** at the assembly pose, then **draw a rectangle and photograph it once**.

**3.7 Draw.** Put a **clean sheet** under the pen, ask for `canvas_info` first (every tool draws inside that canvas), then try `dry_run=true` on anything new. The first real drawing should be small and well inside the sheet. Do not touch the arm while it draws.

## 4. Any pen works

Ballpoint, felt-tip, gel, pencil, a dry-erase marker on a whiteboard: the arm only needs something that marks the surface. The pen holder (`SUPORTE_LAPIS.stl`) has an **11.4 mm** hole: wrap thinner pens in tape or paper until they sit tight, and the tip must just touch the paper with the arm at rest.

The calibration photo (section 5) reads the line by colour (`--ink auto` takes anything clearly different from the paper), so any pen works if the line is clearly visible in a sharp, evenly lit photo.

A ballpoint needs more downward force than a felt-tip, which adds friction and makes the arm lag: draw slowly (30-45 mm/s) and expect a bigger initial error than ours (we calibrated with a felt-tip).

## 5. Calibration: assemble, draw the rectangle, one photo

**Step 1, assemble (no measuring).** Send the servos to the assembly pose and mount both horns there, arm straight (link 1 along the board's centre line, away from the servos; link 2 aligned). The elbow always bends to the board's left, away from the electronics.

    cd server
    penarm-assemble --port /dev/cu.usbserial-XXXX

**Step 2, draw.** Pen in, **clean sheet**:

    penarm-calibrate draw --port /dev/cu.usbserial-XXXX

It draws the canvas rectangle at 30 mm/s and parks the arm at the bottom middle.

**Step 3, one photo.** Photograph the **whole board** from above, four corners in view, nobody touching the arm. Open the full-resolution photo and note the pixel `x,y` of the four corners of the **board** (not the paper), named by what they are in the board frame: BL = the corner nearest the servos on the left, then BR, TR, TL going round. Do not name them by where they land in the photo.

**Step 4, measure and look.**

    penarm-calibrate measure photo.jpg --corners "BLx,BLy BRx,BRy TRx,TRy TLx,TLy" --overlay check.png

It prints the planned and the drawn position of the four edges (left x, right x, bottom y, top y, in board mm). **Open `check.png`** (ink in green, plan in red): if it picked up the pen or the arm, hide them with `--mask x0,y0,x1,y1` (pixels, repeatable); if it misses the line, name the colour with `--ink green|blue|red|brown|dark` (default `auto` works with any pen).

**Step 5, fit.** Same command with `--save`:

    penarm-calibrate measure photo.jpg --corners "..." --save

The four edge positions fix the four unknowns (gain and horn offset of each servo); the fit goes into `~/.penarm/calibration.json` (the previous file is kept as `calibration.json.bak-prev`). Draw again on a **new sheet** and measure again: when the drawn edges sit on the plan (a few mm), you are done. One or two rounds. If you measured the four edge positions some other way (a ruler, say), `penarm-calibrate fit XL XR YB YT` saves them directly.

Rules that cost us time:
- Fresh sheet every round (old ink confuses the reading, and the back of a sheet shows through).
- Never trust a measurement you have not looked at: open the overlay.
- Tighten the horns before drawing: a loose horn makes edges that fit no arm, and the fit says so.
- Always confirm with a human that the arm really moved before saying "drawn": the board can answer `OK` without moving the servos (see Troubleshooting).
- The servos need their own external 5 V (with the ground shared with the Arduino). From USB alone the board can lock up as soon as the arm moves.

Hand-editable fields in `calibration.json`: `page_w`, `page_h`, `base_x`, `base_y`, `offset1`, `offset2`, `sign1`, `sign2`, `l1`, `l2`, `canvas_left_mm`, `canvas_bottom_mm`, `canvas_right_mm`, `canvas_top_mm` (`joint = sign * (servo - offset)`; the canvas edges are board mm that you place and the code checks are reachable).

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Board answers `OK`, servos do not move | Bad flash. Reflash `-e uno` until avrdude prints "verified" |
| Servo twitches or the Uno resets | Servos powered from the Uno, or no common GND |
| Drawing is mirrored, rotated, or the arm goes elsewhere | Servos swapped (`config.h`) or wrong signs: flip `sign1`/`sign2` (section 5) |
| Half the replies are lost | Baud. We run 57600; at 115200 a CH340 clone dropped ~40%. The Windows CH340 driver (3.9) refuses to configure a port at the baud it already has, so `SerialLink` opens at 9600, switches once, never reconfigures |
| First command takes ~2 s / stored drawing stopped | Opening the serial port resets the Uno |
| "port busy" | Another server holds the lock (one per serial port) |
| Drawings come out small and wobbly | Pen friction makes the joints lag; draw slower (30-45 mm/s was more accurate than 100 for long runs), and redo the calibration (section 5) |
| Servo loses steps in a long run | Lower the speed; 100 mm/s once dropped the USB in an infinite loop |

## 8. Using it

### Canvas and tools
The server computes a **canvas**: the largest rectangle the arm can fully reach (grid scan of the IK), in its own mm frame (origin bottom-left). Drawing tools take canvas coordinates only, so the LLM never sees page or servo geometry. All of them build **strokes** and go through one entry that validates the whole drawing before anything moves:
- `draw_svg_path` (SVG `d` strings, scaled into a box you give), `draw_shape` (circle, ellipse, rectangle, square, polygon, triangle, star, spiral, heart, hatch, wave), `draw_polyline`, `draw_line`, `draw_arc`, `draw_bezier`.
- `dry_run=true` on any of them returns bbox, length, estimated time, an ASCII thumbnail and an SVG, and moves nothing.
- Drawings run as **jobs**: a call waits `PENARM_SYNC_WAIT` s (default 20), then returns a `job_id` to poll with `job_status`; `stop()` cancels within a millimetre. One job at a time.
- Also `canvas_info` and `get_state`.

### Environment variables
`PENARM_PORT` (unset = simulator), `PENARM_SYNC_WAIT` (default 20), `PENARM_CALIBRATION` (path, default `~/.penarm/calibration.json`; one file per arm: set it per desk if a laptop drives several arms).

## 9. How it is built

- `firmware/` (PlatformIO). Line protocol over serial at 57600: `?`, `V`, `A s1 s2`, `R`, `W <s>` (release servos after that idle time, default 120 s), timed segments `Q seq a b [ms]` with status `S` and abort `X`, EEPROM program `PB/PD/PE/PI/G` (still in the firmware, no longer used by the server). Envs: `uno`, `esp32` (main firmware), `servotest`, `servotest_uno` (serial test), `servoloop_uno` (no computer: both servos sweep by themselves in a loop; `make servoloop PORT=...`), `idle_uno` (never drives the servos: use it to stop the arm safely). Boot starts with servos released so a reset never moves the arm.
- `server/src/penarm/`: `config.py` geometry (single source of truth), `kinematics.py` IK/FK, `arm.py` owner of the draw cycle, `plotter.py` the one class that draws (use it from Python), `server.py` registers its methods as MCP tools, `calibration.py` (calibration.json), `calibrate.py` (rectangle photo -> 4-parameter fit), `photo.py` (ink reading), `assemble.py`, `profile.py` (speed profile: 100 mm/s, 600 mm/s^2, 180 deg/s defaults), `jobs.py`, `link.py`.
- **Robustness:** one server per port (lock file); every command is idempotent and retried; automatic reconnect when the board goes silent. The board reports a `boot=<id>` that changes on every restart, so the server notices a reset (brown-out, cable bump), re-syncs the real pose and re-validates the stroke. The host stays ahead of the board's queue (64 waypoints on the Uno, 512 on the ESP32); a resent waypoint is never queued twice. Tests run against a fake board that loses 40% of replies like the CH340 clone (`tests/fakes.py`).
- **Portable tool schemas:** no `$ref`, unions, consts or tuples; optional arguments use defaults, never null. `tests/test_schema_portability.py` guards it, and the server carries its own provider-neutral usage guide (MCP `instructions`).

## 10. Known limits / TODO
1. Error dominates at the small scale: SG90 dead band + pen friction + the thin end of link 2 flexing. Large drawings come out more faithful than small ones (the error is roughly constant). Stiffen link 2.
2. Pots are not wired, so there is no closed loop. Wiring them (A0/A1) is the biggest accuracy gain left.
3. Pen lift (3rd servo) -> `pen_up`/`pen_down` tools.

## 11. License
GNU GPL v3 or later (`LICENSE`), a copyleft license: you can use, study, change and share this project, but anything you distribute that is based on it must stay under the same terms with its source available. It covers the code, the firmware, the docs, and the printable parts in `pecas_impressao/`.
