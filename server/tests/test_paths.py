import math

import pytest
from penarm.canvas import Canvas
from penarm.paths import apply_transform_fit, strokes_from_ops, svg_to_strokes
from penarm.preview import ascii_art, describe, stats
from penarm.shapes import (bbox, ellipse_points, heart_points, hatch_points, polygon_points, spiral_points,
                           star_points, transform_strokes, wave_points)

def test_ops_build_one_stroke_and_close_it() -> None:
    s = strokes_from_ops(["move 0 0", "line 10 0", "bezier 12 3 12 7 10 10", "close"])
    assert len(s) == 1 and s[0][0] == s[0][-1] and len(s[0]) > 10


def test_ops_accept_commas_and_any_case() -> None:
    s = strokes_from_ops(["MOVE 0,0", "Line 5, 0", "arc 5 5 5 -90 90"])
    assert len(s) == 1 and s[0][1] == (5.0, 0.0)


def test_move_starts_a_new_stroke() -> None:
    assert len(strokes_from_ops(["move 0 0", "line 5 0", "move 0 9", "line 5 9"])) == 2


@pytest.mark.parametrize("ops,message", [
    (["line 1 1"], "start with a 'move'"),
    (["move 0"], "expected move x y"),
    (["teleport 1 1"], "unknown operation"),
    (["move a b"], "must be numbers"),
    (["move 0 0", "arc 1 2 3"], "expected arc cx cy r a0 a1"),
    ([], "no drawable"),
])
def test_bad_ops_are_readable_errors(ops: list[str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        strokes_from_ops(ops)


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
    out = apply_transform_fit([[(0, 0), (10, 0), (10, 5)]], fit_box=[100, 50, 40, 40], fit_margin=2)
    x0, y0, x1, y1 = bbox(out)
    assert abs((x1 - x0) - 36) < 1e-9 and abs((y1 - y0) - 18) < 1e-9  # width-limited, aspect kept
    assert abs((y0 + y1) / 2 - 70) < 1e-9 and abs((x0 + x1) / 2 - 120) < 1e-9


def test_transform_rotates_about_a_point_and_mirrors() -> None:
    out = transform_strokes([[(10.0, 0.0)]], rotate_deg=90)
    assert abs(out[0][0][0]) < 1e-9 and abs(out[0][0][1] - 10) < 1e-9
    assert transform_strokes([[(3.0, 4.0)]], mirror_x=True)[0][0] == (-3.0, 4.0)
    # through the portable entry point: pivots on the drawing's own center, not on the origin
    square = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]]
    x0, y0, x1, y1 = bbox(apply_transform_fit(square, rotate_deg=90, translate_x=100.0))
    assert abs((x0 + x1) / 2 - 105.0) < 1e-9 and abs((y0 + y1) / 2 - 5.0) < 1e-9


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
