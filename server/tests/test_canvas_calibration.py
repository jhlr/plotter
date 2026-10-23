import math
import random

import pytest

from penarm.arm import Arm
from penarm.calibration import CalibrationStore, Observation, fit, predict, suggest_poses
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


def _truth() -> ArmConfig:
    from dataclasses import replace

    return replace(CFG, offset1=-4.0, offset2=96.0, base_x=118.0, base_y=-35.0)


def _observations(truth: ArmConfig, noise: float = 0.0, n: int = 8) -> list[Observation]:
    rng = random.Random(1)
    out = []
    for s1, s2 in suggest_poses(truth, n):
        x, y = predict(truth, s1, s2)
        out.append(Observation(s1, s2, x + rng.gauss(0, noise), y + rng.gauss(0, noise)))
    return out


def test_fit_recovers_offsets_and_base_from_wrong_start() -> None:
    truth = _truth()
    res = fit(CFG, _observations(truth))
    assert res.rmse_mm < 0.05
    assert abs(res.cfg.offset1 - truth.offset1) < 0.2 and abs(res.cfg.offset2 - truth.offset2) < 0.2
    assert math.dist((res.cfg.base_x, res.cfg.base_y), (truth.base_x, truth.base_y)) < 0.5


def test_fit_tolerates_ruler_noise() -> None:
    res = fit(CFG, _observations(_truth(), noise=1.0, n=10))
    assert res.rmse_mm < 2.0


def test_fit_picks_flipped_sign() -> None:
    from dataclasses import replace

    truth = replace(_truth(), sign2=-1.0, offset2=60.0)
    res = fit(CFG, _observations(truth))
    assert res.cfg.sign2 == -1.0 and res.rmse_mm < 0.1


def test_fit_needs_enough_points() -> None:
    with pytest.raises(ValueError, match="at least"):
        fit(CFG, _observations(_truth(), n=3))


def test_store_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "cal.json"
    store = CalibrationStore(path)
    for o in _observations(_truth()):
        store.add_point(o)
    res = store.fit(CFG)
    again = CalibrationStore(path)
    assert len(again.points) == 8
    assert abs(again.apply(CFG).offset1 - res.cfg.offset1) < 1e-9


def test_portrait_canvas_is_tall_reachable_and_side_aware() -> None:
    from penarm.canvas import portrait_canvas

    left = portrait_canvas(CFG, side="left")
    right = portrait_canvas(CFG, side="right")
    assert left.h >= 1.5 * left.w and right.h >= 1.5 * right.w
    assert left.x0 + left.w / 2 < CFG.page_w / 5 < 4 * CFG.page_w / 5 < right.x0 + right.w / 2
    for port in (left, right, portrait_canvas(CFG)):
        for fx in (0.0, 1.0):
            for fy in (0.0, 0.5, 1.0):
                page_to_servos(CFG, *port.to_page(fx * port.w, fy * port.h))
