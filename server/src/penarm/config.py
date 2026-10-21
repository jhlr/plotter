"""Single source of truth for arm geometry and calibration. Measure and edit here."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ArmConfig:
    # Link lengths, joint axis to joint axis / pen tip (mm). PLACEHOLDERS: measure the real arm.
    l1: float = 100.0
    l2: float = 130.0
    # Shoulder axis position in page coordinates (mm). Page origin = bottom-left corner of the
    # sheet, x to the right, y away from the arm base. Base sits below the sheet's bottom edge.
    base_x: float = 105.0
    base_y: float = -20.0
    # Page size (mm), A5-ish notebook by default.
    page_w: float = 148.0
    page_h: float = 210.0
    # Servo angle (deg) <-> joint angle (deg): joint = sign * (servo - offset).
    # Joint 1 is measured from +x axis (page), joint 2 is relative to link 1.
    sign1: float = 1.0
    offset1: float = 90.0
    sign2: float = 1.0
    offset2: float = 90.0
    elbow_up: bool = True  # which of the two IK solutions to use
    seg_mm: float = 1.0  # Cartesian interpolation step for straight lines
    speed_dps: float = 40.0  # servo speed while drawing (deg/s)


DEFAULT = ArmConfig()


@dataclass(frozen=True)
class VisionConfig:
    """Overhead camera: 4 ArUco markers stuck on the page define the pixel -> mm homography."""

    aruco_dict: str = "DICT_4X4_50"
    marker_size_mm: float = 20.0
    # marker id -> marker CENTER in page mm. Stick them where the printed sheet says; keep in sync.
    marker_centers: tuple[tuple[int, float, float], ...] = (
        (0, 15.0, 15.0),
        (1, 133.0, 15.0),
        (2, 133.0, 195.0),
        (3, 15.0, 195.0),
    )
    # Pencil tag (green eraser end by default), OpenCV HSV ranges (H 0-179).
    hsv_lo: tuple[int, int, int] = (40, 80, 50)
    hsv_hi: tuple[int, int, int] = (85, 255, 255)
    min_blob_px: int = 30
    frames: int = 5  # frames fused (median) per fix


VISION = VisionConfig()
