"""The arm with NO abstraction: you send the board's own text protocol, one line per argument.

    python examples/raw.py "R"                          # where are the two servos now?
    python examples/raw.py "A 100 140"                  # go to servo 1 = 100 deg, servo 2 = 140 deg
    python examples/raw.py "A 100 140" "A 80 120" "?"   # up to 4 lines in a row (the board resets every time the port opens)

Lines: A <servo1> <servo2>  go to those angles (degrees), reply OK on arrival;  R  read the servos (reply R adc1 adc2 servo1 servo2);
?  status;  X  abort. Nothing else is sent.
There is no (x, y), no millimetres and no sheet here: only two servo angles. Servo angles are NOT the arm's joint angles
(each servo horn has its own offset and direction). As a guard, an A line outside the servo range the sheet needs (plus a margin,
and the straight pose) is refused: past that the arm folds onto itself or hits its base."""
import sys

from penarm import find_port
from penarm.calibration import CalibrationStore
from penarm.canvas import safe_canvas
from penarm.config import DEFAULT
from penarm.kinematics import page_to_servos
from penarm.link import SerialLink

MAX_LINES, MARGIN_DEG = 4, 15.0
cfg = CalibrationStore().apply(DEFAULT)
canvas = safe_canvas(cfg)
poses = [page_to_servos(cfg, *canvas.to_page(x, y)) for x in (0, canvas.w / 2, canvas.w) for y in (0, canvas.h / 2, canvas.h)]
poses.append((cfg.offset1 + 90 / cfg.sign1, cfg.offset2))  # the straight arm: joint 1 = 90, joint 2 = 0
LO1, HI1 = min(p[0] for p in poses) - MARGIN_DEG, max(p[0] for p in poses) + MARGIN_DEG
LO2, HI2 = min(p[1] for p in poses) - MARGIN_DEG, max(p[1] for p in poses) + MARGIN_DEG


def refusal(line: str) -> str | None:
    """Why this line must not be sent, or None if it is allowed."""
    parts = line.split()
    if parts[:1] in (["?"], ["R"], ["X"]) and len(parts) == 1:
        return None
    if len(parts) == 3 and parts[0] == "A":
        try:
            s1, s2 = float(parts[1]), float(parts[2])
        except ValueError:
            return "A needs two numbers: A <servo1> <servo2>"
        if not (LO1 <= s1 <= HI1 and LO2 <= s2 <= HI2):
            return f"outside the safe servo range (servo1 {LO1:.0f}..{HI1:.0f}, servo2 {LO2:.0f}..{HI2:.0f}): the arm could fold or hit its base"
        return None
    return "only these lines are allowed: A <servo1> <servo2>, R, ?, X"


if len(sys.argv) < 2:
    sys.exit(__doc__)
if len(sys.argv) - 1 > MAX_LINES:
    sys.exit(f"at most {MAX_LINES} lines per call; send the rest in another call")
for line in sys.argv[1:]:  # check everything before opening the board: a refused line stops the whole call
    if (why := refusal(line)) is not None:
        sys.exit(f"> {line}\n< REFUSED: {why}")
link = SerialLink(find_port())
try:
    for line in sys.argv[1:]:
        try:
            print(f"> {line}\n< {link.raw(line)}")
        except (RuntimeError, TimeoutError) as e:
            print(f"> {line}\n< ERROR: {e}")
finally:
    link.close()
