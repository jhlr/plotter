"""Fit one servo's mapping `joint = sign * (servo - offset)` from two photographed poses.

    uv run python fit_poses.py --servo1 90 120 --joint1 93.8 123.4 --servo2 90 60 --joint2 31.5 4.1

--servoN: the two commanded servo angles. --jointN: the joint angle read from the photo at each pose
(joint 1 = link 1 angle from +x of the board; joint 2 = link 2 angle minus link 1 angle, both counter-clockwise).
Prints sign, offset and whether the two poses agree on the offset (they do by construction; use a third pose to check).
"""
import argparse


def fit(servo: tuple[float, float], joint: tuple[float, float]) -> tuple[float, float]:
    sign = (joint[1] - joint[0]) / (servo[1] - servo[0])
    offset = servo[0] - joint[0] / sign
    return sign, offset


def main() -> None:
    ap = argparse.ArgumentParser()
    for n in (1, 2):
        ap.add_argument(f"--servo{n}", type=float, nargs=2, required=True)
        ap.add_argument(f"--joint{n}", type=float, nargs=2, required=True)
    a = ap.parse_args()
    for n in (1, 2):
        sign, offset = fit(tuple(getattr(a, f"servo{n}")), tuple(getattr(a, f"joint{n}")))
        print(f"sign{n} = {sign:.3f}   offset{n} = {offset:.1f}")
    print("the elbow always bends left: joint 2 must read negative in drawing poses; if positive, remount the horn")


if __name__ == "__main__":
    main()
