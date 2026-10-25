import math
from dataclasses import replace

import pytest

from penarm.calibration import (CORNER_ORDER, Observation, apply_homography, corner_sanity, fit, homography,
                                paper_point_from_photo, predict, suggest_poses)
from penarm.config import ArmConfig

CFG = ArmConfig()
# A made-up camera: maps paper mm to pixels with rotation, scale and perspective
CAM = [[3.0, 0.8, 120.0], [-0.6, 3.2, 90.0], [4e-4, -2e-4, 1.0]]


def to_px(p: tuple[float, float]) -> tuple[float, float]:
    return apply_homography(CAM, p)


def corners_px(w: float, h: float) -> dict[str, tuple[float, float]]:
    mm = {"near_left": (0, 0), "near_right": (w, 0), "far_right": (w, h), "far_left": (0, h)}
    return {k: to_px(v) for k, v in mm.items()}


def test_homography_maps_the_four_points_exactly() -> None:
    src = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)]
    dst = [(10.0, 5.0), (210.0, 20.0), (190.0, 120.0), (-5.0, 90.0)]
    h = homography(src, dst)
    for a, b in zip(src, dst):
        assert math.dist(apply_homography(h, a), b) < 1e-6


def test_point_is_recovered_in_paper_mm_under_perspective() -> None:
    truth = (123.0, 187.0)
    got = paper_point_from_photo(corners_px(200, 275), to_px(truth), 200, 275)
    assert math.dist(got, truth) < 1e-6


def test_missing_corner_and_swapped_order_are_caught() -> None:
    cs = corners_px(200, 275)
    with pytest.raises(ValueError, match="missing"):
        paper_point_from_photo({k: v for k, v in cs.items() if k != "far_left"}, (0.0, 0.0), 200, 275)
    swapped = {**cs, "near_right": cs["far_right"], "far_right": cs["near_right"]}
    assert corner_sanity(swapped) and not corner_sanity(cs)
    assert CORNER_ORDER[0] == "near_left"


def test_base_scope_re_registers_a_moved_paper_from_one_photo() -> None:
    truth = replace(CFG, base_x=130.0, base_y=-15.0)
    s1, s2 = 120.0, 45.0
    x, y = predict(truth, s1, s2)
    res = fit(CFG, [Observation(s1, s2, x, y)], scope="base")
    assert math.dist((res.cfg.base_x, res.cfg.base_y), (130.0, -15.0)) < 1e-3
    assert res.cfg.offset1 == CFG.offset1 and res.cfg.l1 == CFG.l1  # nothing else moved


def test_scope_minimums_and_unknown_scope() -> None:
    obs = [Observation(100.0, 60.0, 50.0, 150.0)]
    with pytest.raises(ValueError, match="at least 4"):
        fit(CFG, obs, scope="pose")
    with pytest.raises(ValueError, match="scope"):
        fit(CFG, obs, scope="everything")


def test_pose_fit_from_photo_derived_points() -> None:
    truth = replace(CFG, offset1=-9.0, offset2=110.0, base_x=118.0, base_y=-20.0)
    cs = corners_px(truth.page_w, truth.page_h)
    obs = []
    for s1, s2 in suggest_poses(truth, 6):
        tx, ty = predict(truth, s1, s2)
        x, y = paper_point_from_photo(cs, to_px((tx, ty)), truth.page_w, truth.page_h)
        obs.append(Observation(s1, s2, x, y))
    res = fit(CFG, obs)
    assert res.rmse_mm < 0.05 and abs(res.cfg.offset2 - 110.0) < 0.2
