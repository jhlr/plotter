"""Set up opencode for a workshop stage:  python fase.py setup   |   python fase.py 2   |   python fase.py 3

It writes AGENTS.md with the shared rules plus ONLY that stage's section (from workshop/agents.md), so the model sees just
what the stage needs, and turns the penarm MCP tools off (setup, 2) or on (3) in opencode.json. Restart opencode after it."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGES = {  # key -> (section heading in workshop/agents.md, MCP tools on?, prompt to paste)
    "setup": ("SETUP", False, "Clone github.com/jhlr/plotter, entre na pasta, leia o AGENTS.md e siga-o."),
    "2": ("FASE 2", False, "Siga o AGENTS.md. Desenhe um quadrado."),
    "3": ("FASE 3", True, "Siga o AGENTS.md. Desenhe uma casa grande com telhado."),
}

if len(sys.argv) != 2 or sys.argv[1] not in STAGES:
    sys.exit(__doc__)
heading, mcp_on, prompt = STAGES[sys.argv[1]]
source = (ROOT / "workshop" / "agents.md").read_text()
parts = re.split(r"(?m)^(?=## (?:SETUP|FASE \d))", source)  # [shared rules, SETUP, FASE 2, FASE 3]
section = next(p for p in parts[1:] if p.startswith(f"## {heading}"))
(ROOT / "AGENTS.md").write_text(parts[0].replace("{STAGE}", heading).rstrip() + "\n\n" + section.rstrip() + "\n")

cfg_path = ROOT / "opencode.json"
cfg = json.loads(cfg_path.read_text())
cfg["mcp"]["penarm"]["enabled"] = mcp_on
cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
print(f"{heading}: AGENTS.md has only this stage; penarm tools {'ON' if mcp_on else 'OFF'}. Feche e abra o opencode nesta pasta e cole:\n\n{prompt}")
