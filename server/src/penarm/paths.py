"""One trajectory language for the LLM: typed path operations, SVG paths and transforms -> strokes (mm polylines)."""
import math
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from svgelements import Move
from svgelements import Path as SvgPath

from .shapes import (Point, Stroke, arc_points, bezier_points, fit_strokes, quad_points, transform_strokes)

XY = tuple[float, float]


class MoveOp(BaseModel):
    """Start a new stroke at a point. Without pen-up hardware the tip still travels there touching the paper."""
    op: Literal["move"]
    to: XY


class LineOp(BaseModel):
    op: Literal["line"]
    to: XY


class ArcOp(BaseModel):
    """Circular arc (degrees from +x, counter-clockwise if end > start). A line joins it if the pen is elsewhere."""
    op: Literal["arc"]
    center: XY
    radius: float
    start_deg: float
    end_deg: float


class BezierOp(BaseModel):
    """Cubic Bezier from the current point."""
    op: Literal["bezier"]
    c1: XY
    c2: XY
    to: XY


class QuadOp(BaseModel):
    """Quadratic Bezier from the current point."""
    op: Literal["quad"]
    c: XY
    to: XY


class CloseOp(BaseModel):
    """Line back to the stroke's first point."""
    op: Literal["close"]


Op = Annotated[MoveOp | LineOp | ArcOp | BezierOp | QuadOp | CloseOp, Field(discriminator="op")]


class Transform(BaseModel):
    """Applied after the ops: mirror, then scale and rotate about `about`, then translate (canvas mm)."""
    scale: float = 1.0
    rotate_deg: float = 0.0
    translate: XY = (0.0, 0.0)
    about: XY = (0.0, 0.0)
    mirror_x: bool = False
    mirror_y: bool = False


class Fit(BaseModel):
    """Scale and move the whole drawing into the box (x, y, width, height), centered, inside `margin` mm."""
    x: float
    y: float
    width: float
    height: float
    margin: float = 0.0
    keep_aspect: bool = True


def strokes_from_ops(ops: list[Op], seg_mm: float = 1.0) -> list[Stroke]:
    strokes: list[Stroke] = []
    cur: Stroke = []

    def need_start(op: str) -> None:
        if not cur:
            raise ValueError(f"'{op}' needs a current point: start with a 'move' op")

    for o in ops:
        if isinstance(o, MoveOp):
            if len(cur) > 1:
                strokes.append(cur)
            cur = [o.to]
        elif isinstance(o, LineOp):
            need_start("line")
            cur.append(o.to)
        elif isinstance(o, ArcOp):
            arc = arc_points(*o.center, o.radius, o.start_deg, o.end_deg)
            cur = cur + arc if cur else arc
        elif isinstance(o, BezierOp):
            need_start("bezier")
            cur += bezier_points(cur[-1], o.c1, o.c2, o.to, seg_mm)[1:]
        elif isinstance(o, QuadOp):
            need_start("quad")
            cur += quad_points(cur[-1], o.c, o.to, seg_mm)[1:]
        elif isinstance(o, CloseOp):
            need_start("close")
            cur.append(cur[0])
    if len(cur) > 1:
        strokes.append(cur)
    if not strokes:
        raise ValueError("the path has no drawable segments")
    return strokes


def apply_transform_fit(strokes: list[Stroke], transform: Transform | None, fit: Fit | None) -> list[Stroke]:
    if transform:
        strokes = transform_strokes(strokes, transform.scale, transform.rotate_deg, transform.translate,
                                    transform.about, transform.mirror_x, transform.mirror_y)
    if fit:
        strokes = fit_strokes(strokes, fit.x, fit.y, fit.width, fit.height, fit.margin, fit.keep_aspect)
    return strokes


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


__all__ = ["Op", "Transform", "Fit", "Point", "strokes_from_ops", "apply_transform_fit", "svg_to_strokes"]
