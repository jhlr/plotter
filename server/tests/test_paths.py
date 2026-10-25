import math

import pytest
from pydantic import TypeAdapter

from penarm.canvas import Canvas
from penarm.paths import Fit, Op, Transform, apply_transform_fit, strokes_from_ops, svg_to_strokes
from penarm.preview import ascii_art, describe, stats
from penarm.shapes import (bbox, ellipse_points, heart_points, hatch_points, polygon_points, spiral_points,
                           star_points, transform_strokes, wave_points)

OPS = TypeAdapter(list[Op])


def ops(*items: dict) -> list:  # type: ignore[type-arg]
    return OPS.validate_python(list(items))


def test_ops_build_one_stroke_and_close_it() -> None:
    s = strokes_from_ops(ops({"op": "move", "to": [0, 0]}, {"op": "line", "to": [10, 0]},
                             {"op": "bezier", "c1": [12, 3], "c2": [12, 7], "to": [10, 10]}, {"op": "close"}))
    assert len(s) == 1 and s[0][0] == s[0][-1] and len(s[0]) > 10


def test_move_starts_a_new_stroke() -> None:
    s = strokes_from_ops(ops({"op": "move", "to": [0, 0]}, {"op": "line", "to": [5, 0]},
                             {"op": "move", "to": [0, 9]}, {"op": "line", "to": [5, 9]}))
    assert len(s) == 2


def test_line_without_move_is_a_readable_error() -> None:
    with pytest.raises(ValueError, match="start with a 'move'"):
        strokes_from_ops(ops({"op": "line", "to": [1, 1]}))


def test_unknown_op_is_rejected_by_the_schema() -> None:
    with pytest.raises(Exception):
        ops({"op": "teleport", "to": [1, 1]})


def test_svg_triangle_is_closed_with_the_right_length() -> None:
    s = svg_to_strokes("M0 0 L10 0 L10 10 Z")
    assert len(s) == 1 and math.dist(s[0][0], s[0][-1]) < 1e-6
    length = sum(math.dist(a, b) for a, b in zip(s[0], s[0][1:]))
    assert abs(length - (20 + math.hypot(10, 10))) < 0.2


def test_svg_relative_curves_and_bad_data() -> None:
    assert len(svg_to_strokes("m0 0 c5 10 15 10 20 0 s10 -10 20 0")[0]) > 20
    with pytest.raises(ValueError):
        svg_to_strokes("not a path")


def test_fit_centers_and_keeps_aspect() -> None:
    out = apply_transform_fit([[(0, 0), (10, 0), (10, 5)]], None, Fit(x=100, y=50, width=40, height=40, margin=2))
    x0, y0, x1, y1 = bbox(out)
    assert abs((x1 - x0) - 36) < 1e-9 and abs((y1 - y0) - 18) < 1e-9  # width-limited, aspect kept
    assert abs((y0 + y1) / 2 - 70) < 1e-9 and abs((x0 + x1) / 2 - 120) < 1e-9


def test_transform_rotates_about_a_point_and_mirrors() -> None:
    out = apply_transform_fit([[(10, 0)]], Transform(rotate_deg=90), None)
    assert abs(out[0][0][0]) < 1e-9 and abs(out[0][0][1] - 10) < 1e-9
    assert transform_strokes([[(3, 4)]], mirror_x=True)[0][0] == (-3, 4)


def test_shapes() -> None:
    hexagon = polygon_points(0, 0, 10, 6)
    assert len(hexagon) == 7 and hexagon[0] == hexagon[-1]
    tri = polygon_points(0, 0, 10, 3)
    assert tri[0] == tri[-1] and len(tri) == 4
    assert len(star_points(0, 0, 10, 4, 5)) == 11
    sp = spiral_points(0, 0, 1, 20, 3)
    assert abs(math.dist(sp[0], (0, 0)) - 1) < 1e-6 and abs(math.dist(sp[-1], (0, 0)) - 20) < 1e-6
    x0, y0, x1, y1 = bbox([hatch_points(5, 5, 20, 10, 2)])
    assert (x0, y0) == (5, 5) and x1 <= 25 and y1 <= 15
    e = ellipse_points(0, 0, 20, 10)
    assert abs(bbox([e])[2] - 20) < 1e-6 and abs(bbox([e])[3] - 10) < 0.2
    assert abs(bbox([heart_points(0, 0, 40)])[2] * 2 - 40) < 1.0
    assert abs(wave_points((0, 0), (40, 0), 5, 2)[-1][0] - 40) < 1e-6
    with pytest.raises(ValueError):
        polygon_points(0, 0, 10, 2)


def test_preview_flags_and_ascii() -> None:
    canvas = Canvas(0, 0, 100, 40)
    strokes = [[(10.0, 10.0), (60.0, 10.0), (60.0, 30.0)]]
    st = stats(strokes, canvas, travel_from=(0.0, 0.0))
    assert st["inside_canvas"] is True and st["length_mm"] == 70.0 and st["bbox_mm"] == [10.0, 10.0, 60.0, 30.0]
    assert abs(float(st["travel_marks_mm"]) - math.hypot(10, 10)) < 0.1  # type: ignore[arg-type]
    art = ascii_art(strokes, canvas)
    assert "S" in art and "E" in art and "#" in art
    loop = ascii_art([[(10.0, 10.0), (50.0, 10.0), (10.0, 10.0)]], canvas)
    assert "O" in loop and "S" not in loop
    d = describe([[(0.0, 0.0), (500.0, 0.0)]], canvas)
    assert d["inside_canvas"] is False and "<svg" in str(d["svg"])
