import math

import pytest

from penarm.arm import Arm
from penarm.canvas import safe_canvas
from penarm.config import ArmConfig
from penarm.errors import Unreachable
from penarm.kinematics import page_to_servos
from penarm.link import SimLink
from penarm.shapes import bezier_points, rect_points

CFG = ArmConfig()


def test_canvas_is_fully_reachable() -> None:
    c = safe_canvas(CFG)
    assert c.w > 20 and c.h > 20
    for fx in (0.0, 0.5, 1.0):
        for fy in (0.0, 0.5, 1.0):
            page_to_servos(CFG, *c.to_page(fx * c.w, fy * c.h))  # raises Unreachable if not


def test_draw_outside_canvas_rejected_and_nothing_moves() -> None:
    link = SimLink()
    arm = Arm(CFG, link)
    with pytest.raises(Unreachable, match="canvas"):
        arm.draw_polyline([(1.0, 1.0), (1.0, 1.5), (arm.canvas.w + 50, 1.0)])
    assert link.history == []


def test_draw_inside_canvas_moves_servos() -> None:
    link = SimLink()
    arm = Arm(CFG, link)
    arm.draw_polyline(rect_points(5.0, 5.0, 10.0, 10.0))
    assert len(link.history) > 40


def test_bezier_endpoints_and_rect_closed() -> None:
    pts = bezier_points((0, 0), (10, 30), (30, 30), (40, 0))
    assert pts[0] == (0, 0) and math.dist(pts[-1], (40, 0)) < 1e-9
    r = rect_points(1, 2, 3, 4)
    assert r[0] == r[-1] and len(r) == 5

