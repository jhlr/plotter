"""Hand-held phone photo -> where the paper and the pen holder are, with no markers and no fixed camera.

The paper is found from its own ruled lines (their dominant direction, then the four lines that bound the ruled
block: first line, last line, and robust fits through the left and right line ends), so perspective is handled by the
homography that follows. The arm is found by its blue plastic; the pen holder is the circular hole at the arm's free
end. Everything returns pixels in the ORIGINAL image plus a confidence and warnings; a debug overlay can be written."""
import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

Img = NDArray[np.uint8]
P2 = tuple[float, float]
MAX_SIDE = 1400  # analysis resolution (longest side); results are scaled back to the original image


class PhotoError(ValueError):
    """The photo cannot be understood (no ruled paper, no arm...): the message says what to retake."""


@dataclass
class PhotoAnalysis:
    corners_px: dict[str, P2]  # near_left, near_right, far_right, far_left (of the ruled block), original pixels
    ring_px: P2 | None  # centre of the pen holder's hole (top face), original pixels
    ring_diameter_px: float | None
    base_px: P2 | None  # free end of the arm opposite the pen holder (the shoulder), original pixels
    confidence: float
    warnings: list[str] = field(default_factory=list)
    lines_found: int = 0
    image_wh: tuple[int, int] = (0, 0)  # size of the original image


def _load(path: str | Path) -> tuple[Img, float]:
    img = cv2.imread(str(path))
    if img is None:
        raise PhotoError(f"cannot read image {path}")
    scale = min(1.0, MAX_SIDE / max(img.shape[:2]))
    if scale < 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return np.asarray(img, dtype=np.uint8), scale


def _blue_mask(img: Img) -> Img:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (92, 90, 150), (112, 255, 255))  # the light-blue PLA; ink blots and servo cases are darker
    return np.asarray(cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)), dtype=np.uint8)


# ---------------------------------------------------------------- ruled paper ----


