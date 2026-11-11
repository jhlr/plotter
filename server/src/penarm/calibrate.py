"""Calibration from ONE photo of a drawn rectangle.

    penarm-calibrate draw --port /dev/cu.usbserial-XXXX            # draws the canvas rectangle on a clean sheet
    # photograph the whole board from above (four corners in view, arm out of the way), read the 4 board corners in pixels
    penarm-calibrate measure photo.jpg --corners "BLx,BLy BRx,BRy TRx,TRy TLx,TLy" --overlay check.png   # look at it
    penarm-calibrate measure photo.jpg --corners "..." --save       # fits and writes calibration.json

Why this works: the arm commanded to the rectangle really draws where its true servo gains and horn offsets put it. The fit
moves four numbers (gain and offset of each servo) until the outline the arm would draw lands on the ink in the photo; the overlay
shows the plan (red), the ink (green) and the fitted outline (blue). Assemble at the assembly pose first (`penarm-assemble`) so
the starting guess is already close."""
import argparse
import shutil
from dataclasses import replace

import cv2
import numpy as np

from .calibration import CalibrationStore
from .canvas import safe_canvas
from .config import DEFAULT, ArmConfig
from .kinematics import fk, page_to_servos
from .photo import Rect, _parse_corners, _write_overlay, ink_pixels, INKS, to_board_mm
from .plotter import Plotter

FIELDS = ("sign1", "sign2", "offset1", "offset2")
CAP_MM = 12.0  # a point farther than this from the outline is not part of the drawing (pen blobs, the arm, old ink)
MAX_INK = 1500
FIT_STEP_MM = 0.5  # model outline spacing: coarser than this and the nearest-point distances are too lumpy for LM to converge


def planned(cfg: ArmConfig) -> Rect:
    c = safe_canvas(cfg)
    return c.x0, c.y0, c.x0 + c.w, c.y0 + c.h


def outline(commanded: ArmConfig, true: ArmConfig, step: float = 2.0) -> np.ndarray:
    """Where the pen lands along the commanded rectangle if the arm, driven by `commanded`'s calibration, were built like `true`."""
    x0, y0, x1, y1 = planned(commanded)
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    out: list[tuple[float, float]] = []
    for (ax, ay), (bx, by) in zip(corners[:-1], corners[1:]):
        n = max(1, int(np.hypot(bx - ax, by - ay) / step))
        for i in range(n):
            s1, s2 = page_to_servos(commanded, ax + (bx - ax) * i / n, ay + (by - ay) * i / n)
            out.append(fk(true, true.sign1 * (s1 - true.offset1), true.sign2 * (s2 - true.offset2)))
    out.append(out[0])
    return np.array(out)


def _nearest(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distance from each point of a to its nearest point of b."""
    return np.asarray(np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)).min(axis=1))


def fit(cfg: ArmConfig, ink: np.ndarray) -> tuple[dict[str, float], float]:
    """Levenberg-Marquardt on (sign1, sign2, offset1, offset2) so the outline the arm would draw matches the ink: every ink
    point near the outline and every outline point near some ink (distances capped, so stray marks do not pull).
    Returns the parameters and the rms distance (mm) of the matched points."""
    if len(ink) > MAX_INK:
        ink = ink[np.random.default_rng(0).choice(len(ink), MAX_INK, replace=False)]
    x = np.array([getattr(cfg, f) for f in FIELDS])

    def residual(v: np.ndarray) -> np.ndarray:
        line = outline(cfg, replace(cfg, **dict(zip(FIELDS, v.tolist()))), FIT_STEP_MM)
        return np.concatenate([np.minimum(_nearest(ink, line), CAP_MM), np.minimum(_nearest(line, ink), CAP_MM)])

    lam, r = 1e-1, residual(x)
    for _ in range(100):
        jac = np.empty((len(r), 4))
        for k in range(4):
            d = np.zeros(4)
            d[k] = 1e-3
            jac[:, k] = (residual(x + d) - r) / 1e-3
        step = np.linalg.solve(jac.T @ jac + lam * np.eye(4), -jac.T @ r)
        r_new = residual(x + step)
        if r_new @ r_new < r @ r:
            x, r, lam = x + step, r_new, lam * 0.3
            if np.abs(step).max() < 1e-6:
                break
        else:
            lam *= 10
    matched = r[r < CAP_MM - 1e-6]
    rms = float(np.sqrt((matched**2).mean())) if len(matched) else CAP_MM
    return dict(zip(FIELDS, (round(float(v), 4) for v in x))), rms


def draw(port: str) -> None:
    with Plotter(port) as p:
        p.arm.set_config(replace(p.arm.cfg, feed_mm_s=30.0))  # slow: the edge positions are what we measure
        c = p.arm.canvas
        print(f"canvas {c.w:.0f} x {c.h:.0f} mm at board ({c.x0:.0f},{c.y0:.0f}): drawing its outline")
        p.draw_polyline([[0.0, 0.0], [c.w, 0.0], [c.w, c.h], [0.0, c.h], [0.0, 0.0], [c.w / 2, 0.0]])  # ends parked at the bottom middle
    print("done. Photograph the whole board now (four corners in view, arm out of the way).")


def measure(photo_path: str, corners: str, masks: list[str], ink_color: str, overlay: str | None, do_save: bool) -> None:
    store = CalibrationStore()
    cfg = store.apply(DEFAULT)
    photo = cv2.imread(photo_path)
    if photo is None:
        raise SystemExit(f"cannot read {photo_path}")
    boxes = [tuple(int(v) for v in m.split(",")) for m in masks]
    px = ink_pixels(photo, boxes, ink_color)  # type: ignore[arg-type,arg-type]
    if len(px) < 500:
        raise SystemExit(f"only {len(px)} ink pixels found: is the photo sharp and the line dark enough? try --ink with a colour, and --mask for the pen")
    ink = to_board_mm(px, _parse_corners(corners), cfg.page_w, cfg.page_h)
    params, rms = fit(cfg, ink)
    line = outline(cfg, replace(cfg, **params))
    if overlay:
        _write_overlay(overlay, ink, planned(cfg), line)
        print("overlay:", overlay, "(ink green, plan red, fitted outline blue): OPEN IT before trusting the numbers")
    print("fit:", ", ".join(f"{k} {getattr(cfg, k):.3f} -> {v:.3f}" for k, v in params.items()), f"| rms {rms:.1f} mm")
    if rms > 4.0:
        print("WARNING: the outline does not match the ink well (rms > 4 mm): check the overlay, the corners and the masks before saving")
    if do_save:
        if store.path.exists():
            shutil.copy(store.path, store.path.with_name(store.path.name + ".bak-prev"))
        store.params.update(params)
        store.save()
        print("saved to", store.path, "; draw again on a new sheet to confirm")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("draw", help="draw the canvas rectangle on a clean sheet").add_argument("--port", required=True)
    m = sub.add_parser("measure", help="read the drawn rectangle from a photo (and --save the fit)")
    m.add_argument("photo")
    m.add_argument("--corners", required=True, help='"BLx,BLy BRx,BRy TRx,TRy TLx,TLy": the board corners in photo pixels')
    m.add_argument("--mask", action="append", default=[], help="x0,y0,x1,y1 pixels to ignore (the pen, the arm); repeatable")
    m.add_argument("--ink", default="auto", choices=INKS)
    m.add_argument("--overlay")
    m.add_argument("--save", action="store_true")
    a = ap.parse_args()
    if a.cmd == "draw":
        draw(a.port)
    else:
        measure(a.photo, a.corners, a.mask, a.ink, a.overlay, a.save)


if __name__ == "__main__":
    main()
