"""Dry-run description of a drawing: numbers, an ASCII thumbnail and an SVG, so the LLM can check before the pen moves."""
import math

from .canvas import Canvas
from .shapes import Stroke, bbox

EST_MM_PER_S = 25.0  # rough end-to-end tip speed (serial round trip per 1 mm step dominates), not a spec


def stats(strokes: list[Stroke], canvas: Canvas, travel_from: tuple[float, float] | None = None) -> dict[str, object]:
    pts = [p for s in strokes for p in s]
    length = sum(math.dist(a, b) for s in strokes for a, b in zip(s, s[1:]))
    travel = 0.0
    prev = travel_from
    for s in strokes:
        if prev is not None:
            travel += math.dist(prev, s[0])
        prev = s[-1]
    x0, y0, x1, y1 = bbox(strokes)
    return {
        "strokes": len(strokes), "points": len(pts), "bbox_mm": [round(v, 1) for v in (x0, y0, x1, y1)],
        "length_mm": round(length, 1), "travel_marks_mm": round(travel, 1),
        "est_seconds": round((length + travel) / EST_MM_PER_S),
        "inside_canvas": all(canvas.contains(*p) for p in pts),
        "canvas_mm": [round(canvas.w, 1), round(canvas.h, 1)],
    }


def ascii_art(strokes: list[Stroke], canvas: Canvas, cols: int = 60) -> str:
    """Thumbnail of the canvas ('.' empty, '#' ink, 'S'/'E' first/last point, 'O' if they coincide, y up, aspect corrected for chars)."""
    rows = max(4, round(cols * canvas.h / canvas.w / 2))
    grid = [["." for _ in range(cols)] for _ in range(rows)]

    def cell(p: tuple[float, float]) -> tuple[int, int]:
        c = min(cols - 1, max(0, int(p[0] / canvas.w * cols)))
        r = min(rows - 1, max(0, int((1 - p[1] / canvas.h) * rows)))
        return r, c

    for s in strokes:
        for a, b in zip(s, s[1:]):
            n = max(1, int(math.dist(a, b) / canvas.w * cols * 2))
            for i in range(n + 1):
                r, c = cell((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n))
                grid[r][c] = "#"
    (rs, cs), (re_, ce) = cell(strokes[0][0]), cell(strokes[-1][-1])
    grid[rs][cs] = "S"
    grid[re_][ce] = "O" if (rs, cs) == (re_, ce) else "E"  # O = a closed shape: start and end are the same spot
    return "\n".join("".join(row) for row in grid)


def svg(strokes: list[Stroke], canvas: Canvas) -> str:
    def poly(s: Stroke) -> str:
        return " ".join(f"{x:.1f},{canvas.h - y:.1f}" for x, y in s)  # SVG y points down

    body = "".join(f'<polyline fill="none" stroke="black" stroke-width="0.6" points="{poly(s)}"/>' for s in strokes)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas.w:.1f} {canvas.h:.1f}">'
            f'<rect width="{canvas.w:.1f}" height="{canvas.h:.1f}" fill="none" stroke="red" stroke-width="0.5"/>{body}</svg>')


def describe(strokes: list[Stroke], canvas: Canvas, travel_from: tuple[float, float] | None = None) -> dict[str, object]:
    out = stats(strokes, canvas, travel_from)
    out["ascii"] = ascii_art(strokes, canvas)
    out["svg"] = svg(strokes, canvas)
    return out