def _ruled_segments(gray: Img, blue: Img) -> list[tuple[float, float, float, float]]:
    """Long, thin, dark line segments (candidate ruled lines), with the blue arm masked out."""
    k = max(9, int(min(gray.shape) * 0.012) | 1)
    thin = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    thin = np.asarray(cv2.GaussianBlur(thin, (3, 3), 0), dtype=np.uint8)
    _, bw = cv2.threshold(thin, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bw[cv2.dilate(blue, np.ones((9, 9), np.uint8)) > 0] = 0
    min_len = int(max(gray.shape) * 0.12)
    segs = cv2.HoughLinesP(bw, 1, np.pi / 720, threshold=60, minLineLength=min_len, maxLineGap=int(min_len * 0.35))
    return [] if segs is None else [(float(a), float(b), float(c), float(d)) for a, b, c, d in segs.reshape(-1, 4)]


def _dominant_direction(segs: list[tuple[float, float, float, float]]) -> float:
    """Length-weighted dominant angle (radians, mod pi), refined as the weighted circular mean near the histogram peak."""
    ang = np.array([math.atan2(y2 - y1, x2 - x1) % math.pi for x1, y1, x2, y2 in segs])
    w = np.array([math.hypot(x2 - x1, y2 - y1) for x1, y1, x2, y2 in segs])
    hist, edges = np.histogram(ang, bins=180, range=(0, math.pi), weights=w)
    hist = np.convolve(np.r_[hist[-2:], hist, hist[:2]], np.ones(5), "same")[2:-2]
    peak = float((edges[int(np.argmax(hist))] + edges[int(np.argmax(hist)) + 1]) / 2)
    d = (ang - peak + math.pi / 2) % math.pi - math.pi / 2
    near = np.abs(d) < math.radians(5)
    return float((peak + np.average(d[near], weights=w[near])) % math.pi)


def _fit_line(points: NDArray[np.float64]) -> tuple[P2, P2]:
    """Robust line through points: (point, unit direction)."""
    v = cv2.fitLine(points.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).flatten()
    return (float(v[2]), float(v[3])), (float(v[0]), float(v[1]))


def _intersect(a: tuple[P2, P2], b: tuple[P2, P2]) -> P2:
    (px, py), (dx, dy) = a
    (qx, qy), (ex, ey) = b
    den = dx * ey - dy * ex
    if abs(den) < 1e-9:
        raise PhotoError("ruled-block edges are parallel: the photo is too oblique or the lines were misdetected")
    t = ((qx - px) * ey - (qy - py) * ex) / den
    return px + t * dx, py + t * dy


def _periodic_run(lines: list[tuple[float, float, float, NDArray[np.float64]]]
                  ) -> tuple[list[tuple[float, float, float, NDArray[np.float64]]], int]:
    """Keep the longest run of evenly spaced lines (ruled paper is periodic; board and clip edges that happen to be
    parallel to it are not). Spacing may drift with perspective, so each step is compared with the previous one;
    one or more missing lines (a gap of 2x, 3x...) are tolerated."""
    best: list[int] = []
    for start in range(len(lines)):
        run = [start]
        prev = None
        for k in range(start + 1, len(lines)):
            d = lines[k][2] - lines[run[-1]][2]
            if prev is None:
                if 3 <= d < 400:  # a first step decides the spacing, as long as it is a plausible line distance
                    run.append(k)
                    prev = d
                continue
            mult = round(d / prev)
            if 1 <= mult <= 4 and abs(d - mult * prev) < 0.28 * prev * mult:
                run.append(k)
                prev = d / mult
        if len(run) > len(best):
            best = run
    kept = [lines[i] for i in best]
    gaps = 0
    for a, b in zip(best, best[1:]):
        gaps += max(0, round((lines[b][2] - lines[a][2]) / max(1.0, (lines[best[-1]][2] - lines[best[0]][2]) / max(1, len(best) - 1))) - 1)
    return kept, gaps


def find_ruled_block(img: Img, blue: Img) -> tuple[list[P2], int, list[str]]:
    """The four corners (image order tl, tr, br, bl of the block as photographed) of the ruled area, #lines, warnings."""
    gray = np.asarray(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), dtype=np.uint8)
    segs = _ruled_segments(gray, blue)
    if len(segs) < 8:
        raise PhotoError("no ruled paper found: show the lined sheet and avoid heavy glare")
    theta = _dominant_direction(segs)
    u = np.array([math.cos(theta), math.sin(theta)])  # along the lines
    n = np.array([-u[1], u[0]])  # across the lines
    keep = []
    for x1, y1, x2, y2 in segs:
        a = math.atan2(y2 - y1, x2 - x1) % math.pi
        if abs((a - theta + math.pi / 2) % math.pi - math.pi / 2) < math.radians(4):
            keep.append((x1, y1, x2, y2))
    # merge segments into lines by their offset across the lines
    items = sorted(((np.dot(n, [(x1 + x2) / 2, (y1 + y2) / 2]), x1, y1, x2, y2) for x1, y1, x2, y2 in keep))
    lines: list[list[tuple[float, float, float, float]]] = []
    last = -1e9
    for off, x1, y1, x2, y2 in items:
        if off - last > 4.0:
            lines.append([])
        lines[-1].append((x1, y1, x2, y2))
        last = off
    # a real ruled line spans a good part of the block: keep lines whose merged length is large enough
    spans = []
    for seg_list in lines:
        pts = np.array([[x, y] for s in seg_list for x, y in ((s[0], s[1]), (s[2], s[3]))])
        along = pts @ u
        spans.append((float(along.min()), float(along.max()), float(np.mean(pts @ n)), pts))
    if len(spans) < 6:
        raise PhotoError("too few ruled lines detected: retake the photo with the whole ruled area in view")
    lengths = np.array([b - a for a, b, _, _ in spans])
    good = [s for s, ln in zip(spans, lengths) if ln > 0.5 * np.median(lengths)]
    good.sort(key=lambda s: s[2])
    good, gaps = _periodic_run(good)
    if len(good) < 6:
        raise PhotoError("too few evenly spaced ruled lines: the sheet may be torn or folded; retake with the whole ruled area flat")
    first, last_line = good[0], good[-1]
    left_pts = np.array([[a * u[0] + off * n[0], a * u[1] + off * n[1]] for a, _, off, _ in good])
    right_pts = np.array([[b * u[0] + off * n[0], b * u[1] + off * n[1]] for _, b, off, _ in good])
    lines4 = {
        "first": _fit_line(first[3]), "last": _fit_line(last_line[3]),
        "left": _fit_line(left_pts), "right": _fit_line(right_pts),
    }
    corners = [_intersect(lines4["first"], lines4["left"]), _intersect(lines4["first"], lines4["right"]),
               _intersect(lines4["last"], lines4["right"]), _intersect(lines4["last"], lines4["left"])]
    # plausibility: a wrong quad must be refused, never trusted (scribbles and torn sheets break the line ends)
    h, w = img.shape[:2]
    margin = 0.08
    if any(not (-margin * w <= x <= (1 + margin) * w and -margin * h <= y <= (1 + margin) * h) for x, y in corners):
        raise PhotoError("the ruled block does not fit the photo (heavy ink, folds or a torn sheet confuse the line ends): "
                         "retake with the whole lined area visible, or give the corners yourself")
    # a photographed rectangle keeps nearly right angles and similar opposite edges unless the camera is very oblique
    for i in range(4):
        pa, pb, pc = corners[i - 1], corners[i], corners[(i + 1) % 4]
        v1, v2 = np.array(pa) - np.array(pb), np.array(pc) - np.array(pb)
        ang = math.degrees(math.acos(float(np.clip(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9), -1, 1))))
        if abs(ang - 90.0) > 20.0:
            raise PhotoError(f"the detected ruled block is not rectangular enough (a corner measures {ang:.0f} deg): "
                             "retake with the camera more above the sheet, or give the corners yourself")
    e = [math.dist(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    if not (0.7 < e[0] / e[2] < 1.43 and 0.7 < e[1] / e[3] < 1.43):
        raise PhotoError("opposite edges of the detected ruled block differ too much: the line ends were misdetected; "
                         "retake the photo or give the corners yourself")
    tol = 0.03 * max(w, h)
    inl = 0.0
    for fit_line, pts in ((lines4["left"], left_pts), (lines4["right"], right_pts)):
        (px, py), (dx, dy) = fit_line
        dist = np.abs((pts[:, 0] - px) * dy - (pts[:, 1] - py) * dx)
        inl += float(np.mean(dist < tol)) / 2
    if inl < 0.7:
        raise PhotoError(f"the left/right ends of the ruled lines are not straight ({inl:.0%} agree): torn or inked sheet; "
                         "retake it flat, or give the corners yourself")
    warnings = []
    if gaps:
        warnings.append(f"{gaps} ruled line(s) missing inside the block (occluded or faint)")
    if len(good) < 12:
        warnings.append(f"only {len(good)} ruled lines found: corner accuracy is reduced")
    return corners, len(good), warnings


# ---------------------------------------------------------------- the arm ----


def find_arm(img: Img, blue: Img) -> tuple[P2 | None, float | None, P2 | None, list[str]]:
    """(pen-holder hole centre, its diameter, shoulder position, warnings), analysis-scale pixels.

    The thin neck of link 2 often disconnects the holder from the rest of the arm in the mask, so nothing here relies on
    connectivity: circular holes anywhere in the blue plastic are candidates, the dark-blue servo cases are landmarks,
    the pen holder is the hole farthest from every servo and the shoulder is the servo farthest from that hole."""
    warnings: list[str] = []
    mask = cv2.morphologyEx(blue, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return None, None, None, ["no blue arm found"]
    holes = []
    for c, h in zip(contours, hier[0]):
        if h[3] < 0:
            continue
        area = cv2.contourArea(c)
        per = cv2.arcLength(c, True)
        if area < 150 or per == 0:
            continue
        circ = 4 * math.pi * area / per**2
        if circ < 0.6:
            continue
        (cx, cy), _ = cv2.minEnclosingCircle(c)
        holes.append(((cx, cy), 2 * math.sqrt(area / math.pi), circ, area))
    if not holes:
        return None, None, None, ["no circular hole found in the arm: is the pen holder in view?"]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    case = cv2.inRange(hsv, (100, 150, 60), (130, 255, 215))
    case = cv2.morphologyEx(case, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cn, _, cs, cc = cv2.connectedComponentsWithStats(case)
    servos = [cc[k] for k in range(1, cn) if cs[k, cv2.CC_STAT_AREA] > 250]
    if not servos:
        warnings.append("no servo case found: the pen holder is taken as the largest circular hole and the shoulder is unknown")
        best = max(holes, key=lambda h: h[3])
        return best[0], best[1], None, warnings
    best = max(holes, key=lambda h: min(float(np.linalg.norm(np.array(h[0]) - sp)) for sp in servos))
    ring = np.array(best[0])
    shoulder = max(servos, key=lambda sp: float(np.linalg.norm(sp - ring)))
    if len(servos) < 2:
        warnings.append("only one servo case found: the shoulder may be misplaced")
    return best[0], best[1], (float(shoulder[0]), float(shoulder[1])), warnings


# ---------------------------------------------------------------- labelling and public API ----


def label_corners(block: list[P2], base: P2 | None) -> tuple[dict[str, P2], list[str]]:
    """Name the block's corners from the arm's point of view: near = the edge closest to the base."""
    tl, tr, br, bl = block
    edges = {"top": (tl, tr), "right": (tr, br), "bottom": (br, bl), "left": (bl, tl)}
    if base is None:
        near = "bottom"
        warn = ["arm base not found: assuming the arm is at the bottom of the photo"]
    else:
        near = min(edges, key=lambda k: math.dist(((edges[k][0][0] + edges[k][1][0]) / 2, (edges[k][0][1] + edges[k][1][1]) / 2), base))
        warn = []
    order = ["top", "right", "bottom", "left"]
    k = order.index(near)
    cyc = [block[(k + i) % 4] for i in range(4)]  # corners going around, starting at the near edge's first corner
    a, b, c, d = cyc  # a-b is the near edge, c-d the far edge
    fwd = np.array([(c[0] + d[0]) / 2 - (a[0] + b[0]) / 2, (c[1] + d[1]) / 2 - (a[1] + b[1]) / 2])
    right = np.array([-fwd[1], fwd[0]])  # image y points down
    if np.dot(np.array(b) - np.array(a), right) > 0:
        near_left, near_right, far_right, far_left = a, b, c, d
    else:
        near_left, near_right, far_right, far_left = b, a, d, c
    return {"near_left": near_left, "near_right": near_right, "far_right": far_right, "far_left": far_left}, warn


def analyze(path: str | Path, debug_path: str | Path | None = None) -> PhotoAnalysis:
    img, s = _load(path)
    blue = _blue_mask(img)
    block, nlines, w1 = find_ruled_block(img, blue)
    ring, ring_d, base, w2 = find_arm(img, blue)
    corners, w3 = label_corners(block, base)
    conf = min(1.0, nlines / 14) * (1.0 if ring else 0.6) * (1.0 if base else 0.8)
    res = PhotoAnalysis(
        corners_px={k: (v[0] / s, v[1] / s) for k, v in corners.items()},
        ring_px=None if ring is None else (ring[0] / s, ring[1] / s),
        ring_diameter_px=None if ring_d is None else ring_d / s,
        base_px=None if base is None else (base[0] / s, base[1] / s),
        confidence=round(conf, 2), warnings=[*w1, *w2, *w3], lines_found=nlines,
        image_wh=(round(img.shape[1] / s), round(img.shape[0] / s)),
    )
    if debug_path:
        write_overlay(path, res, debug_path)
    return res


RING_HOLE_MM = 11.4  # diameter of the pen holder's hole (CAD: SUPORTE_LAPIS.stl)


def tip_from_ring(
    ring_px: P2, ring_diameter_px: float, image_wh: tuple[int, int], corners_px: dict[str, P2], paper_w: float, paper_h: float,
    ring_hole_mm: float = RING_HOLE_MM,
) -> tuple[P2, float, list[str]]:
    """Pen tip on the PAPER (mm, paper frame) from the holder's hole seen from above.

    The hole sits about 4-5 cm above the paper, so it looks bigger and farther from the image centre than the tip it
    carries. The hole's known diameter gives the magnification there; the paper's own scale (from the corners) gives it
    at the paper; their ratio k is how much to pull the hole's pixel toward the camera's centre, where a vertical line
    (the pen) meets the paper. Returns (tip in mm, k, warnings)."""
    from .calibration import apply_homography, homography  # local: calibration is pure Python, photocv needs cv2

    src = [corners_px[k] for k in ("near_left", "near_right", "far_right", "far_left")]
    h_mm = homography(src, [(0.0, 0.0), (paper_w, 0.0), (paper_w, paper_h), (0.0, paper_h)])
    e = 1.0
    a = apply_homography(h_mm, (ring_px[0] + e, ring_px[1]))
    b = apply_homography(h_mm, (ring_px[0], ring_px[1] + e))
    c0 = apply_homography(h_mm, ring_px)
    mm_per_px = math.sqrt(abs((a[0] - c0[0]) * (b[1] - c0[1]) - (a[1] - c0[1]) * (b[0] - c0[0])))  # local |det J|
    k = (ring_diameter_px / ring_hole_mm) * mm_per_px  # (px/mm at the hole) / (px/mm at the paper)
    warnings = []
    if not 0.95 <= k <= 1.8:
        warnings.append(f"implausible perspective factor k={k:.2f} (expected 1.0-1.5): the paper size or the hole may be off")
        k = min(max(k, 1.0), 1.8)
    cx, cy = image_wh[0] / 2, image_wh[1] / 2
    tip_px = (cx + (ring_px[0] - cx) / k, cy + (ring_px[1] - cy) / k)
    return apply_homography(h_mm, tip_px), k, warnings


def write_overlay(path: str | Path, res: PhotoAnalysis, out: str | Path) -> None:
    img = cv2.imread(str(path))
    assert img is not None
    th = max(2, img.shape[1] // 400)
    pts = [res.corners_px[k] for k in ("near_left", "near_right", "far_right", "far_left")]
    cv2.polylines(img, [np.array(pts, np.int32)], True, (0, 200, 0), th)
    for name, p in res.corners_px.items():
        cv2.circle(img, (int(p[0]), int(p[1])), th * 4, (0, 0, 255), -1)
        cv2.putText(img, name, (int(p[0]) + 10, int(p[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, th / 1.5, (0, 0, 255), th)
    if res.ring_px:
        cv2.circle(img, (int(res.ring_px[0]), int(res.ring_px[1])), int((res.ring_diameter_px or 20) / 2), (0, 140, 255), th)
        cv2.putText(img, "ring", (int(res.ring_px[0]) + 15, int(res.ring_px[1])), cv2.FONT_HERSHEY_SIMPLEX, th / 1.5, (0, 140, 255), th)
    if res.base_px:
        cv2.circle(img, (int(res.base_px[0]), int(res.base_px[1])), th * 5, (255, 0, 255), th)
        cv2.putText(img, "base", (int(res.base_px[0]) + 15, int(res.base_px[1])), cv2.FONT_HERSHEY_SIMPLEX, th / 1.5, (255, 0, 255), th)
    small = cv2.resize(img, None, fx=min(1.0, 1400 / max(img.shape[:2])), fy=min(1.0, 1400 / max(img.shape[:2])))
    cv2.imwrite(str(out), small)
