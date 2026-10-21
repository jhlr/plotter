"""Synthetic scene: markers + green tag on a page canvas, warped by a known perspective into a 'camera frame'."""
import math

import cv2
import numpy as np
import pytest

from penarm.config import ArmConfig, VISION
from penarm.errors import VisionError
from penarm.vision import Fix, Frame, PencilLocator

PPM = 4  # canvas px per mm
ARM = ArmConfig()
WARP = np.array([[0.9, 0.08, 40.0], [-0.05, 0.95, 30.0], [2e-5, 1e-5, 1.0]])  # mild perspective


def scene(tag_mm: tuple[float, float] | None, hide_marker: int | None = None) -> Frame:
    h, w = int(ARM.page_h * PPM), int(ARM.page_w * PPM)
    canvas = np.full((h, w, 3), 255, np.uint8)
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, VISION.aruco_dict))
    side = int(VISION.marker_size_mm * PPM)
    for i, x, y in VISION.marker_centers:
        if i == hide_marker:
            continue
        m = cv2.cvtColor(cv2.aruco.generateImageMarker(d, i, side), cv2.COLOR_GRAY2BGR)
        cx, cy = int(x * PPM), int((ARM.page_h - y) * PPM)  # image y points down
        canvas[cy - side // 2 : cy + side // 2, cx - side // 2 : cx + side // 2] = m
    if tag_mm:
        cv2.circle(canvas, (int(tag_mm[0] * PPM), int((ARM.page_h - tag_mm[1]) * PPM)), 8, (0, 200, 0), -1)
    return np.asarray(cv2.warpPerspective(canvas, WARP, (w + 120, h + 120), borderValue=(255, 255, 255)), np.uint8)


class Fixed:
    def __init__(self, frame: Frame) -> None:
        self.frame = frame

    def read(self) -> Frame:
        return self.frame


def test_recovers_known_tag_position() -> None:
    # The scene's page axes are flipped vs the canvas (y up), so mm coords must come back as drawn.
    # Markers sit at mm positions in a y-up frame; the homography is learned from them, not assumed.
    truth = (70.0, 120.0)
    fix = PencilLocator(ARM, Fixed(scene(truth))).locate()
    assert math.dist((fix.x_mm, fix.y_mm), truth) < 1.0
    assert fix.seen == fix.frames and fix.in_page and fix.spread_mm < 0.5


def test_no_tag_raises() -> None:
    with pytest.raises(VisionError, match="tag"):
        PencilLocator(ARM, Fixed(scene(None))).locate()


def test_missing_marker_raises_before_any_calibration() -> None:
    with pytest.raises(VisionError, match="markers"):
        PencilLocator(ARM, Fixed(scene((70.0, 120.0), hide_marker=2))).locate()


def test_fix_type_is_plain_numbers() -> None:
    fix = PencilLocator(ARM, Fixed(scene((30.0, 40.0)))).locate()
    assert isinstance(fix, Fix) and all(isinstance(v, (int, float, bool)) for v in vars(fix).values())
