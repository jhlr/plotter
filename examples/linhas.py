"""Drawings made only of draw_line:  python examples/linhas.py casa     (or escada, estrela, zigzag; add `sim` for the simulator)

The arm never lifts the pen, so each line must START where the last one ENDED. Then the drawing is one clean stroke.
A line that starts somewhere else makes the pen travel there, leaving a mark. Plan the order before you run."""
import math
import sys

from penarm import Plotter, find_port


def line(p: Plotter, x1: float, y1: float, x2: float, y2: float) -> None:
    """draw_line with the numbers below written for a 134 x 48 mm sheet, scaled to the sheet this arm really has."""
    k = min(p.canvas.w / 134, p.canvas.h / 48)
    p.draw_line(x1 * k, y1 * k, x2 * k, y2 * k)


def casa(p: Plotter) -> None:
    """House with a roof, one stroke: starts and ends at the two corners where three lines meet."""
    line(p, 50, 30, 50, 6)    # left wall, going down
    line(p, 50, 6, 90, 6)     # floor
    line(p, 90, 6, 90, 30)    # right wall, going up
    line(p, 90, 30, 70, 44)   # right side of the roof
    line(p, 70, 44, 50, 30)   # left side of the roof
    line(p, 50, 30, 90, 30)   # ceiling: closes the square and the triangle


def escada(p: Plotter) -> None:
    """Stairs: right, up, right, up..."""
    x, y = 10, 6
    for _ in range(5):
        line(p, x, y, x + 20, y)          # tread
        line(p, x + 20, y, x + 20, y + 8)  # riser
        x, y = x + 20, y + 8


def zigzag(p: Plotter) -> None:
    """Zigzag: the end of each line is the start of the next."""
    x, y = 10, 10
    for i in range(8):
        nx, ny = x + 15, 40 if i % 2 == 0 else 10
        line(p, x, y, nx, ny)
        x, y = nx, ny


def estrela(p: Plotter) -> None:
    """Five-point star in one stroke: join every second point of a pentagon."""
    cx, cy, r = 67, 24, 22  # centre of a 134 x 48 sheet
    tips = [(cx + r * math.cos(math.radians(90 + 72 * k)), cy + r * math.sin(math.radians(90 + 72 * k))) for k in range(5)]
    order = [0, 2, 4, 1, 3, 0]
    for a, b in zip(order[:-1], order[1:]):
        line(p, *tips[a], *tips[b])


DRAWINGS = {"casa": casa, "escada": escada, "zigzag": zigzag, "estrela": estrela}

if __name__ == "__main__":
    args = sys.argv[1:]
    name = next((a for a in args if a in DRAWINGS), "casa")
    port = None if "sim" in args else find_port()
    with Plotter(port) as p:
        print(f"canvas: {p.canvas.w:.0f} x {p.canvas.h:.0f} mm; drawing '{name}'")
        DRAWINGS[name](p)
