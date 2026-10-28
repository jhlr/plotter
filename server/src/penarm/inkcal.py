"""Rectangle calibration from a photo: draw a reference rectangle, photograph the whole clipboard, measure how far the
ink is from the plan and fold that into the correction mesh (see mesh.py). Needs the `vision` extra (numpy, OpenCV).

    uv run penarm-inkcal draw --port /dev/cu.usbserial-XXXX
    uv run penarm-inkcal measure photo.jpg --corners "BLx,BLy BRx,BRy TRx,TRy TLx,TLy" [--update-mesh]

Corners are the four corners of the clipboard board in photo pixels, named by the board frame: origin = bottom-left,
the bottom edge is the one nearest the arm's servos, x to the right and y away from them (as seen from the arm base).
A photo taken from any side works as long as each corner is labelled by what it is, not by where it lands in the photo."""
import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from .arm import Arm
from .calibration import CalibrationStore, homography
from .config import DEFAULT, ArmConfig
from .link import SerialLink, SimLink
from .mesh import CorrectionMesh
from .shapes import rect_points

Pts = NDArray[np.float64]
Rect = tuple[float, float, float, float]  # x0, y0, x1, y1 in page mm
EDGE_STEP_MM = 6.0
LAB_L_MAX = 205
INKS = ("green", "blue", "red", "dark")  # `dark` = black or very dark blue ballpoint: judged against the photo's own paper brightness
DARK_DROP = 70  # a `dark` ink pixel is this much darker (Lab L) than the median pixel of the photo


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
    if ink == "green":
        return (a < 115) & (light < LAB_L_MAX)  # green ink drops a below ~112
    if ink == "red":
        return (a > 140) & (light < LAB_L_MAX)
    if ink == "blue":
        return (b < 112) & (light < LAB_L_MAX)
    if ink == "dark":
        return light < float(np.median(light)) - DARK_DROP
    raise ValueError(f"unknown ink {ink!r}: choose one of {INKS}")


def ink_pixels(photo: NDArray[np.uint8], masked_out: list[tuple[int, int, int, int]], ink: str = "green") -> NDArray[np.int64]:
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


def _residual(ink: Pts, axis: int, level: float, ts: Pts, band: float = 12.0, strip: float = 3.0) -> tuple[Pts, int]:
    """Ink position minus the planned edge position, along one edge. axis 1: horizontal edge (error in y)."""
    along = 0 if axis == 1 else 1
    out = np.full(len(ts), np.nan)
    for j, t in enumerate(ts):
        sel = ink[(np.abs(ink[:, along] - t) < strip) & (np.abs(ink[:, axis] - level) < band)]
        if len(sel):
            out[j] = np.median(sel[:, axis]) - level
    ok = ~np.isnan(out)
    out = np.interp(ts, ts[ok], out[ok]) if ok.any() else np.zeros(len(ts))  # gaps: interpolate; ends: hold
    return np.convolve(np.pad(out, 1, mode="edge"), np.ones(3) / 3, mode="valid"), int(ok.sum())


def measure(ink: Pts, rect: Rect, old: CorrectionMesh | None, gain: float = 0.8) -> tuple[CorrectionMesh, dict[str, object]]:
    """New mesh = what the old mesh already predicted + gain * the error that is left. Also returns the statistics."""
    x0, y0, x1, y1 = rect
    tx, ty = np.arange(x0, x1 + 0.1, EDGE_STEP_MM), np.arange(y0, y1 + 0.1, EDGE_STEP_MM)
    rb, nb = _residual(ink, 1, y0, tx)
    rt, nt = _residual(ink, 1, y1, tx)
    rl, nl = _residual(ink, 0, x0, ty)
    rr, nr = _residual(ink, 0, x1, ty)

    def fold(ts: Pts, r: Pts, at: "list[tuple[float, float]]", comp: int) -> tuple[tuple[float, ...], tuple[float, ...]]:
        prior = [old.error_at(*q)[comp] if old else 0.0 for q in at]
        return tuple(float(v) for v in ts), tuple(float(np.clip(p + gain * v, -15, 15)) for p, v in zip(prior, r))

    mesh = CorrectionMesh(
        x0, y0, x1, y1,
        fold(tx, rb, [(t, y0) for t in tx], 1), fold(tx, rt, [(t, y1) for t in tx], 1),
        fold(ty, rl, [(x0, t) for t in ty], 0), fold(ty, rr, [(x1, t) for t in ty], 0),
    )
    d = np.concatenate([np.abs(r) for r in (rb, rt, rl, rr)])
    stats = {"edge_error_rms_mm": float(np.sqrt((d**2).mean())), "edge_error_max_mm": float(d.max()),
             "positions_measured": [nb, nt, nl, nr], "of": [len(tx), len(tx), len(ty), len(ty)]}
    return mesh, stats


