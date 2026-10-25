"""One trajectory language for the LLM, portable across providers (plain strings and numbers, no nested schemas):
path operations as short text lines, SVG path data, and transform/fit -> strokes (mm polylines)."""
import math

from svgelements import Move
from svgelements import Path as SvgPath

from .shapes import Point, Stroke, arc_points, bbox, bezier_points, fit_strokes, quad_points, transform_strokes

# operation -> (number of numeric arguments, what they are)
OPS_HELP = {
    "move": (2, "move x y            start a new stroke at (x, y)"),
    "line": (2, "line x y            straight line to (x, y)"),
    "arc": (5, "arc cx cy r a0 a1    circular arc, angles in degrees from +x, counter-clockwise if a1 > a0"),
    "bezier": (6, "bezier x1 y1 x2 y2 x y   cubic Bezier from the current point (two control points, then the end)"),
    "quad": (4, "quad cx cy x y      quadratic Bezier from the current point (control point, then the end)"),
    "close": (0, "close              line back to the stroke's first point"),
}


def parse_ops(ops: list[str]) -> list[tuple[str, list[float]]]:
    parsed: list[tuple[str, list[float]]] = []
    for i, line in enumerate(ops):
        tokens = line.replace(",", " ").split()
        if not tokens:
            raise ValueError(f"op {i} is empty")
        name = tokens[0].lower()
        if name not in OPS_HELP:
            raise ValueError(f"op {i} '{line}': unknown operation '{tokens[0]}'; use one of {sorted(OPS_HELP)}")
        try:
            nums = [float(t) for t in tokens[1:]]
        except ValueError:
            raise ValueError(f"op {i} '{line}': arguments must be numbers") from None
        if len(nums) != OPS_HELP[name][0]:
            raise ValueError(f"op {i} '{line}': expected {OPS_HELP[name][1].strip()}")
        parsed.append((name, nums))
    return parsed


def strokes_from_ops(ops: list[str], seg_mm: float = 1.0) -> list[Stroke]:
    strokes: list[Stroke] = []
    cur: Stroke = []
    for name, n in parse_ops(ops):
        if name == "move":
            if len(cur) > 1:
                strokes.append(cur)
            cur = [(n[0], n[1])]
        elif name == "arc":
            arc = arc_points(n[0], n[1], n[2], n[3], n[4])
            cur = cur + arc if cur else arc
        else:
            if not cur:
                raise ValueError(f"'{name}' needs a current point: start with a 'move' op")
            if name == "line":
                cur.append((n[0], n[1]))
            elif name == "bezier":
                cur += bezier_points(cur[-1], (n[0], n[1]), (n[2], n[3]), (n[4], n[5]), seg_mm)[1:]
            elif name == "quad":
                cur += quad_points(cur[-1], (n[0], n[1]), (n[2], n[3]), seg_mm)[1:]
            else:  # close
                cur.append(cur[0])
    if len(cur) > 1:
        strokes.append(cur)
    if not strokes:
        raise ValueError("the path has no drawable segments")
    return strokes


def apply_transform_fit(
    strokes: list[Stroke], scale: float = 1.0, rotate_deg: float = 0.0, translate_x: float = 0.0, translate_y: float = 0.0,
    mirror_x: bool = False, mirror_y: bool = False, fit_box: list[float] | None = None, fit_margin: float = 0.0,
) -> list[Stroke]:
    """Mirror, scale and rotate about the drawing's center, translate; then optionally fit into [x, y, width, height]."""
    if (scale, rotate_deg, translate_x, translate_y, mirror_x, mirror_y) != (1.0, 0.0, 0.0, 0.0, False, False):
        x0, y0, x1, y1 = bbox(strokes)
        strokes = transform_strokes(strokes, scale, rotate_deg, (translate_x, translate_y),
                                    ((x0 + x1) / 2, (y0 + y1) / 2), mirror_x, mirror_y)
    if fit_box:
        if len(fit_box) != 4:
            raise ValueError("fit_box must be [x, y, width, height]")
        bx, by, bw, bh = fit_box
        strokes = fit_strokes(strokes, bx, by, bw, bh, margin=fit_margin)
    return strokes


def point(p: list[float], what: str = "point") -> Point:
    if len(p) != 2:
        raise ValueError(f"{what} must be [x, y], got {p}")
    return float(p[0]), float(p[1])


def svg_to_strokes(d: str, seg_mm: float = 1.0) -> list[Stroke]:
    """SVG path data -> strokes, in the path's own units with y DOWN (the caller flips and fits)."""
    try:
        path = SvgPath(d)
    except Exception as exc:  # svgelements raises assorted parse errors
        raise ValueError(f"invalid SVG path data: {exc}") from exc
    strokes: list[Stroke] = []
    cur: Stroke = []
    for seg in path:
        if isinstance(seg, Move):
            if len(cur) > 1:
                strokes.append(cur)
            cur = [(float(seg.end.x), float(seg.end.y))]
            continue
        length = float(seg.length(error=1e-4))
        n = max(1, math.ceil(length / seg_mm))
        pts = [seg.point(i / n) for i in range(1, n + 1)]
        if not cur and seg.start is not None:
            cur = [(float(seg.start.x), float(seg.start.y))]
        cur += [(float(p.x), float(p.y)) for p in pts]
    if len(cur) > 1:
        strokes.append(cur)
    if not strokes:
        raise ValueError("SVG path has no drawable segments")
    return strokes
