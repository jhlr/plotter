"""Workshop phase 1, by hand:  python examples/phase1.py   (one USB board plugged in = the real arm;
`python examples/phase1.py sim` = simulator).

Four tools, from the simplest to the richest (more line drawings: examples/linhas.py). Change the numbers, run again.
Coordinates are mm: x to the right, y up, (0, 0) at the bottom-left of the usable paper."""
import sys

from penarm import Plotter, find_port

port = None if "sim" in sys.argv[1:] else find_port()
with Plotter(port) as p:
    print(f"canvas: {p.canvas.w:.0f} x {p.canvas.h:.0f} mm")

    # 0. Rehearse: dry_run=True moves nothing and prints a preview. Do this before every new drawing.
    print(p.draw_line(10, 10, 60, 10, dry_run=True)["ascii"])

    # 1. One straight line: from (x1, y1) to (x2, y2).
    p.draw_line(10, 10, 60, 10)

    # 2. Several lines, one after the other: each starts where the last one ended, so the pen never travels. A rectangle:
    p.draw_line(10, 10, 60, 10)
    p.draw_line(60, 10, 60, 40)
    p.draw_line(60, 40, 10, 40)
    p.draw_line(10, 40, 10, 10)

    # 3. A circular arc: centre, radius, start and end angle in degrees.
    p.draw_arc(100, 24, 20, 0, 180)                                            # a half circle

    # 4. A ready-made shape: kind, centre, size. Try "star", "heart", "spiral", "circle", "triangle".
    p.draw_shape("star", 100, 24, 30, sides=7)
