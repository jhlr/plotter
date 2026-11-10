---
name: calibrate-angles
description: Calibrate the arm's servo angles (stage 1 of 2). Use when a new arm/kit is assembled, servos or pins were changed, or drawings come out the wrong size or place. Ends with the arm stretched to the middle of the paper so the human can see it is calibrated; the next stage is movement calibration (the rectangle, `penarm-inkcal`).
---

# Angle calibration (stage 1)

**Fast path for a new kit (minutes, no photos):** the defaults in `config.py` already describe the reference kit. Run `uv run penarm-assemble --port P`, mount both horns with the arm straight (links aligned, along the board's centre line), tighten, then go to the rectangle. Use the long procedure below only when the arm was not built that way or the rectangle shows a clear rotation/scale error.

Goal: write `server/calibration.json` `params` (`base_x`, `base_y`, `offset1/2`, `sign1/2`, `l1`, `l2`, `page_w`, `page_h`) so that commanded servo angles match the real arm. Pen removed for all of it. No ML fit: two photographed poses per arm, by hand.

Do not draw anything until the last step. Ask the human for every photo and every physical change; they cannot be inferred.

## 1. Hardware sanity (never skip: bad power cost hours)

1. Port: `ls /dev/cu.usb*`. Every board has its own port name. Use it explicitly: an empty port string silently starts the simulator (check `canvas_info` shows `"simulated": false`).
2. Firmware: if the board does not answer (`no reply to 'V ...'`), flash `make flash PORT=...` and wait for "verified".
3. Power: servos must be on an external 5 V supply with common GND, never the USB 5 V. Limp servos give meaningless poses.
4. Pins (`firmware/src/config.h`, Uno): proximal servo (shoulder, servo 1) on **D9**, distal (elbow, servo 2) on **D8**.

## 2. Isolated servo test (before any pose photo)

Sweep one servo with the other held, 4 s per step, and ask the human which link moved:
`p.arm.goto_servos(90,90)`, then `(120,90) (60,90) (90,90)` (servo 1 only), then `(90,60) (90,120) (90,90)` (servo 2 only). Servo 1 must move only link 1, servo 2 only link 2, both firmly. Otherwise fix wires/horns first.

## 3. Two poses, two photos

Pose A = servos (90, 90), pose B = (120, 60). After each move, ask for a photo of the whole board from the same spot, nobody touching the arm. The board is 230 x 330 mm: use it as the scale and name its corners by what they are (BL = nearest the servos, on the left), not by where they land in the photo. Any photo rotation is fine; convert to board frame (x right, y up from BL).

From each photo read, in pixels: shoulder screw, elbow screw, pen-hole centre (or the pen tip).

**Parallax:** the links sit above the board, so they look larger than the board plane. Scale factor `f = (link-1 pixel length / l1) / (board pixels per mm)` (typically 1.1-1.2); divide each link point's offset from the image centre by `f` before measuring angles. Check: the corrected link-1 length must come out at `l1` (108.1 mm, from the CAD).

Per pose compute: `t1` = link-1 angle from board +x; `t2` = link-2 angle minus `t1`. Base = shoulder position in board mm (average of the poses).

## 4. Fit and write

`uv run python .claude/skills/calibrate-angles/scripts/fit_poses.py --servo1 90 120 --joint1 <t1A> <t1B> --servo2 90 60 --joint2 <t2A> <t2B>` prints sign and offset per servo. Expect |sign| near 1 (0.9-1.0); a very different value means a servo did not really move: go back to step 2.

**The elbow always bends to the board's left** (joint 2 < 0), away from the Arduino on the right; the code has no option for the other side. Servo 2 covers only 180 deg, so `joint2 = sign2 * (servo2 - offset2)` must reach about -90 deg (offset2 near 139). Mount the distal horn for that (servo 2 at 90 deg, link 2 about 45 deg to the left of link 1). If `Plotter()` warns that the canvas is tiny, or joint 2 reads positive in your poses, the horn is mounted for the right side: remount it and redo steps 3-4.

Keep `l1`/`l2` from the CAD unless a ruler disagrees. Write the params into `server/calibration.json`, **delete the `mesh` key** (it belongs to the old calibration), keep a backup of the old file outside the repo.

Verify in code: `servos_to_joints` + `fk` at both poses must reproduce the measured joints, and `Plotter().canvas_info()` must show a sensible canvas. Then `make check`.

## 4b. Offsets again without photos (horn remounted, everything else unchanged)

The gains, base and link lengths belong to the arm; only the horn mounting moves the two offsets. Re-find them by eye: `scripts/straight_pose.py move S1 S2 --port P` sends the arm to a guess of the straight pose (links aligned, along the board's vertical centre line), the human says nudge +/-1 deg, repeat; when it looks straight, `straight_pose.py write S1 S2` saves `offset2 = S2`, `offset1 = S1 - 90 / sign1` and drops the mesh. Current arm: offset1 4.5, offset2 93.2, i.e. straight at servos (90.5, 93.2). Check the result with step 5.

## 5. Proof for the human: stretch the arm to the middle of the paper

With the pen still removed, move the arm so its tip sits at the centre of the canvas:

```python
from penarm import Plotter
from penarm.kinematics import page_to_servos
p = Plotter("<port>")
x, y = p.canvas.to_page(p.canvas.w / 2, p.canvas.h / 2)
p.arm.goto_servos(*page_to_servos(p.arm.cfg, x, y))
```

The human looks at the sheet: the tip (pen hole) must sit over the middle of the paper's drawable area. If it does, the angles are calibrated. If not, redo step 3 with a third pose and compare. Report the result honestly; the arm answering `OK` proves nothing, only the human seeing it does.

## 6. Next: movement calibration

Only after step 5 is confirmed: put the pen in, a clean sheet under it, and run the rectangle calibration (README section 6: `penarm-inkcal draw`, photo, `measure ... --overlay`, open the overlay, `--update-mesh`, 2-3 rounds on fresh sheets).
