"""Curve primitives sampled into polylines (max chord error `tol` mm)."""
import math


def arc_points(
    cx: float, cy: float, r: float, start_deg: float, end_deg: float, tol: float = 0.1
) -> list[tuple[float, float]]:
    """Counter-clockwise if end > start, clockwise otherwise. Angles from +x, degrees."""
    if r <= 0:
        raise ValueError("radius must be > 0")
    sweep = math.radians(end_deg - start_deg)
    step = 2 * math.acos(max(0.0, 1 - tol / r)) or math.radians(1)  # chord error <= tol
    n = max(2, math.ceil(abs(sweep) / step))
    a0 = math.radians(start_deg)
    return [(cx + r * math.cos(a0 + sweep * i / n), cy + r * math.sin(a0 + sweep * i / n)) for i in range(n + 1)]


def rect_points(x: float, y: float, w: float, h: float) -> list[tuple[float, float]]:
    """Closed rectangle path from corner (x, y), counter-clockwise."""
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]


def bezier_points(
    p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float],
    seg_mm: float = 1.0,
) -> list[tuple[float, float]]:
    """Cubic Bezier sampled so consecutive points are about `seg_mm` apart (control polygon length bound)."""
    poly = math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
    n = max(2, math.ceil(poly / seg_mm))
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append((
            u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
        ))
    return pts


Point = tuple[float, float]
Stroke = list[Point]


def _rot(p: Point, deg: float, about: Point) -> Point:
    a = math.radians(deg)
    dx, dy = p[0] - about[0], p[1] - about[1]
    return about[0] + dx * math.cos(a) - dy * math.sin(a), about[1] + dx * math.sin(a) + dy * math.cos(a)


def ellipse_points(
    cx: float, cy: float, rx: float, ry: float, rot_deg: float = 0.0,
    start_deg: float = 0.0, end_deg: float = 360.0, tol: float = 0.1,
) -> Stroke:
    """Ellipse (or elliptical arc), counter-clockwise if end > start; rot_deg rotates it about its center."""
    if rx <= 0 or ry <= 0:
        raise ValueError("radii must be > 0")
    r = max(rx, ry)
    step = 2 * math.acos(max(0.0, 1 - tol / r)) or math.radians(1)
    sweep = math.radians(end_deg - start_deg)
    n = max(8, math.ceil(abs(sweep) / step))
    a0 = math.radians(start_deg)
    pts = [(cx + rx * math.cos(a0 + sweep * i / n), cy + ry * math.sin(a0 + sweep * i / n)) for i in range(n + 1)]
    return [_rot(p, rot_deg, (cx, cy)) for p in pts] if rot_deg else pts


def polygon_points(cx: float, cy: float, r: float, sides: int, rot_deg: float = 0.0) -> Stroke:
    """Regular polygon, closed; first vertex at angle rot_deg from +x (default: pointing right)."""
    if sides < 3 or r <= 0:
        raise ValueError("a polygon needs sides >= 3 and radius > 0")
    pts = [(cx + r * math.cos(math.radians(rot_deg) + 2 * math.pi * i / sides),
            cy + r * math.sin(math.radians(rot_deg) + 2 * math.pi * i / sides)) for i in range(sides)]
    return [*pts, pts[0]]


def star_points(cx: float, cy: float, r_outer: float, r_inner: float, tips: int, rot_deg: float = 90.0) -> Stroke:
    """Star with `tips` points, closed; default orientation has one tip pointing up."""
    if tips < 3 or r_outer <= 0 or not 0 < r_inner < r_outer:
        raise ValueError("a star needs tips >= 3 and 0 < r_inner < r_outer")
    pts = []
    for i in range(2 * tips):
        r = r_outer if i % 2 == 0 else r_inner
        a = math.radians(rot_deg) + math.pi * i / tips
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return [*pts, pts[0]]


def spiral_points(cx: float, cy: float, r_start: float, r_end: float, turns: float, seg_mm: float = 1.0) -> Stroke:
    """Archimedean spiral from r_start to r_end over `turns` turns (counter-clockwise)."""
    if turns <= 0 or min(r_start, r_end) < 0 or max(r_start, r_end) <= 0:
        raise ValueError("spiral needs turns > 0 and a positive radius")
    length = math.pi * turns * 2 * (r_start + r_end) / 2
    n = max(16, math.ceil(length / seg_mm))
    return [(cx + (r_start + (r_end - r_start) * i / n) * math.cos(2 * math.pi * turns * i / n),
             cy + (r_start + (r_end - r_start) * i / n) * math.sin(2 * math.pi * turns * i / n)) for i in range(n + 1)]


