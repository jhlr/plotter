from dataclasses import replace

import numpy as np
import pytest

from penarm.calibrate import _nearest, fit, outline, planned
from penarm.config import ArmConfig

CFG = ArmConfig()
BUILDS = [
    dict(sign1=1.0, sign2=0.85, offset1=6.0, offset2=137.0),
    dict(sign1=1.08, sign2=0.9, offset1=2.0, offset2=132.0),
    dict(sign1=0.98, sign2=0.8, offset1=5.5, offset2=139.0),
]


def test_a_perfect_arm_draws_the_plan() -> None:
    x0, y0, x1, y1 = planned(CFG)
    line = outline(CFG, CFG)
    assert line[:, 0].min() == pytest.approx(x0, abs=1.0)
    assert line[:, 0].max() == pytest.approx(x1, abs=1.0)
    assert line[:, 1].min() == pytest.approx(y0, abs=1.0)
    assert line[:, 1].max() == pytest.approx(y1, abs=1.0)


@pytest.mark.parametrize("d", BUILDS)
def test_fit_recovers_a_differently_built_arm_from_its_outline(d: dict[str, float]) -> None:
    truth = replace(CFG, **d)
    ink = outline(CFG, truth)
    got, rms = fit(CFG, ink)
    assert rms < 1.0  # offsets trade off against gains a little: the outline matches, the numbers need not be exact
    assert _nearest(ink, outline(CFG, replace(CFG, **got))).max() < 1.5


def test_fit_survives_a_millimetre_of_measuring_noise() -> None:
    truth = replace(CFG, sign1=1.02, sign2=0.9, offset1=6.0, offset2=137.0)
    ink = outline(CFG, truth)
    noisy = ink + np.random.default_rng(1).normal(0.0, 1.0, ink.shape)
    got, rms = fit(CFG, noisy)
    assert rms < 3.0
    assert _nearest(ink, outline(CFG, replace(CFG, **got))).max() < 3.0


def test_stray_marks_do_not_pull_the_fit() -> None:
    truth = replace(CFG, sign1=1.02, sign2=0.9, offset1=6.0, offset2=137.0)
    ink = outline(CFG, truth)
    x0, y0, x1, y1 = planned(CFG)
    strays = np.array([[x0 - 40.0, y0 - 40.0]] * 30 + [[x1 + 40.0, y1 + 40.0]] * 30)  # old ink far from the rectangle
    got, _ = fit(CFG, np.vstack([ink, strays]))
    assert _nearest(ink, outline(CFG, replace(CFG, **got))).max() < 1.5
