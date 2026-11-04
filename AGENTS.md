# AGENTS.md: runbook for an AI agent setting up or operating this plotter

A 2-link pen-plotter arm on an Arduino Uno, driven through an MCP server. Read `README.md` for the full picture; this file is the order of operations, and who must do what. **The software is pen-agnostic**: never assume the ink colour.

## What you can do alone vs. what needs the human

| Step | Who |
|---|---|
| Install, run tests, simulator, connect MCP | you |
| Build/flash firmware (`make flash PORT=...`) | you, if the board is plugged in; check for "verified" |
| Wiring, power (external 5 V for the servos), printing and assembling the parts (`pecas_impressao/`) | the human (README sections 1-2) |
| Putting a **clean sheet** under the pen, swapping it between rounds | the human; **ask before every drawing round** |
| Photographing the board, reading the 4 board corners in pixels | the human sends the photo; you read the corners (crop 2x2 and read by hand) |
| Confirming the arm really moved | the human. The board answers `OK` even when the servos did not move, and you cannot see the arm. **Never say "drawn" without their confirmation** |

## Procedure

1. **No hardware yet:** `make setup` (uv + tests, 100+ pass), then `make sim`. The server runs a simulator when `PENARM_PORT` is unset or empty. `canvas_info` shows `"simulated": true`.
2. **Connect yourself to the server.** It is a stdio MCP server: command `uv`, args `["--directory", "<repo>/server", "run", "penarm-mcp"]`, env `PENARM_PORT=<serial port>` (omit for simulator). The repo's `.mcp.json` already does this for Claude Code. The server ships usage instructions: read them, then call `canvas_info`.
3. **Hardware bring-up, in order** (README section 3): servo test (`make servotest PORT=...`; if a servo does not move it is wiring or power, stop and tell the human), flash the main firmware (`make flash PORT=...`, wait for "verified", reflash otherwise), then restart the server with `PENARM_PORT`. Serial port: macOS `ls /dev/cu.usbserial*`, Linux `ls /dev/ttyUSB*`, Windows `COM3`. Opening the port resets the Uno; only one process may hold it.
4. **Calibrate before drawing** (README sections 5-6). `server/calibration.json` is specific to one arm and git-ignored; without it the defaults describe the author's arm, so drawings come out the wrong size. Remove the pen for pose calibration, then run the rectangle calibration 2-3 times on fresh sheets (`penarm-inkcal draw`, photo, `measure ... --overlay`, **open the overlay and look**, then `--update-mesh`).
5. **Draw:** `canvas_info` first, `dry_run=true` for anything new, a small first drawing well inside the sheet, 30-45 mm/s for long runs.

## Rules that have cost real time

- No pen lift: every move marks the paper. Clean sheet each round; reusing a sheet corrupts the calibration read.
- Do not move the arm with a pen on the desk and an unvalidated mapping (it scratched the table once). Order: no pen, validate mapping, small drawing.
- Name the board corners in the photo by what they are (BL = nearest the servos, on the left), not by where they land in the image.
- Never trust an ink measurement you have not looked at: open the `--overlay` PNG. If it picked up the arm or the pen barrel, `--mask x0,y0,x1,y1`; if it misses the line, name the colour with `--ink`.
- After changing offsets, gains or lengths, delete the `mesh` key in `calibration.json` and re-measure.
- A background process you start is yours to clean up (`ps aux`, kill). A drawing loop runs on the host; stop it with SIGINT/SIGTERM so the arm parks.

## Checks before you finish a change to this repo

    make check            # mypy --strict + pytest, no hardware
    make firmware-build   # every firmware env compiles

CI (`.github/workflows/ci.yml`) runs the same on every push.
