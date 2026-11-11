"""Reading the drawn rectangle from a photo: ink pixels (any pen colour), rectified to board mm with the board's four corners.
Corners are the four corners of the clipboard board in photo pixels, named by the board frame: origin = bottom-left, the
bottom edge is the one nearest the arm's servos, x to the right and y away from them. A photo from any side works as long as
each corner is labelled by what it is, not by where it lands in the photo."""
import cv2
import numpy as np
from numpy.typing import NDArray

Pts = NDArray[np.float64]
Rect = tuple[float, float, float, float]  # x0, y0, x1, y1 in page mm

LAB_L_MAX = 205
INKS = ("auto", "green", "blue", "red", "brown", "dark")  # `auto` = any pen; the others are colour hints for a photo `auto` struggles with
AUTO_DELTA = 20.0  # `auto`: Lab distance from the paper around the pixel above which it is ink (JPEG noise is ~3-5)
AUTO_SCALE = 8  # the paper colour is estimated on a photo this many times smaller, with a median far wider than a stroke
AUTO_WINDOW = 51
DARK_DROP = 70  # a `dark` ink pixel is this much darker (Lab L) than the median pixel of the photo


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(m[r][i]))
        m[i], m[p] = m[p], m[i]
        if abs(m[i][i]) < 1e-12:
            raise ValueError("the four points are degenerate (collinear?)")
        for r in range(i + 1, n):
            f = m[r][i] / m[i][i]
            m[r] = [x - f * y for x, y in zip(m[r], m[i])]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


def homography(src: list[tuple[float, float]], dst: list[tuple[float, float]]) -> list[list[float]]:
    """3x3 projective map taking the 4 src points to the 4 dst points (h33 = 1)."""
    if len(src) != 4 or len(dst) != 4:
        raise ValueError("a homography needs exactly 4 point pairs")
    a: list[list[float]] = []
    b: list[float] = []
    for (x, y), (u, v) in zip(src, dst):
        a += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        b += [u, v]
    h = _solve(a, b)
    return [h[0:3], h[3:6], [h[6], h[7], 1.0]]


def apply_homography(h: list[list[float]], p: tuple[float, float]) -> tuple[float, float]:
    w = h[2][0] * p[0] + h[2][1] * p[1] + h[2][2]
    return (h[0][0] * p[0] + h[0][1] * p[1] + h[0][2]) / w, (h[1][0] * p[0] + h[1][1] * p[1] + h[1][2]) / w


def thin(mask: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Zhang-Suen thinning: a stroke becomes a one-pixel centreline."""
    im = (mask > 0).astype(np.uint8)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            p = np.pad(im, 1)
            n = [p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:], p[2:, 2:], p[2:, 1:-1], p[2:, :-2], p[1:-1, :-2], p[:-2, :-2]]
            b = sum(n)
            seq = [*n, n[0]]
            a = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8) for i in range(8))
            c = ((n[0] * n[2] * n[4] == 0) & (n[2] * n[4] * n[6] == 0)) if step == 0 else (
                (n[0] * n[2] * n[6] == 0) & (n[0] * n[4] * n[6] == 0))
            remove = (im == 1) & (b >= 2) & (b <= 6) & (a == 1) & c
            if remove.any():
                im[remove] = 0
                changed = True
    return im


def _is_ink(lab: NDArray[np.uint8], ink: str) -> NDArray[np.bool_]:
    """Pixels whose colour is the ink's, from Lab (paper is ~127 on a and b; HSV saturation loses thin strokes)."""
    light, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    if ink == "auto":
        h, w = light.shape
        small = cv2.resize(lab, (max(1, w // AUTO_SCALE), max(1, h // AUTO_SCALE)), interpolation=cv2.INTER_AREA)
        paper = cv2.resize(cv2.medianBlur(small, AUTO_WINDOW), (w, h), interpolation=cv2.INTER_LINEAR)
        return np.asarray(np.linalg.norm(lab.astype(np.float32) - paper.astype(np.float32), axis=2) > AUTO_DELTA)
    if ink == "green":
        return (a < 115) & (light < LAB_L_MAX)  # green ink drops a below ~112
    if ink == "red":
        return (a > 140) & (light < LAB_L_MAX)
    if ink == "brown":
        return (a > 133) & (b > 135) & (light < LAB_L_MAX)  # brown: warm, between red (a high) and yellow (b high)
    if ink == "blue":
        return (b < 112) & (light < LAB_L_MAX)
    if ink == "dark":
        return light < float(np.median(light)) - DARK_DROP
    raise ValueError(f"unknown ink {ink!r}: choose one of {INKS}")


def ink_pixels(photo: NDArray[np.uint8], masked_out: list[tuple[int, int, int, int]], ink: str = "auto") -> NDArray[np.int64]:
    """(x, y) pixels of the one-pixel centreline of the ink; `masked_out` boxes (x0, y0, x1, y1 px) hide the pen."""
    mask = np.where(_is_ink(np.asarray(cv2.cvtColor(photo, cv2.COLOR_BGR2LAB), dtype=np.uint8), ink), 255, 0).astype(np.uint8)
    for x0, y0, x1, y1 in masked_out:
        mask[y0:y1, x0:x1] = 0
    blots = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41)))
    mask[cv2.dilate(blots, np.ones((21, 21), np.uint8)) > 0] = 0  # ink blots where the pen rested are not the path
    closed = np.asarray(cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)), dtype=np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    keep = np.isin(labels, [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > 500]).astype(np.uint8)
    ys, xs = np.nonzero(thin(keep * 255))
    return np.stack([xs, ys], 1)


def to_board_mm(px: NDArray[np.int64], corners_px: list[tuple[float, float]], page_w: float, page_h: float) -> Pts:
    """Photo pixels -> board mm. corners_px: bottom-left, bottom-right, top-right, top-left of the board."""
    h = np.array(homography(corners_px, [(0.0, 0.0), (page_w, 0.0), (page_w, page_h), (0.0, page_h)]))
    p = np.c_[px.astype(float), np.ones(len(px))] @ h.T
    return np.asarray(p[:, :2] / p[:, 2:3], dtype=np.float64)


def _parse_corners(text: str) -> list[tuple[float, float]]:
    pts = [tuple(float(v) for v in pair.split(",")) for pair in text.split()]
    if len(pts) != 4 or any(len(p) != 2 for p in pts):
        raise SystemExit('--corners needs four "x,y" pairs: bottom-left bottom-right top-right top-left (photo pixels)')
    return [(p[0], p[1]) for p in pts]


def _write_overlay(path: str, ink: Pts, rect: Rect, fitted: Pts | None = None) -> None:
    sc = 4
    x0, y0, x1, y1 = rect
    lo_y, hi_y = y0 - 40, y1 + 40
    img = np.full((int((hi_y - lo_y) * sc), int(260 * sc), 3), 255, np.uint8)

    def pt(p: tuple[float, float]) -> tuple[int, int]:
        return int(p[0] * sc), int((hi_y - p[1]) * sc)

    for p in ink:
        if lo_y <= p[1] <= hi_y:
            cv2.circle(img, pt((p[0], p[1])), 1, (0, 140, 0), -1)
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    for a, b in zip(corners[:-1], corners[1:]):
        cv2.line(img, pt(a), pt(b), (0, 0, 255), 1)
    if fitted is not None:  # where the arm would draw the plan with the fitted calibration (blue)
        for a, b in zip(fitted[:-1], fitted[1:]):
            cv2.line(img, pt((a[0], a[1])), pt((b[0], b[1])), (255, 80, 0), 1)
    cv2.imwrite(path, img)
