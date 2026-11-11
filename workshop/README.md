# Workshop kit (1 hour, Portuguese)

Three phases, all on the real arm: **1** by hand in Python (20 min), **2** asking an LLM through MCP (20 min), **3** each group presents (20 min).

## Before class (once per arm)

1. Flash the main firmware and check for "verified": `make flash PORT=<port>`.
2. Assembly pose: `penarm-assemble --port <port>`, mount both horns straight, tighten.
3. Draw the rectangle, one photo, measure and fit (README section 5): `penarm-calibrate draw --port <port>`, then `penarm-calibrate measure photo.jpg --corners "..." --overlay check.png`, look, then `--save`. Check with `python examples/phase1.py`.
4. Per desk: one arm, one USB cable, **external 5 V for the servos**, clean sheets, pencil in the holder.

## Each workshop computer (once)

1. `git clone https://github.com/jhlr/plotter` and `cd plotter`.
2. Python 3.11+, then `python setup.py` (Windows: `py setup.py`). It makes `.venv`, installs `penarm`, writes the board's port into `opencode.json` and checks the simulator. Run it again with the board plugged in if it found none.
3. Install [opencode](https://opencode.ai) and log in to a model provider (`opencode auth login`) or set its API key.
4. USB driver for the board: none on macOS/Linux; Windows needs the CH340 driver for clones.
5. PlatformIO (`pio`) is installed on the lab machines, so any board can be flashed on the spot. Windows has no `make`; run it directly (the Uno env is `uno`, the port is the board's `COMx`):

       pio run -d firmware -e uno -t upload --upload-port COM3

   Wait for "verified". `python setup.py` reports whether `pio` is on the PATH.

## In class

- Phase 1: `python examples/phase1.py` (one board plugged in is found automatically; `python examples/phase1.py sim` uses the simulator).
- Phase 2: run `opencode` from the repo folder. The committed `opencode.json` (and `.mcp.json` for Claude Code) connects it to the arm; put the desk's serial port in `PENARM_PORT` inside `opencode.json` (empty = simulator).

## The deck

`oficina-braco-plotter.pptx` is the deck on the Rec'n'Play template (13 slides, speaker notes included; the template uses the DM Sans font). Rebuild it with:

    brew install librsvg                                  # once: renders the figures
    python workshop/build_pptx.py "<path to [TEMPLATE] Palestras RNP.pptx>"

The arm figures are computed from the real geometry (`build_deck.py`), so regenerate instead of editing by hand. `build_deck.py` also writes the earlier web-slides version into `deck/project/`.
