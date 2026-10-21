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
