"""Photo-free offsets: find the servo angles at which the arm is straight, and derive offset1/offset2 from them.

Use it after a horn was remounted or the arm was reassembled, when sign1/sign2, base and l1/l2 are still valid.
"Straight" = reference pose: link 1 along the board's vertical centre line (joint 1 = 90 deg) and link 2 aligned
with link 1 (joint 2 = 0 deg). Then, with joint = sign * (servo - offset):
    offset2 = servo2,   offset1 = servo1 - 90 / sign1

    uv run python straight_pose.py move  90.5 93.2 --port /dev/cu.usbserial-XXXX   # go there, look, nudge by +-1 deg
    uv run python straight_pose.py write 91.5 93.2                                  # the arm LOOKS straight: save
`write` stores offset1/offset2 in calibration.json and drops the mesh (it belongs to the old offsets).
The current arm: offset1 4.5, offset2 93.2 = straight at servos (90.5, 93.2).
"""
import argparse
import time

from penarm import Plotter
from penarm.calibration import CalibrationStore

JOINT1_STRAIGHT = 90.0  # link 1 along the board's vertical centre line


def offsets(servo1: float, servo2: float, sign1: float) -> tuple[float, float]:
    return servo1 - JOINT1_STRAIGHT / sign1, servo2


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("move", "write"))
    ap.add_argument("servo1", type=float)
    ap.add_argument("servo2", type=float)
    ap.add_argument("--port", default="")
    a = ap.parse_args()
    store = CalibrationStore()
    if a.mode == "move":
        with Plotter(a.port or None) as p:
            p.arm.goto_servos(a.servo1, a.servo2)
            time.sleep(5)
            print(f"servos at {p.get_state()['servo_deg']}: is the arm straight, along the board's centre line?")
        return
    sign1 = store.params.get("sign1", 1.0)
    store.params["offset1"], store.params["offset2"] = (round(v, 1) for v in offsets(a.servo1, a.servo2, sign1))
    store.mesh = None
    store.save()
    print(f"saved offset1={store.params['offset1']} offset2={store.params['offset2']} to {store.path} (mesh dropped)")


if __name__ == "__main__":
    main()
