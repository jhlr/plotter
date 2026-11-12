# Workshop kit (1 hour, Portuguese)

Four phases, all on the real arm: **1** by hand in Python; **2** an LLM with no abstraction (it sends raw servo angles with `examples/raw.py`: no (x, y), no sheet, no limits); **3** an LLM with the abstraction of the MCP tools; **4** the groups debate what they saw. The stages switch with `python fase.py 2` / `python fase.py 3`, which turn the penarm tools off and on in `opencode.json`.

## Before class (once per arm)

1. Flash the main firmware and check for "verified": `make flash PORT=<port>` (macOS/Linux only; on Windows: `pio run -d firmware -e uno -t upload --upload-port COM3`).
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

- Setup (one prompt, in the folder or not): `opencode`, then paste: `Clone github.com/jhlr/plotter, entre na pasta, leia o AGENTS.md e siga-o.` It ends with a square on the arm.
- Phase 1, by hand: `python examples/phase1.py` (one board plugged in is found automatically; `sim` uses the simulator). The students write a few lines with the Plotter.
- Phase 2, LLM with no abstraction: `python fase.py 2` (penarm tools off), restart `opencode` in the repo folder, paste the prompt it prints. The agent only has `examples/raw.py`.
- Phase 3, LLM with the MCP: `python fase.py 3` (penarm tools on), restart `opencode`, paste the prompt it prints. Keep the arm's port in `PENARM_PORT` in `opencode.json` (`python setup.py` writes it).
- Phase 4: the groups debate. `python fase.py setup|2|3` writes `AGENTS.md` with the shared rules plus only that stage's section (the source is `workshop/agents.md`: edit that one), so the model sees just what the stage needs. A fresh clone is in the setup stage.

## The deck

`oficina-braco-plotter.pptx` is the deck on the Rec'n'Play template (13 slides, speaker notes included; the template uses the DM Sans font). Rebuild it with:

    brew install librsvg                                  # once: renders the figures
    python workshop/build_pptx.py "<path to [TEMPLATE] Palestras RNP.pptx>"

The arm figures are computed from the real geometry (`build_deck.py`), so regenerate instead of editing by hand. `build_deck.py` also writes the earlier web-slides version into `deck/project/`.
