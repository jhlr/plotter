"""Calibration: observations (servo angles, measured tip position) -> offsets/base (and link lengths).
Stored in a JSON file so calibrating never means editing code; pure-Python Levenberg-Marquardt (no scipy)."""
import itertools
import json
import math
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .config import ArmConfig
from .kinematics import fk, servos_to_joints

POSE_FIELDS = ("offset1", "offset2", "base_x", "base_y")
LENGTH_FIELDS = ("l1", "l2")
SAVED_FIELDS = (*POSE_FIELDS, *LENGTH_FIELDS, "sign1", "sign2")
MIN_POINTS = 4  # 4 free params, 2 equations per point
MIN_POINTS_LENGTHS = 7


@dataclass(frozen=True)
class Observation:
    s1: float
    s2: float
    x: float  # measured tip position, page mm
    y: float


@dataclass(frozen=True)
class FitResult:
    cfg: ArmConfig
    rmse_mm: float
    n: int


def _updated(cfg: ArmConfig, changes: dict[str, float]) -> ArmConfig:
    return ArmConfig(**{**asdict(cfg), **changes})


def predict(cfg: ArmConfig, s1: float, s2: float) -> tuple[float, float]:
    return fk(cfg, *servos_to_joints(cfg, s1, s2))


def _residuals(cfg: ArmConfig, obs: list[Observation]) -> list[float]:
    out: list[float] = []
    for o in obs:
        px, py = predict(cfg, o.s1, o.s2)
        out += [px - o.x, py - o.y]
    return out


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(m[r][i]))
        m[i], m[p] = m[p], m[i]
        if abs(m[i][i]) < 1e-12:
            raise ValueError("calibration points are degenerate: spread them over the workspace")
        for r in range(i + 1, n):
            f = m[r][i] / m[i][i]
            m[r] = [x - f * y for x, y in zip(m[r], m[i])]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


def _lm(cfg: ArmConfig, obs: list[Observation], names: tuple[str, ...], iters: int = 80) -> FitResult:
    def with_x(v: list[float]) -> ArmConfig:
        return _updated(cfg, dict(zip(names, v)))

    x = [float(getattr(cfg, n)) for n in names]
    r = _residuals(with_x(x), obs)
    cost = sum(v * v for v in r)
    lam = 1e-3
    for _ in range(iters):
        jac = []
        for j in range(len(x)):
            h = 1e-4 * max(1.0, abs(x[j]))
            xp = x[:]
            xp[j] += h
            rp = _residuals(with_x(xp), obs)
            jac.append([(rp[i] - r[i]) / h for i in range(len(r))])
        a = [[sum(jac[i][k] * jac[j][k] for k in range(len(r))) for j in range(len(x))] for i in range(len(x))]
        g = [sum(jac[i][k] * r[k] for k in range(len(r))) for i in range(len(x))]
        improved = False
        for _ in range(12):
            damped = [[a[i][j] + (lam * max(a[i][i], 1e-9) if i == j else 0.0) for j in range(len(x))] for i in range(len(x))]
            step = _solve(damped, [-v for v in g])
            xn = [x[i] + step[i] for i in range(len(x))]
            rn = _residuals(with_x(xn), obs)
            cn = sum(v * v for v in rn)
            if cn < cost:
                x, r, cost, lam, improved = xn, rn, cn, max(lam / 3, 1e-9), True
                break
            lam *= 4
        if not improved or max(abs(s) for s in step) < 1e-7:
            break
    return FitResult(with_x(x), math.sqrt(cost / len(obs)), len(obs))


def fit(cfg: ArmConfig, obs: list[Observation], fit_lengths: bool = False) -> FitResult:
    """Best of the 4 sign combinations (signs are uncertain on a fresh build); joint angles at servo=90 are kept
    when a sign flips so every start is near the same physical pose."""
    need = MIN_POINTS_LENGTHS if fit_lengths else MIN_POINTS
    if len(obs) < need:
        raise ValueError(f"need at least {need} calibration points, have {len(obs)}")
    names = POSE_FIELDS + (LENGTH_FIELDS if fit_lengths else ())
    best: FitResult | None = None
    for s1, s2 in itertools.product((1.0, -1.0), repeat=2):
        start = replace(
            cfg, sign1=s1, sign2=s2,
            offset1=90.0 - (cfg.sign1 / s1) * (90.0 - cfg.offset1),
            offset2=90.0 - (cfg.sign2 / s2) * (90.0 - cfg.offset2),
        )
        res = _lm(start, obs, names)
        if best is None or res.rmse_mm < best.rmse_mm:
            best = res
    assert best is not None
    return best


class CalibrationStore:
    """calibration.json: recorded observations + the last fitted parameters."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(os.environ.get("PENARM_CALIBRATION", "calibration.json"))
        self.points: list[Observation] = []
        self.params: dict[str, float] = {}
        self.rmse_mm: float | None = None
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self.points = [Observation(**p) for p in data.get("points", [])]
            self.params = {k: float(v) for k, v in data.get("params", {}).items() if k in SAVED_FIELDS}
            self.rmse_mm = data.get("rmse_mm")

    def apply(self, cfg: ArmConfig) -> ArmConfig:
        return _updated(cfg, self.params)

    def add_point(self, o: Observation) -> None:
        self.points.append(o)
        self.save()

    def clear_points(self) -> None:
        self.points = []
        self.save()

    def fit(self, base_cfg: ArmConfig, fit_lengths: bool = False) -> FitResult:
        res = fit(self.apply(base_cfg), self.points, fit_lengths)
        self.params = {f: float(getattr(res.cfg, f)) for f in SAVED_FIELDS}
        self.rmse_mm = res.rmse_mm
        self.save()
        return res

    def save(self) -> None:
        data = {"points": [vars(p) for p in self.points], "params": self.params, "rmse_mm": self.rmse_mm}
        self.path.write_text(json.dumps(data, indent=2))


def suggest_poses(cfg: ArmConfig, n: int = 8) -> list[tuple[float, float]]:
    """Servo poses spread over the workspace whose estimated tip lies on the page (under the current estimate)."""
    cands = [
        (float(a), float(b))
        for a in range(40, 161, 15)
        for b in range(30, 151, 15)
        if cfg.servo_min <= a <= cfg.servo_max and cfg.servo_min <= b <= cfg.servo_max
        and 0.0 <= predict(cfg, a, b)[0] <= cfg.page_w and 0.0 <= predict(cfg, a, b)[1] <= cfg.page_h
    ]
    if len(cands) <= n:
        return cands
    cands.sort(key=lambda p: (round(predict(cfg, *p)[1] / 40), predict(cfg, *p)[0]))  # rows by y, then x
    return [cands[round(i * (len(cands) - 1) / (n - 1))] for i in range(n)]
