"""A drawing the board plays on its own: servo waypoints -> start pose + int8 deltas in 0.1 degree units.

The board keeps these in EEPROM (2 bytes per step), so the host can disconnect after starting it. The encoder tracks the
quantised position, so rounding never accumulates; a jump larger than one int8 is split into equal pieces."""
import math

UNIT_DEG = 0.1
MAX_DELTA = 127

Step = tuple[int, int]


def encode(points: list[tuple[float, float]]) -> tuple[Step, list[Step]]:
    """(start pose, steps), both in 0.1 degree units. Steps that would not move the arm are dropped."""
    if not points:
        raise ValueError("no waypoints to store")
    q = [(round(a / UNIT_DEG), round(b / UNIT_DEG)) for a, b in points]
    cur, steps = q[0], []
    for target in q[1:]:
        da, db = target[0] - cur[0], target[1] - cur[1]
        pieces = max(1, math.ceil(max(abs(da), abs(db)) / MAX_DELTA))
        prev = cur
        for i in range(1, pieces + 1):
            nxt = (cur[0] + round(da * i / pieces), cur[1] + round(db * i / pieces))
            if nxt != prev:
                steps.append((nxt[0] - prev[0], nxt[1] - prev[1]))
            prev = nxt
        cur = target
    return q[0], steps


def decode(start: Step, steps: list[Step]) -> list[tuple[float, float]]:
    """What the board will play, in degrees (the inverse of encode, for previews and tests)."""
    a, b = start
    out = [(a * UNIT_DEG, b * UNIT_DEG)]
    for da, db in steps:
        a, b = a + da, b + db
        out.append((a * UNIT_DEG, b * UNIT_DEG))
    return out
