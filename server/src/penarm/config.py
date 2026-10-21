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
