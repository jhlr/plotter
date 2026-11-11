---
name: calibrate-arm
description: Calibrate a pen-plotter arm in two steps: assemble at the assembly pose, then draw the canvas rectangle, photograph it once and fit the servo gains and horn offsets from where the four edges landed. Use when a new kit is assembled, the horns were remounted, or drawings come out the wrong size or position.
---

# Calibrate the arm (about 10 minutes)

The elbow always bends to the board's left. Servos need an external 5 V with the ground shared with the Arduino (limp servos make every number meaningless; from USB alone the board can lock up). Port: macOS `ls /dev/cu.usb*`; one process at a time.

1. **Assemble** (human mounts, you drive): `cd server && penarm-assemble --port P`. Both horns go on with the arm straight (link 1 along the board's centre line away from the servos, link 2 aligned). Tighten. If the elbow points right, remount.
2. **Draw** (pen in, clean sheet, ask first): `penarm-calibrate draw --port P`. Never say "drawn" until the human confirms the arm moved.
3. **Photo** (human): the whole board from above, four corners in view, arm out of the way. You read the board's four corners in pixels (crop 2x2 and read by hand), named by what they are: BL nearest the servos on the left, then BR, TR, TL.
4. **Measure and look**: `penarm-calibrate measure photo.jpg --corners "BLx,BLy BRx,BRy TRx,TRy TLx,TLy" --overlay check.png`. **Open check.png.** `--mask x0,y0,x1,y1` hides the pen or arm; `--ink green|blue|red|brown|dark` names a colour auto misses.
5. **Fit**: same command with `--save` (writes `~/.penarm/calibration.json`, previous copy `calibration.json.bak-prev`). "fit no arm" means a bad read or a loose horn: re-photograph first.
6. **Confirm**: new clean sheet, draw again, measure again: the drawn edges should sit on the plan within a few mm. One or two rounds.

If `canvas_info` errors with `Unreachable` after assembly, the horn is on the wrong side or too far off: remount it (README section 5). Canvas edges (`canvas_*_mm`) are set in `calibration.json` by hand; the code only checks they are reachable.
