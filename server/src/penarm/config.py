"""Single source of truth for arm geometry and calibration. Measure and edit here."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ArmConfig:
    # Link lengths, joint axis to joint axis / pen axis (mm), from the CAD in pecas_impressao/*.stl:
    # shoulder x=20.7 -> elbow x=128.8 -> pencil hole x=243.0 (all on y=8). A ruler gave 105 / 115 on the printed arm.
    l1: float = 108.1
    l2: float = 114.2
    # Shoulder axis position in page coordinates (mm). Page origin = bottom-left corner of the
    # sheet, x to the right, y away from the arm base. Base sits below the sheet's bottom edge.
    # Base axis ~1 cm below the sheet, centered (measured roughly). A commanded 60 mm square came out ~50 mm:
    # pen friction makes the joints lag (the thin end of link 2 bends), so drawings run small and wobbly.
    # Re-measured from an overhead photo at servos 90/90 (rough, +-5 mm): ~11 cm from the sheet's left edge,
    # ~2.7 cm below its bottom edge.
    base_x: float = 110.0
    base_y: float = -27.0
    # Page size (mm): 200 x 275 notebook sheet.
    page_w: float = 200.0
    page_h: float = 275.0
    # Servo angle (deg) <-> joint angle (deg): joint = sign * (servo - offset).
    # Joint 1 is measured from +x axis (page), joint 2 is relative to link 1.
    # Signs: both servos turn the arm counter-clockwise (seen from above) as the angle grows (tested).
    # Offsets from a second overhead photo at 90/90: link 1 at 100.4 deg, link 2 at 87.3 deg (joint 2 = -13.1 deg).
    sign1: float = 1.0
    offset1: float = -10.4
    sign2: float = 1.0
    offset2: float = 103.1
    # Usable servo range (deg): an SG90 driven near its end stops (500/2400 us) is inaccurate, so keep a margin.
    servo_min: float = 10.0
    servo_max: float = 170.0
    elbow_up: bool = True  # which of the two IK solutions to use
    seg_mm: float = 1.0  # Cartesian interpolation step for straight lines
    speed_dps: float = 40.0  # servo speed while drawing (deg/s)
    idle_release_s: float = 120.0  # board releases the servos after this long without commands; 0 = never


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
