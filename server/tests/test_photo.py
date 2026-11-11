import cv2
import numpy as np
import pytest

from penarm.photo import _parse_corners, apply_homography, homography, ink_pixels, to_board_mm

CORNERS_PX = [(100.0, 900.0), (650.0, 880.0), (640.0, 100.0), (110.0, 110.0)]  # board BL, BR, TR, TL as photographed
RECT = (23.0, 163.0, 201.0, 223.0)


def _photo(top_error: float, right_error: float, colour: tuple[int, int, int] = (30, 140, 40)) -> np.ndarray:
    """A synthetic phone photo: white board, a rectangle in `colour` whose top edge is `top_error` mm too high and whose right
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


def test_ink_lands_on_the_drawn_rectangle_in_board_mm() -> None:
    ink = to_board_mm(ink_pixels(_photo(top_error=5.0, right_error=-4.0), []), CORNERS_PX, 230.0, 330.0)
    x0, y0, x1, y1 = RECT
    assert ink[:, 0].min() == pytest.approx(x0, abs=1.5)
    assert ink[:, 0].max() == pytest.approx(x1 - 4.0, abs=1.5)
    assert ink[:, 1].min() == pytest.approx(y0, abs=1.5)
    assert ink[:, 1].max() == pytest.approx(y1 + 5.0, abs=1.5)


def test_pen_box_is_ignored() -> None:
    img = _photo(0.0, 0.0)
    cv2.rectangle(img, (300, 400), (318, 600), (30, 140, 40), -1)  # a thin pen barrel (not a blot: it survives that filter)
    with_pen = ink_pixels(img, [])
    without = ink_pixels(img, [(290, 390, 330, 610)])
    assert len(without) < len(with_pen)


def test_corners_argument_needs_four_points() -> None:
    assert _parse_corners("1,2 3,4 5,6 7,8")[3] == (7.0, 8.0)
    with pytest.raises(SystemExit):
        _parse_corners("1,2 3,4")


PENS = {"green": (30, 140, 40), "blue": (170, 60, 20), "red": (30, 30, 200), "black": (40, 35, 35), "orange": (30, 120, 240),
        "purple": (150, 40, 130), "yellow marker": (60, 215, 235)}


@pytest.mark.parametrize("pen", PENS)
def test_auto_reads_any_pen_to_the_same_rectangle(pen: str) -> None:
    got = to_board_mm(ink_pixels(_photo(top_error=5.0, right_error=0.0, colour=PENS[pen]), []), CORNERS_PX, 230.0, 330.0)
    assert abs(float(np.percentile(got[:, 1], 99.5)) - (RECT[3] + 5.0)) < 2.0


def test_auto_ignores_uneven_lighting() -> None:
    img = _photo(top_error=5.0, right_error=0.0, colour=PENS["blue"])
    shade = np.linspace(1.0, 0.7, img.shape[1], dtype=np.float32)[None, :, None]  # light fades towards one side
    shaded = np.where(img > 250, (img * shade).astype(np.uint8), img)
    got = to_board_mm(ink_pixels(shaded, []), CORNERS_PX, 230.0, 330.0)
    assert abs(float(np.percentile(got[:, 1], 99.5)) - (RECT[3] + 5.0)) < 2.0


@pytest.mark.parametrize("ink,bgr", [("green", (30, 140, 40)), ("blue", (170, 60, 20)), ("red", (30, 30, 200)), ("dark", (40, 35, 35))])
def test_colour_hints_read_the_same_rectangle(ink: str, bgr: tuple[int, int, int]) -> None:
    got = to_board_mm(ink_pixels(_photo(top_error=5.0, right_error=0.0, colour=bgr), [], ink), CORNERS_PX, 230.0, 330.0)
    assert abs(float(np.percentile(got[:, 1], 99.5)) - (RECT[3] + 5.0)) < 2.0


def test_green_pen_is_not_read_as_blue_ink() -> None:
    assert len(ink_pixels(_photo(0.0, 0.0), [], "blue")) < 500


def test_brown_ink_is_told_apart_from_green_and_paper() -> None:
    import cv2
    import numpy as np

    from penarm.photo import _is_ink

    bgr = np.array([[[30, 60, 110], [40, 150, 40], [235, 235, 235]]], dtype=np.uint8)  # brown, green, paper
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    assert _is_ink(lab, "brown").tolist() == [[True, False, False]]
    assert _is_ink(lab, "green").tolist() == [[False, True, False]]
