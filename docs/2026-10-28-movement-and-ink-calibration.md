# Movement, on-board program, resume and ink-based calibration (2026-10-28)

## Firmware (Uno)
- Motion is a chain of timed segments: both servos interpolate together over `ms` and the next waypoint starts on the same tick (no stop per waypoint). `Q <seq> <a> <b> [ms]`; the V limit still caps each servo.
- Stored drawing in EEPROM: `PB a b n [ms]`, `PD`, `PE`, `PI`, `G [loops]` (0 = forever). The program starts at the drawing's first point. Opening the serial port resets the Uno and stops it.
- Boots with servos released; `X` also saves the resting pose (a resume needs it).
- Flash note: avrdude sometimes fails its verify step. One such flash left a firmware that answered OK but did not drive the servos; reflashing with a passing verify fixed it. Check for "verified".

## Host
- `profile.py`: speed profile (feed, acceleration, slow corners/ends). Defaults: 100 mm/s, 600 mm/s^2, 180 deg/s cap. A 30-45 mm/s feed was more accurate for long loops.
- `journal.py` + `resume_drawing` tool: an interrupted drawing resumes from the arm's real pose.
- `SerialLink`: only whole protocol lines count as replies; a garbled `Q` reply is resent; one wrong `S` is not taken for a board restart.
- `mesh.py`: residual correction measured from a drawn rectangle (edge errors, interior blended between opposite edges). `Arm` aims against it and the canvas is computed from where the arm aims. Stored in `calibration.json` under `mesh`.
- Servo range now 0-180 deg, edge margin 10 mm (`edge_margin_mm`, `edge_margin_right_mm`).

## Ink calibration (what worked)
Draw a rectangle, photograph the whole clipboard, rectify with the board corners (230x330), read the ink with a Lab green-channel mask (HSV saturation drops thin strokes), and compare with the plan.
- Offsets and gains fit to ink: offset1 -8.09, offset2 134.54, gain1 1.015, gain2 0.813 (error about 4-5 mm rms vs 11 before).
- The edge error repeats between drawings (bottom edge, two days: correlation 0.94, 1.3 mm rms difference), so a mesh correction is worth keeping and can be iterated: new mesh = old mesh + leftover error.
- Did not generalise (leave-one-drawing-out): per-servo angle curves, direction-dependent lag, link lengths/base, a smooth residual field from separate drawings, ink dots at fixed poses (ambiguous to match).
- The first mesh extended a reach-limit saturation (x=215) inward; measure on the rectangle that will be used.
- Packaged as `penarm-inkcal` (`draw` / `measure`, `penarm/inkcal.py`); see the README for the procedure.
