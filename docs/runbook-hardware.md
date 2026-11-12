# Hardware runbook for an AI agent setting up or operating this plotter (flash, calibrate, draw)

A 2-link pen-plotter arm on an Arduino Uno, driven through an MCP server. Read `README.md` for the full picture; this file is the order of operations, and who must do what. **The software is pen-agnostic**: never assume the ink colour.

## If you were told only "clone this repo and run the README"

That means set up a machine, nothing else. Do exactly this and stop:

1. `git clone https://github.com/jhlr/plotter`, then `cd plotter`.
2. `python setup.py` (Windows: `py setup.py`). It creates `.venv`, installs `penarm`, writes the board's USB port into `opencode.json` and checks the simulator. If Python 3.11+ is missing, tell the human.
3. Check: `python examples/phase1.py sim` should print the canvas and an ASCII preview.
4. If `setup.py` printed a port (a board is plugged in), draw the first square so the student sees the arm work: `python examples/quadrado.py` (a 36 mm square, four `draw_line`). The human has pre-approved this one drawing, with the pen in the holder and a sheet under it; if the pen or sheet is not there, ask first. Then ask the human whether the arm really moved (never say "drawn" on your own). With no port, run it with `sim`.
5. Report what worked. **Do not** flash firmware, calibrate or run `penarm-assemble`, and do not draw anything else on a real arm unless the human asks: the rest of this file (hardware bring-up, calibration) is for those later requests.
6. The MCP tools (`draw_line`, `draw_shape`, ...) load only when `opencode` is started inside the repo folder with `.venv` active, so tell the human to restart it there.

Only one program can hold the serial port: quit `opencode`'s arm tools or the MCP server before running a Python script on the real board, and the other way round.

## What you can do alone vs. what needs the human

| Step | Who |
|---|---|
| Install, run tests, simulator, connect MCP | you |
| Build/flash firmware (`make flash PORT=...` on macOS/Linux; Windows: `pio run -d firmware -e uno -t upload --upload-port COM3`) | you, if the board is plugged in; check for "verified" |
| Wiring, power (external 5 V for the servos), printing and assembling the parts (`pecas_impressao/`) | the human (README sections 1-2) |
| Putting a **clean sheet** under the pen, swapping it between rounds | the human; **ask before every drawing round** |
| Photographing the board, reading the 4 board corners in pixels | the human sends the photo; you read the corners (crop 2x2 and read by hand) |
| Confirming the arm really moved | the human. The board answers `OK` even when the servos did not move, and you cannot see the arm. **Never say "drawn" without their confirmation** |

## Procedure

1. **No hardware yet:** `python setup.py` (any OS), then `penarm-mcp` for the simulator; on macOS/Linux `make setup` also runs the tests (100+ pass) and `make sim` starts the server. **`make` does not exist on Windows**: use the plain commands. The server runs a simulator when `PENARM_PORT` is unset or empty. `canvas_info` shows `"simulated": true`.
2. **Connect yourself to the server.** It is a stdio MCP server: command `python -c "from penarm.server import main; main()"` with `.venv` active (or `<repo>/.venv/bin/penarm-mcp`, Windows `.venv\Scripts\penarm-mcp.exe`), env `PENARM_PORT=<serial port>` (omit for simulator). The repo's `.mcp.json` already does this for Claude Code. The server ships usage instructions: read them, then call `canvas_info`.
3. **Hardware bring-up, in order** (README section 3): servo test (`make servotest PORT=...`, macOS/Linux; on Windows use `pio run -d firmware -e servotest_uno -t upload --upload-port COM3`; if a servo does not move it is wiring or power, stop and tell the human), flash the main firmware (`make flash PORT=...` or the Windows `pio` command above, wait for "verified", reflash otherwise), then restart the server with `PENARM_PORT`. Serial port: macOS `ls /dev/cu.usbserial*`, Linux `ls /dev/ttyUSB*`, Windows `COM3`. Opening the port resets the Uno; only one process may hold it.
4. **Calibrate before drawing** (README section 5): assemble at the assembly pose (`penarm-assemble`, no measuring), then ONE rectangle and ONE photo: `penarm-calibrate draw --port P` on a clean sheet, the human photographs the whole board and you read its 4 corners in pixels (crop 2x2 and read by hand), `penarm-calibrate measure photo.jpg --corners "BL BR TR TL" --overlay check.png`, **open the overlay and look**, then `--save`. Draw again to confirm. Without a `~/.penarm/calibration.json` the defaults describe the author's arm.
5. **Draw:** `canvas_info` first, `dry_run=true` for anything new, a small first drawing well inside the sheet, 30-45 mm/s for long runs.

## Rules that have cost real time

- No pen lift: every move marks the paper. Clean sheet each round; reusing a sheet corrupts the calibration read.
- Do not move the arm with a pen on the desk and an unvalidated mapping (it scratched the table once). Order: no pen, validate mapping, small drawing.
- Name the board corners in the photo by what they are (BL = nearest the servos, on the left), not by where they land in the image.
- Never trust an ink measurement you have not looked at: open the `--overlay` PNG. If it picked up the arm or the pen barrel, `--mask x0,y0,x1,y1`; if it misses the line, name the colour with `--ink`.
- The servos need external 5 V with the ground shared with the Arduino: from USB alone the board locks up when the arm moves.
- A background process you start is yours to clean up (`ps aux`, kill). A drawing loop runs on the host; stop it with SIGINT/SIGTERM so the arm parks.

## Checks before you finish a change to this repo

    make check            # mypy --strict + pytest, no hardware (macOS/Linux; Windows: cd server, then mypy src and pytest)
    make firmware-build   # every firmware env compiles (Windows: pio run -d firmware)

CI (`.github/workflows/ci.yml`) runs the same on every push.
