"""Camera -> pencil position in page mm. Only numbers leave this module, never frames."""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from .config import VISION, ArmConfig, VisionConfig
from .errors import VisionError

Frame = NDArray[np.uint8]


class FrameSource(Protocol):
    def read(self) -> Frame: ...


class Camera:
    """cv2.VideoCapture wrapper: device index ("0") or a stream/file path."""

    def __init__(self, source: str, warmup: int = 5) -> None:
        self.cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
        if not self.cap.isOpened():
            raise RuntimeError(f"cannot open camera {source!r}")
        for _ in range(warmup):  # let auto-exposure settle
            self.cap.read()

    def read(self) -> Frame:
        ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError("camera read failed")
        return np.asarray(frame, dtype=np.uint8)


@dataclass(frozen=True)
class Fix:
    x_mm: float
    y_mm: float
    seen: int  # frames (of `frames`) where the pencil tag was found
    frames: int
    spread_mm: float  # max deviation of per-frame detections from the median
    in_page: bool


class PencilLocator:
    def __init__(self, arm_cfg: ArmConfig, source: FrameSource, cfg: VisionConfig = VISION) -> None:
        self.arm_cfg, self.cfg, self.source = arm_cfg, cfg, source
        self._detector = cv2.aruco.ArucoDetector(
            cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, cfg.aruco_dict)),
            cv2.aruco.DetectorParameters(),
        )
        self._world = {i: (x, y) for i, x, y in cfg.marker_centers}
        self._h: NDArray[np.float64] | None = None  # pixel -> page mm

    def calibrate(self, frame: Frame) -> bool:
        """Refresh the homography from the markers in `frame`. Needs all markers visible."""
        corners, ids, _ = self._detector.detectMarkers(frame)
        if ids is None:
            return False
        px, mm = [], []
        for c, i in zip(corners, ids.flatten()):
            if int(i) in self._world:
                px.append(c.reshape(4, 2).mean(axis=0))
                mm.append(self._world[int(i)])
        if len(px) < 4:
            return False
        h, _ = cv2.findHomography(np.array(px, np.float32), np.array(mm, np.float32))
        if h is None:
            return False
        self._h = np.asarray(h, dtype=np.float64)
        return True

    def _tag_px(self, frame: Frame) -> tuple[float, float] | None:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(self.cfg.hsv_lo), np.array(self.cfg.hsv_hi))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        best = max(contours, key=cv2.contourArea)
        if cv2.contourArea(best) < self.cfg.min_blob_px:
            return None
        m = cv2.moments(best)
        return m["m10"] / m["m00"], m["m01"] / m["m00"]

    def locate(self) -> Fix:
        pts: list[tuple[float, float]] = []
        for _ in range(self.cfg.frames):
            frame = self.source.read()
            self.calibrate(frame)  # re-calibrates every frame, so a nudged camera self-corrects
            if self._h is None:
                raise VisionError("page markers not seen yet: check camera view and lighting")
            tag = self._tag_px(frame)
            if tag is not None:
                mm = cv2.perspectiveTransform(np.array([[tag]], np.float32), self._h)[0, 0]
                pts.append((float(mm[0]), float(mm[1])))
        if not pts:
            raise VisionError("pencil tag not found in any frame")
        arr = np.array(pts)
        med = np.median(arr, axis=0)
        spread = float(np.max(np.linalg.norm(arr - med, axis=1)))
        x, y = float(med[0]), float(med[1])
        c = self.arm_cfg
        return Fix(round(x, 1), round(y, 1), len(pts), self.cfg.frames, round(spread, 2),
                   0.0 <= x <= c.page_w and 0.0 <= y <= c.page_h)


def write_marker_sheet(out_dir: Path, cfg: VisionConfig = VISION, px: int = 600) -> list[Path]:
    """Writes marker_<id>.png (with white quiet zone). Print each at cfg.marker_size_mm."""
    out_dir.mkdir(parents=True, exist_ok=True)
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, cfg.aruco_dict))
    paths = []
    for i, x, y in cfg.marker_centers:
        img = cv2.aruco.generateImageMarker(d, i, px)
        img = cv2.copyMakeBorder(img, px // 6, px // 6, px // 6, px // 6, cv2.BORDER_CONSTANT, value=255)
        p = out_dir / f"marker_{i}.png"
        cv2.imwrite(str(p), img)
        paths.append(p)
        print(f"{p}: print at {cfg.marker_size_mm:.0f} mm (black square), center at page ({x}, {y}) mm")
    return paths


def markers_main() -> None:
    write_marker_sheet(Path("markers"))
