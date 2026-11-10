"""Assembly pose: send the servos to the angles where the arm must be STRAIGHT (joint 1 = 90 deg, link 1 along the board's
centre line; joint 2 = 0, links aligned), so each horn is mounted at the position the default calibration assumes.

    uv run penarm-assemble --port /dev/cu.usbserial-XXXX

Mount the horns with the arm straight, tighten, and nothing else needs calibrating: go straight to the rectangle."""
import argparse
import time

from .calibration import CalibrationStore
from .config import DEFAULT
from .kinematics import joints_to_servos
from .plotter import Plotter


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True)
    port = ap.parse_args().port
    s1, s2 = joints_to_servos(CalibrationStore().apply(DEFAULT), 90.0, 0.0)
    with Plotter(port) as p:
        p.arm.goto_servos(s1, s2)
        time.sleep(5)
        print(f"servos held at ({s1:.1f}, {s2:.1f}): mount link 1 along the board's centre line (away from the servos) and "
              "link 2 aligned with it, tighten both horns. The servos stay powered; Ctrl+C or unplug when done.")
        time.sleep(1)
