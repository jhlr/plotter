import cv2
import numpy as np
import pytest

from penarm.calibration import apply_homography, homography
from penarm.inkcal import _parse_corners, ink_pixels, measure, to_board_mm

CORNERS_PX = [(100.0, 900.0), (650.0, 880.0), (640.0, 100.0), (110.0, 110.0)]  # board BL, BR, TR, TL as photographed
RECT = (23.0, 163.0, 201.0, 223.0)


def _photo(top_error: float, right_error: float, colour: tuple[int, int, int] = (30, 140, 40)) -> np.ndarray:
    """A synthetic phone photo: white board, green rectangle whose top edge is `top_error` mm too high and whose right
    edge is `right_error` mm too far right."""
    mm_to_px = homography([(0.0, 0.0), (230.0, 0.0), (230.0, 330.0), (0.0, 330.0)], CORNERS_PX)
    x0, y0, x1, y1 = RECT

    def px(x: float, y: float) -> tuple[int, int]:
        u, v = apply_homography(mm_to_px, (x, y))
        return int(round(u)), int(round(v))

    img = np.full((1000, 760, 3), 255, np.uint8)
    path = [(x0, y0), (x1 + right_error, y0), (x1 + right_error, y1 + top_error), (x0, y1 + top_error), (x0, y0)]
    for a, b in zip(path[:-1], path[1:]):
        for t in np.linspace(0, 1, 200):  # many short segments: the lines are curves in the photo's perspective
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            cv2.circle(img, px(*p), 2, colour, -1)
    return img


def test_measure_recovers_the_edge_errors_of_a_synthetic_photo() -> None:
    ink = to_board_mm(ink_pixels(_photo(top_error=5.0, right_error=-4.0), []), CORNERS_PX, 230.0, 330.0)
    mesh, stats = measure(ink, RECT, None, gain=1.0)
    mid = len(mesh.top[1]) // 2
    assert mesh.top[1][mid] == pytest.approx(5.0, abs=1.0)  # top edge ink is 5 mm above the plan
    assert mesh.bottom[1][mid] == pytest.approx(0.0, abs=1.0)
    assert mesh.right[1][len(mesh.right[1]) // 2] == pytest.approx(-4.0, abs=1.0)
    assert stats["positions_measured"][0] >= 20  # type: ignore[index]


def test_a_second_pass_adds_only_the_error_that_is_left() -> None:
    ink = to_board_mm(ink_pixels(_photo(top_error=5.0, right_error=0.0), []), CORNERS_PX, 230.0, 330.0)
    first, _ = measure(ink, RECT, None, gain=1.0)
    same_again, _ = measure(ink, RECT, first, gain=1.0)  # the old mesh already predicts it: the leftover would be added twice
    mid = len(first.top[1]) // 2
    assert same_again.top[1][mid] == pytest.approx(2 * first.top[1][mid], abs=1.0)


def test_pen_box_is_ignored() -> None:
    img = _photo(0.0, 0.0)
    cv2.rectangle(img, (300, 400), (318, 600), (30, 140, 40), -1)  # a thin green pen barrel (not a blot: it survives that filter)
    with_pen = ink_pixels(img, [])
    without = ink_pixels(img, [(290, 390, 330, 610)])
    assert len(without) < len(with_pen)


def test_corners_argument_needs_four_points() -> None:
    assert _parse_corners("1,2 3,4 5,6 7,8")[3] == (7.0, 8.0)
    with pytest.raises(SystemExit):
        _parse_corners("1,2 3,4")


@pytest.mark.parametrize("ink,bgr", [("green", (30, 140, 40)), ("blue", (170, 60, 20)), ("red", (30, 30, 200)), ("dark", (40, 35, 35))])
def test_every_ink_colour_is_read_to_the_same_rectangle(ink: str, bgr: tuple[int, int, int]) -> None:
    got = to_board_mm(ink_pixels(_photo(top_error=5.0, right_error=0.0, colour=bgr), [], ink), CORNERS_PX, 230.0, 330.0)
    assert abs(float(np.percentile(got[:, 1], 99.5)) - (RECT[3] + 5.0)) < 2.0


def test_green_pen_is_not_read_as_blue_ink() -> None:
    assert len(ink_pixels(_photo(0.0, 0.0), [], "blue")) < 500
