import math

from penarm.profile import step_times


def _line(n: int, step: float = 1.0) -> list[tuple[float, float]]:
    return [(i * step, 0.0) for i in range(n + 1)]


def test_a_straight_run_cruises_at_the_feed_and_eases_in_and_out() -> None:
    ms = step_times(_line(200), feed=60.0, accel=300.0, slow=15.0)
    cruise = round(1000 / 60.0)
    assert ms[100] == cruise
    assert ms[0] > cruise and ms[-1] > cruise


def test_total_time_is_never_shorter_than_length_over_feed() -> None:
    ms = step_times(_line(200), feed=60.0, accel=300.0, slow=15.0)
    assert sum(ms) >= 200 / 60.0 * 1000 - 5


def test_a_right_angle_corner_slows_down_and_a_gentle_bend_does_not() -> None:
    corner = [(float(i), 0.0) for i in range(60)] + [(59.0, float(i)) for i in range(1, 60)]
    ms = step_times(corner, feed=60.0, accel=300.0, slow=15.0)
    assert ms[58] > ms[20] and ms[59] > ms[20]  # the steps next to the corner
    bend = [(math.cos(i / 40) * 100, math.sin(i / 40) * 100) for i in range(120)]
    mb = step_times(bend, feed=60.0, accel=300.0, slow=15.0)
    assert mb[60] <= round(1000 * math.dist(bend[60], bend[61]) / 60.0) + 1


def test_speed_never_changes_faster_than_the_acceleration_limit() -> None:
    pts = _line(150)
    ms = step_times(pts, feed=60.0, accel=300.0, slow=15.0)
    v = [1000.0 / m for m in ms]  # mm/s per 1 mm step (whole-ms rounding blurs it by about 2 mm/s)
    assert all(abs(b * b - a * a) <= 2 * 300.0 * 1.0 + 450 for a, b in zip(v, v[1:]))


def test_zero_length_steps_take_no_time_and_short_paths_work() -> None:
    assert step_times([(0.0, 0.0)], 60.0, 300.0, 15.0) == []
    assert step_times([(0.0, 0.0), (0.0, 0.0), (1.0, 0.0)], 60.0, 300.0, 15.0)[0] == 0
