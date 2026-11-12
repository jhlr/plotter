# Workshop kit (1 hour, Portuguese)

Four phases, all on the real arm: **1** by hand in Python; **2** an LLM with no abstraction (it sends raw servo angles with `examples/raw.py`: no (x, y), no sheet, no limits); **3** an LLM with the abstraction of the MCP tools; **4** the groups debate what they saw. All in one `opencode` session: the student starts each message with the stage name (SETUP, FASE 2, FASE 3).

## Before class (once per arm)

1. Flash the main firmware and check for "verified": `make flash PORT=<port>` (macOS/Linux only; on Windows: `pio run -d firmware -e uno -t upload --upload-port COM3`).
2. Assembly pose: `penarm-assemble --port <port>`, mount both horns straight, tighten.
3. Draw the rectangle, one photo, measure and fit (README section 5): `penarm-calibrate draw --port <port>`, then `penarm-calibrate measure photo.jpg --corners "..." --overlay check.png`, look, then `--save`. Check with `python examples/phase1.py`.
4. Per desk: one arm, one USB cable, **external 5 V for the servos**, clean sheets, pencil in the holder.

## Each workshop computer (once)

1. Python 3.11+, Git, and [opencode](https://opencode.ai). USB driver for the board: none on macOS/Linux; Windows needs the CH340 driver for clones.
2. PlatformIO (`pio`) is installed on the lab machines, so any board can be flashed on the spot. Windows has no `make`; run it directly (the Uno env is `uno`, the port is the board's `COMx`):

       pio run -d firmware -e uno -t upload --upload-port COM3

   Wait for "verified".

## In class: one terminal, one opencode, no restarts

1. Each student, in a terminal (Windows: `py` instead of `python`):

       git clone https://github.com/jhlr/plotter && cd plotter && python setup.py
       opencode

   `setup.py` makes `.venv`, installs `penarm`, writes the board's port and the venv's Python into `opencode.json` (so the arm tools work with no activation) and checks the simulator. Run it again with the board plugged in if it found none. `opencode` must be started inside the `plotter` folder: it reads `AGENTS.md`, the Centopeia provider and the arm tools from there.
2. **SETUP** prompt: `SETUP: confira a instalação e desenhe o primeiro quadrado.` The agent checks the simulator and draws a square on the arm.
3. **Phase 1, by hand:** `python examples/phase1.py` (a few lines with the Plotter; `sim` uses the simulator). No agent.
4. **Phase 2, no abstraction:** in the same `opencode` session: `FASE 2: desenhe um quadrado.` The agent only uses `examples/raw.py` (servo angles).
5. **Phase 3, with the MCP:** same session: `FASE 3: desenhe uma casa grande com telhado.` The agent only uses the penarm tools.
6. **Phase 4:** the groups debate.

`AGENTS.md` holds the rules and the three stage sections; the student's message starts with the stage name, and the agent follows only that section. The penarm tools stay on the whole time: in phase 2 the rules tell the agent not to call them (a 27B model may slip, so watch it).

## The deck

`oficina-braco-plotter.pptx` is the deck on the Rec'n'Play template (14 slides, speaker notes included; the template uses the DM Sans font). Rebuild it with:

    brew install librsvg                                  # once: renders the figures
    python workshop/build_pptx.py "<path to [TEMPLATE] Palestras RNP.pptx>"

The arm figures are computed from the real geometry (`build_deck.py`), so regenerate instead of editing by hand. `build_deck.py` also writes the earlier web-slides version into `deck/project/`.
