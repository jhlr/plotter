"""Single source of truth for arm geometry and calibration. Measure and edit here."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ArmConfig:
    # THE REFERENCE KIT, measured 2026-11-10 from overhead photos at servos 90/90 and 120/60 (+-3 deg, +-5 mm).
    # Build every new kit at the ASSEMBLY POSE (`penarm-assemble`) and these numbers hold without any photo.
    # Link lengths (mm): l1 shoulder axis -> elbow axis (CAD 108.1); l2 elbow axis -> pen hole (the ring, ~106 on the print).
    l1: float = 108.1
    l2: float = 106.0
    # Shoulder axis in page coordinates (mm). Page = the board: origin bottom-left corner, x right, y away from the
    # servos. The shoulder sits on the board's bottom edge, centred.
    base_x: float = 116.0
    base_y: float = 8.0
    page_w: float = 230.0
    page_h: float = 330.0
    # joint = sign * (servo - offset). Joint 1 = link 1 angle from +x; joint 2 = link 2 relative to link 1, always
    # negative in use: the elbow always bends to the board's left, away from the electronics.
    # ASSEMBLY POSE: joint 1 = 90 deg (link 1 along the board's centre line, away from the servos), joint 2 = 0
    # (links aligned) is reached at servos (90.5, 135.0). Mount both horns with the arm straight there.
    sign1: float = 1.047
    offset1: float = 4.5
    sign2: float = 0.877
    offset2: float = 135.0
    # Usable servo range (deg): the full travel (chosen 2026-10-27 for a larger canvas; an SG90 is less accurate near its end stops).
    servo_min: float = 0.0
    servo_max: float = 180.0
    # The canvas: the drawing rectangle, as four edge positions in page mm (the same board frame as base_x/base_y).
    # You place the edges; the code only checks that the whole rectangle is reachable (it does not search for a size).
    canvas_left_mm: float = 24.0  # the leftmost reachable with the top at 201 (arm fully extended there); more needs the base moved left
    canvas_bottom_mm: float = 153.0  # our sheet's bottom edge is at y = 111; the drawing starts ~40 mm above it
    canvas_right_mm: float = 199.0  # our sheet ends ~18 mm short of the board's right edge (230)
    canvas_top_mm: float = 201.0
    seg_mm: float = 1.0  # Cartesian interpolation step for straight lines
    feed_mm_s: float = 100.0  # pen-tip speed while drawing (mm/s); faster is smoother (slow servos stick in their dead band)
    accel_mm_s2: float = 600.0  # how fast the pen tip may speed up or brake (mm/s^2)
    corner_mm_s: float = 15.0  # tip speed at a stroke's ends and at sharp corners (mm/s)
    speed_dps: float = 180.0  # servo speed limit (deg/s)
    idle_release_s: float = 120.0  # board releases the servos after this long without commands; 0 = never


DEFAULT = ArmConfig()

