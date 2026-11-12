# Workshop kit (1 hour, Portuguese)

Four phases, all on the real arm: **1** by hand in Python; **2** an LLM with no abstraction (it sends raw servo angles with `examples/raw.py`: no (x, y), no sheet, no limits); **3** an LLM with the abstraction of the MCP tools; **4** the groups debate what they saw. All in one `opencode` session: the student starts each message with the stage name (SETUP, FASE 2, FASE 3).

## Before class (once per arm and per computer)

1. Flash the main firmware and check for "verified": `make flash PORT=<port>` (macOS/Linux only; on Windows: `pio run -d firmware -e uno -t upload --upload-port COM3`).
2. Assembly pose: `penarm-assemble --port <port>`, mount both horns straight, tighten.
3. Calibrate (README section 5; needs `pip install -e "server[calibrate]"`): `penarm-calibrate draw --port <port>`, one photo, `penarm-calibrate measure photo.jpg --corners "..." --overlay check.png`, look, then `--save`.
4. **The calibration lives on the computer that ran `--save`**, in `~/.penarm/calibration.json` (`%USERPROFILE%\.penarm\calibration.json` on Windows). Copy that file to the computer that will drive that arm. Without it the computer uses the reference kit's numbers and drives the arm wrong; `setup.py` warns when the file is missing. The sheet size differs per arm, so the slides say "confira com canvas_info" and the examples use `p.canvas.w` / `p.canvas.h`.
5. Per desk: one arm, one USB cable, **external 5 V for the servos**, clean sheets, pencil in the holder.
6. Per computer: Python 3.11+, Git, [opencode](https://opencode.ai), the CH340 driver on Windows for clones, and PlatformIO if you flash there. Pre-install all of it on the lab machines so the hour is not spent on installs.

## In class: one terminal for opencode, no restarts

1. Each student, in a terminal, one command per line (macOS: `python3`; Windows: `py`; PowerShell 5 does not accept `&&`):

       git clone https://github.com/jhlr/plotter
       cd plotter
       python3 setup.py
       opencode

   Plug the board in **before** `setup.py`: it writes the board's port and the venv's Python into `opencode.json` (so the arm tools work with no activation). Run `setup.py` again and restart `opencode` if the board was not plugged in. `opencode` must start inside the `plotter` folder: it reads `AGENTS.md`, the Centopeia provider and the arm tools from there.
2. **SETUP** prompt: `SETUP: confira a instalação e desenhe o primeiro quadrado.`
3. **Fase 1, by hand:** open a **second terminal** in the `plotter` folder, activate the venv (macOS/Linux `source .venv/bin/activate`, Windows `.venv\Scripts\activate`), edit `examples/phase1.py` and run `python examples/phase1.py`. No agent. Everyone draws the same target: a square.
4. **Fase 2, no abstraction:** in the same `opencode` session: `FASE 2: desenhe um quadrado.` The agent only uses `examples/raw.py` (servo angles; the script refuses angles outside the safe range).
5. **Fase 3, with the MCP:** same session: `FASE 3: desenhe um quadrado.` The agent only uses the penarm tools. Then ask for a house.
6. **Debate:** the groups compare the three ways of drawing the same square.

Good to know:
- The MCP server opens the serial port at the first penarm tool call (Fase 3), not when `opencode` starts. From then on it holds the port: to run a script again, quit `opencode` first.
- `AGENTS.md` keeps the three stages; the student's first message names the stage and it stays until another is named. The penarm tools stay on the whole time, so keeping the agent out of them in Fase 2 is a prompt rule only (a 27B model may slip). That is a point for the debate, not a hidden guarantee.
- Emergency stop: the agent cannot stop a move in progress. Cut the arm's external 5 V.

## The deck

One deck: `dinamica-ia-hardware.pptx`, on the Rec'n'Play template (37 slides, speaker notes included, Arial). Rebuild it with:

    pip install python-pptx pillow                        # once (the `deck` extra of the server package does the same)
    brew install librsvg                                  # once: renders the arm figures
    python workshop/build_dinamica.py "<path to [TEMPLATE] Palestras RNP.pptx>"

`pptx_helpers.py` holds the template helpers, `figuras.py` the two arm figures (computed from the real geometry, so regenerate instead of editing by hand) and `icons/` the diagram icons.
