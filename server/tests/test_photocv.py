"""Hand-held photo understanding, on synthetic scenes (a ruled sheet, a white board, a blue arm) and a pinhole model."""
import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from penarm.calibration import apply_homography, homography
from penarm.photocv import PhotoError, analyze, tip_from_ring

W, H = 1000, 1400
PAPER_W, PAPER_H = 176.0, 240.0  # the ruled block, mm
PPM = 4.0  # px per mm in the flat scene


def flat_scene(lines: int = 26, torn: bool = False) -> tuple[np.ndarray, dict[str, tuple[float, float]], tuple[float, float]]:
    """Top-down scene: grey table, white board, ruled block, blue holder with a hole at the bottom, two servo cases.
    Returns (image, ruled-block corners as drawn, ring centre)."""
    img = np.full((H, W, 3), (118, 120, 122), np.uint8)
    cv2.rectangle(img, (60, 60), (940, 1330), (245, 245, 245), -1)  # board
    x0, y0 = 150, 200
    x1, y1 = int(x0 + PAPER_W * PPM), int(y0 + PAPER_H * PPM)
    cv2.rectangle(img, (x0 - 30, y0 - 40), (x1 + 30, y1 + 40), (235, 235, 235), -1)  # sheet a little larger than the lines
    gap = (y1 - y0) / (lines - 1)
    for i in range(lines):
        y = int(y0 + i * gap)
        cv2.line(img, (x0, y), (x1, y), (95, 95, 95), 2)
    if torn:
        cv2.line(img, (500, y0 - 40), (520, y1 + 40), (250, 250, 250), 10)  # a tear that shifts nothing but hides line ends
    # arm: light blue strip + holder ring (with a hole) near the bottom of the board, servo cases below it
    ring = (560.0, 1050.0)
    cv2.circle(img, (int(ring[0]), int(ring[1])), 55, (255, 175, 70), -1)
    cv2.circle(img, (int(ring[0]), int(ring[1])), 23, (225, 225, 225), -1)
    cv2.line(img, (int(ring[0]), int(ring[1]) + 40), (360, 1290), (255, 175, 70), 14)
    cv2.rectangle(img, (300, 1240), (420, 1320), (255, 175, 70), -1)
    cv2.rectangle(img, (330, 1250), (380, 1300), (140, 70, 25), -1)  # servo case (dark blue)
    cv2.rectangle(img, (440, 1110), (500, 1170), (140, 70, 25), -1)  # elbow servo case
    corners = {"tl": (float(x0), float(y0)), "tr": (float(x1), float(y0)), "br": (float(x1), float(y1)), "bl": (float(x0), float(y1))}
    return img, corners, ring


def photograph(img: np.ndarray, corners: dict[str, tuple[float, float]], ring: tuple[float, float], rot: float = 8.0,
               skew: float = 6e-5) -> tuple[np.ndarray, dict[str, tuple[float, float]], tuple[float, float]]:
    """A hand-held shot: rotate about the scene's centre inside a square frame and add a little perspective."""
    size = 1500
    a = math.radians(rot)
    rot_m = np.array([[math.cos(a), -math.sin(a), 0.0], [math.sin(a), math.cos(a), 0.0], [0.0, 0.0, 1.0]])
    to_centre = np.array([[1.0, 0.0, -W / 2], [0.0, 1.0, -H / 2], [0.0, 0.0, 1.0]])
    to_frame = np.array([[1.0, 0.0, size / 2], [0.0, 1.0, size / 2], [0.0, 0.0, 1.0]])
    persp = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [skew, -skew, 1.0]])
    m = to_frame @ persp @ rot_m @ to_centre
    out = cv2.warpPerspective(img, m, (size, size), borderValue=(118, 120, 122))
    hm = m.tolist()
    return np.asarray(out), {k: apply_homography(hm, v) for k, v in corners.items()}, apply_homography(hm, ring)


def save(img: np.ndarray, tmp_path: Path) -> Path:
    p = tmp_path / "shot.png"
    cv2.imwrite(str(p), img)
    return p


def expected_corners(c: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    # the arm's base is below the board in the flat scene, so near = the bottom edge of the ruled block as drawn
    return {"near_left": c["bl"], "near_right": c["br"], "far_right": c["tr"], "far_left": c["tl"]}


@pytest.mark.parametrize("rot", [0.0, 8.0, 90.0])
def test_finds_the_ruled_block_the_ring_and_the_orientation(tmp_path: Path, rot: float) -> None:
    flat, corners, ring = flat_scene()
    shot, c, r = photograph(flat, corners, ring, rot=rot)
    res = analyze(save(shot, tmp_path))
    assert res.confidence >= 0.7 and res.ring_px is not None and res.base_px is not None
    assert math.dist(res.ring_px, r) < 8
    for name, p in expected_corners(c).items():  # near/far/left/right come from where the arm is, whatever the rotation
        assert math.dist(res.corners_px[name], p) < 0.01 * W, name


@pytest.mark.parametrize("rot", [-12.0, 180.0])
def test_known_limit_a_line_hidden_by_the_arm_moves_that_edge_by_about_one_line(tmp_path: Path, rot: float) -> None:
    """When the arm hides the extreme ruled line, the block ends one line short on that side (~1 line spacing, here
    ~40 px of 1060): documented, bounded, and the overlay shows it."""
    flat, corners, ring = flat_scene()
    shot, c, r = photograph(flat, corners, ring, rot=rot)
    res = analyze(save(shot, tmp_path))
    for name, p in expected_corners(c).items():
        assert math.dist(res.corners_px[name], p) < 0.09 * W, name


def test_refuses_a_photo_with_no_ruled_paper(tmp_path: Path) -> None:
    blank = np.full((H, W, 3), (120, 120, 120), np.uint8)
    with pytest.raises(PhotoError, match="ruled"):
        analyze(save(blank, tmp_path))


def test_refuses_too_few_lines(tmp_path: Path) -> None:
    flat, corners, ring = flat_scene(lines=5)
    with pytest.raises(PhotoError):
        analyze(save(flat, tmp_path))


def test_perspective_correction_recovers_the_tip_on_the_paper() -> None:
    """Pinhole camera H mm above the paper, centred; the holder's top face is h mm above the paper."""
    cam_h, ring_h, f = 400.0, 45.0, 3000.0  # mm, mm, px
    cx, cy = 1536.0, 2048.0

    def project(x: float, y: float, z: float) -> tuple[float, float]:
        return cx + f * (x - 90.0) / (cam_h - z), cy - f * (y - 120.0) / (cam_h - z)  # camera above (90, 120)

    paper_w, paper_h = 176.0, 240.0
    corners = {"near_left": project(0, 0, 0), "near_right": project(paper_w, 0, 0),
               "far_right": project(paper_w, paper_h, 0), "far_left": project(0, paper_h, 0)}
    tip = (130.0, 170.0)  # the pen axis, in paper mm
    ring_px = project(*tip, ring_h)
    ring_diam_px = f * 11.4 / (cam_h - ring_h)
    got, k, warn = tip_from_ring(ring_px, ring_diam_px, (3072, 4096), corners, paper_w, paper_h)
    assert math.dist(got, tip) < 1.0 and abs(k - cam_h / (cam_h - ring_h)) < 0.02 and not warn
    naive = apply_homography(homography([corners[k_] for k_ in ("near_left", "near_right", "far_right", "far_left")],
                                         [(0, 0), (paper_w, 0), (paper_w, paper_h), (0, paper_h)]), ring_px)
    assert math.dist(naive, tip) > 5.0  # without the correction the ring would have been mistaken for the tip
