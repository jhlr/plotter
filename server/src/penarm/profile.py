"""Speed profile along a path: constant feed on straight runs, braking into corners, soft start and stop.

The servos have a dead band, so slow motion sticks and jerks; but a jolt at a stroke's start, end or corner is as bad
(ink blots, wobble). Each Cartesian step gets a duration so the tip accelerates at most `accel` mm/s^2, never exceeds
`feed`, and slows to `slow` mm/s at the ends and at sharp turns."""
import math

XY = tuple[float, float]


def step_times(points: list[XY], feed: float, accel: float, slow: float) -> list[int]:
    """Milliseconds for each step points[i] -> points[i+1] (zero for a step of zero length)."""
    n = len(points) - 1
    if n < 1:
        return []
    d = [math.dist(points[i], points[i + 1]) for i in range(n)]
    v = [feed] * (n + 1)
    v[0] = v[n] = slow
    for i in range(1, n):  # junction speed: full on a straight, down to `slow` at a right angle or sharper
        if d[i - 1] > 0 and d[i] > 0:
            cos = ((points[i][0] - points[i - 1][0]) * (points[i + 1][0] - points[i][0])
                   + (points[i][1] - points[i - 1][1]) * (points[i + 1][1] - points[i][1])) / (d[i - 1] * d[i])
            v[i] = min(feed, max(slow, feed * cos))
    for i in range(n):  # accelerate no faster than `accel` going forward ...
        v[i + 1] = min(v[i + 1], math.sqrt(v[i] ** 2 + 2 * accel * d[i]))
    for i in range(n - 1, -1, -1):  # ... and brake no harder than `accel` going backward
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2 * accel * d[i]))
    out: list[int] = []
    carry = 0.0  # rounding to whole ms must not add up to a drift in total time
    for i in range(n):
        if d[i] == 0:
            out.append(0)
            continue
        want = 1000.0 * 2 * d[i] / (v[i] + v[i + 1]) + carry
        ms = max(1, round(want))
        carry = want - ms
        out.append(ms)
    return out
