import math

import pytest

from penarm.arm import Arm
from penarm.config import ArmConfig
from penarm.kinematics import Unreachable, fk, ik, interpolate, page_to_servos
from penarm.link import SimLink

CFG = ArmConfig()


@pytest.mark.parametrize("elbow_up", [True, False])
@pytest.mark.parametrize("pt", [(105.0, 100.0), (60.0, 150.0), (140.0, 60.0)])
def test_ik_fk_roundtrip(pt: tuple[float, float], elbow_up: bool) -> None:
    cfg = ArmConfig(elbow_up=elbow_up)
    x, y = fk(cfg, *ik(cfg, *pt))
    assert math.dist((x, y), pt) < 1e-6


def test_unreachable_far_point() -> None:
    with pytest.raises(Unreachable):
        ik(CFG, 105.0, 500.0)


def test_outside_page_rejected() -> None:
    with pytest.raises(Unreachable):
        page_to_servos(CFG, -5.0, 100.0)


def test_interpolate_ends_at_target() -> None:
    pts = interpolate((0, 0), (10, 0), 1.0)
    assert len(pts) == 10 and pts[-1] == (10, 0)


def test_failed_path_moves_nothing() -> None:
    link = SimLink()
    arm = Arm(CFG, link)
    with pytest.raises(Unreachable):
        arm.draw_polyline([(105.0, 100.0), (105.0, 100.5), (999.0, 999.0)])
    assert link.history == []
