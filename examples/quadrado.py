"""A first drawing, to see the arm work right after the setup:  python examples/quadrado.py   (add `sim` for the simulator)
A 36 mm square in the middle of the sheet, four lines, each starting where the last one ended. Pen in the holder, sheet under it."""
import sys

from penarm import Plotter, find_port

port = None if "sim" in sys.argv[1:] else find_port()
with Plotter(port) as p:
    cx, cy, h = p.canvas.w / 2, p.canvas.h / 2, 18       # centre of the sheet and half the side, in mm
    print(p.draw_line(cx - h, cy - h, cx + h, cy - h, dry_run=True)["ascii"])  # rehearsal: nothing moves
    p.draw_line(cx - h, cy - h, cx + h, cy - h)
    p.draw_line(cx + h, cy - h, cx + h, cy + h)
    p.draw_line(cx + h, cy + h, cx - h, cy + h)
    p.draw_line(cx - h, cy + h, cx - h, cy - h)
    print("done")
