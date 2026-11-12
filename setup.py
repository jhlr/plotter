"""One-shot setup for a workshop computer (Windows, macOS, Linux):  python setup.py

Creates .venv, installs penarm, finds the arm's USB port and writes it into opencode.json,
then runs a simulator check. Plain standard library: it runs before anything is installed."""
import json
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def step(text: str) -> None:
    print(f"\n== {text}")


def run(*cmd: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, text=True)


def main() -> int:
    if sys.version_info < (3, 11):
        print(f"Python 3.11+ needed, this is {sys.version.split()[0]}. Install it from python.org.")
        return 1

    step("1/4 virtual environment (.venv)")
    if not PY.exists():
        venv.create(VENV, with_pip=True)
    print("ok:", VENV)

    step("2/4 installing penarm (a minute the first time)")
    r = run(PY, "-m", "pip", "install", "-q", "-e", "server")
    if r.returncode:
        print(r.stdout, r.stderr)
        return 1
    print("ok")

    step("3/4 the arm's USB port")
    r = run(PY, "-c", "from penarm import find_port; print(find_port())")
    port = r.stdout.strip() if r.returncode == 0 else ""
    if port:
        print("found:", port)
    else:
        print((r.stderr.strip().splitlines() or ["no board found"])[-1])
        print("Plug in ONE board and run this script again (the simulator works without it).")
    cfg_path = ROOT / "opencode.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["mcp"]["penarm"]["environment"]["PENARM_PORT"] = port
    cfg["mcp"]["penarm"]["command"][0] = str(PY)  # the venv's own python: opencode needs no activated venv
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    print("opencode.json PENARM_PORT =", repr(port), "(empty = simulator); MCP uses", PY)

    step("4/4 check with the simulator")
    r = run(PY, "examples/phase1.py", "sim")
    print("ok: simulator draws" if r.returncode == 0 else r.stdout + r.stderr)
    if r.returncode:
        return 1

    print("pio (flashing):", "found" if shutil.which("pio") or shutil.which("platformio") else "NOT on PATH (only needed to flash a board)")

    activate = r".venv\Scripts\activate" if sys.platform == "win32" else "source .venv/bin/activate"
    print(f"\nDone. Each new terminal:  {activate}")
    print("  python examples/phase1.py     # phase 1, by hand")
    print("  opencode                      # phase 2, with the LLM" if shutil.which("opencode") else "  opencode is NOT installed yet: https://opencode.ai")
    return 0


if __name__ == "__main__":
    sys.exit(main())