def wave_points(p0: Point, p1: Point, amplitude: float, cycles: float, seg_mm: float = 1.0) -> Stroke:
    """Sine wave along the segment p0 -> p1, peak deviation `amplitude` mm, `cycles` full periods."""
    length = math.dist(p0, p1)
    if length <= 0 or cycles <= 0:
        raise ValueError("wave needs two distinct points and cycles > 0")
    ux, uy = (p1[0] - p0[0]) / length, (p1[1] - p0[1]) / length
    n = max(16, math.ceil(length / seg_mm))
    out = []
    for i in range(n + 1):
        t = i / n
        off = amplitude * math.sin(2 * math.pi * cycles * t)
        out.append((p0[0] + ux * length * t - uy * off, p0[1] + uy * length * t + ux * off))
    return out


def hatch_points(x: float, y: float, w: float, h: float, spacing: float, vertical: bool = False) -> Stroke:
    """Zigzag that fills a rectangle with parallel strokes `spacing` mm apart (one continuous stroke)."""
    if w <= 0 or h <= 0 or spacing <= 0:
        raise ValueError("hatch needs w, h, spacing > 0")
    pts: Stroke = []
    n = int((w if vertical else h) / spacing) + 1
    for i in range(n):
        t = i * spacing
        a, b = ((x + t, y), (x + t, y + h)) if vertical else ((x, y + t), (x + w, y + t))
        pts += [a, b] if i % 2 == 0 else [b, a]
    return pts


def heart_points(cx: float, cy: float, size: float, seg_mm: float = 1.0) -> Stroke:
    """Heart curve, `size` mm wide, starting and ending at the bottom tip."""
    if size <= 0:
        raise ValueError("size must be > 0")
    n = max(48, math.ceil(size * 3 / seg_mm))
    raw = [(16 * math.sin(t) ** 3,
            13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
           for t in (math.pi + 2 * math.pi * i / n for i in range(n + 1))]
    k = size / 32.0
    return [(cx + px * k, cy + py * k) for px, py in raw]


def quad_points(p0: Point, c: Point, p1: Point, seg_mm: float = 1.0) -> Stroke:
    """Quadratic Bezier p0 -> p1 with control point c."""
    return bezier_points(p0, ((p0[0] + 2 * c[0]) / 3, (p0[1] + 2 * c[1]) / 3), ((p1[0] + 2 * c[0]) / 3, (p1[1] + 2 * c[1]) / 3), p1, seg_mm)


def transform_strokes(
    strokes: list[Stroke], scale: float = 1.0, rotate_deg: float = 0.0, translate: Point = (0.0, 0.0),
    about: Point = (0.0, 0.0), mirror_x: bool = False, mirror_y: bool = False,
) -> list[Stroke]:
    """Mirror, then scale and rotate about `about`, then translate. mirror_x flips left-right, mirror_y top-bottom."""
    out = []
    for s in strokes:
        pts = []
        for x, y in s:
            dx, dy = (x - about[0]) * scale, (y - about[1]) * scale
            dx, dy = -dx if mirror_x else dx, -dy if mirror_y else dy
            px, py = _rot((about[0] + dx, about[1] + dy), rotate_deg, about)
            pts.append((px + translate[0], py + translate[1]))
        out.append(pts)
    return out


def bbox(strokes: list[Stroke]) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y)."""
    xs = [p[0] for s in strokes for p in s]
    ys = [p[1] for s in strokes for p in s]
    return min(xs), min(ys), max(xs), max(ys)


def fit_strokes(strokes: list[Stroke], x: float, y: float, w: float, h: float, margin: float = 0.0,
                keep_aspect: bool = True) -> list[Stroke]:
    """Scale and move the drawing so its bounding box lands inside the box (x, y, w, h) shrunk by `margin`."""
    x0, y0, x1, y1 = bbox(strokes)
    bw, bh = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    tw, th = w - 2 * margin, h - 2 * margin
    if tw <= 0 or th <= 0:
        raise ValueError("fit box is smaller than the margin")
    sx, sy = tw / bw, th / bh
    if keep_aspect:
        sx = sy = min(sx, sy)
    ox = x + margin + (tw - bw * sx) / 2  # centered in the box
    oy = y + margin + (th - bh * sy) / 2
    return [[(ox + (px - x0) * sx, oy + (py - y0) * sy) for px, py in s] for s in strokes]
