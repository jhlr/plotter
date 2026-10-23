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