def _planned_rect(cfg: ArmConfig, mesh: CorrectionMesh | None) -> Rect:
    c = Arm(cfg, SimLink(), mesh=mesh).canvas
    return c.x0, c.y0, c.x0 + c.w, c.y0 + c.h


def _parse_corners(text: str) -> list[tuple[float, float]]:
    pts = [tuple(float(v) for v in pair.split(",")) for pair in text.split()]
    if len(pts) != 4 or any(len(p) != 2 for p in pts):
        raise SystemExit('--corners needs four "x,y" pairs: bottom-left bottom-right top-right top-left (photo pixels)')
    return [(p[0], p[1]) for p in pts]


def draw(port: str, feed: float, speed: float) -> None:
    store = CalibrationStore()
    cfg = replace(store.apply(DEFAULT), feed_mm_s=feed, speed_dps=speed)
    link = SerialLink(port)
    try:
        arm = Arm(cfg, link, mesh=store.mesh)
        c = arm.canvas
        print(f"canvas {c.w:.0f} x {c.h:.0f} mm at page ({c.x0:.0f},{c.y0:.0f}); mesh {'on' if arm.mesh else 'off'}")
        arm.draw_strokes([[(0.0, 0.0)]])  # get to the start first (the pen has no lift: this travel marks the paper)
        arm.draw_strokes([rect_points(0.0, 0.0, c.w, c.h)])
        arm.draw_strokes([[(c.w / 2, 0.0)]])  # park at the bottom middle: the arm then hides only a sliver of the drawing
        print("done: photograph the whole clipboard now (four corners in view, arm out of the way)")
    finally:
        link.close()


def run(photo_path: str, corners: str, masks: list[str], update: bool, gain: float, overlay: str | None, ink_color: str = "green") -> None:
    store = CalibrationStore()
    cfg = store.apply(DEFAULT)
    photo = cv2.imread(photo_path)
    if photo is None:
        raise SystemExit(f"cannot read {photo_path}")
    boxes = [tuple(int(v) for v in m.split(",")) for m in masks]
    px = ink_pixels(photo, boxes, ink_color)  # type: ignore[arg-type]
    if len(px) < 500:
        raise SystemExit(f"only {len(px)} ink pixels found: is the ink really {ink_color} (see --ink) and the photo sharp? mask the pen with --mask")
    ink = to_board_mm(px, _parse_corners(corners), cfg.page_w, cfg.page_h)
    rect = _planned_rect(cfg, store.mesh)
    mesh, stats = measure(ink, rect, store.mesh, gain)
    print(json.dumps({"rect_mm": rect, **stats}, indent=1))
    if overlay:
        _write_overlay(overlay, ink, rect)
        print("overlay:", overlay, "(ink green, plan red): look at it before trusting the numbers")
    if update:
        store.mesh = mesh
        store.save()
        print("mesh updated in", store.path)


def _write_overlay(path: str, ink: Pts, rect: Rect) -> None:
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
    cv2.imwrite(path, img)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="penarm-inkcal", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw", help="draw the reference rectangle (with the current mesh) and park the arm")
    d.add_argument("--port", required=True)
    d.add_argument("--feed", type=float, default=30.0, help="pen speed mm/s (default 30: slow is more accurate)")
    d.add_argument("--speed", type=float, default=60.0, help="servo speed cap deg/s")
    m = sub.add_parser("measure", help="measure a photo of the drawn rectangle")
    m.add_argument("photo")
    m.add_argument("--corners", required=True, help='"x,y x,y x,y x,y": board bottom-left, bottom-right, top-right, top-left')
    m.add_argument("--mask", action="append", default=[], help="x0,y0,x1,y1 (px) box to ignore, e.g. the pen barrel (repeatable)")
    m.add_argument("--ink", choices=INKS, default="green", help="colour of the pen that drew the rectangle (ballpoint: blue, or dark for black)")
    m.add_argument("--update-mesh", action="store_true", help="fold the measured error into calibration.json")
    m.add_argument("--gain", type=float, default=0.8)
    m.add_argument("--overlay", help="write a PNG of the ink against the plan")
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])
    if a.cmd == "draw":
        draw(a.port, a.feed, a.speed)
    else:
        run(a.photo, a.corners, a.mask, a.update_mesh, a.gain, a.overlay, a.ink)


if __name__ == "__main__":
    main()
