"""The arm with NO abstraction: you send the board's own text protocol, one line per argument.

    python examples/raw.py "A 100 140"                  # go to servo 1 = 100 deg, servo 2 = 140 deg
    python examples/raw.py "A 100 140" "A 80 120" "?"   # several lines in a row (the board resets every time the port opens)

Lines: A <servo1> <servo2>  go to those angles (0-180 degrees), reply OK on arrival;  ?  status;  X  abort.
There is no (x, y), no millimetres and no sheet here: only two servo angles. Servo angles are NOT the arm's joint angles
(each servo horn has its own offset and direction), and nothing stops the pen from leaving the paper."""
import sys

from penarm import find_port
from penarm.link import SerialLink

if len(sys.argv) < 2:
    sys.exit(__doc__)
link = SerialLink(find_port())
try:
    for line in sys.argv[1:]:
        try:
            print(f"> {line}\n< {link.raw(line)}")
        except (RuntimeError, TimeoutError) as e:
            print(f"> {line}\n< ERROR: {e}")
finally:
    link.close()
