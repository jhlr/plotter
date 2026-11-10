# /// script
# requires-python = ">=3.11"
# dependencies = ["penarm"]
# [tool.uv.sources]
# penarm = { path = "../server", editable = true }
# ///
"""Draw without any LLM, from any folder:  uv run examples/hello.py
No port = simulator. For the real arm: Plotter("/dev/cu.usbserial-10")."""
from penarm import Plotter

with Plotter() as p:
    print(f"canvas: {p.canvas.w:.0f} x {p.canvas.h:.0f} mm")
    middle = dict(cx=p.canvas.w / 2, cy=p.canvas.h / 2, size=p.canvas.h * 0.6)
    print(p.draw_shape("heart", **middle, dry_run=True)["ascii"])  # see it before the arm moves
    print(p.draw_shape("heart", **middle))                         # now draw it
