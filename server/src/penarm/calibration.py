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
PAPER_FIELDS = ("page_w", "page_h")
SAVED_FIELDS = (*POSE_FIELDS, *LENGTH_FIELDS, *PAPER_FIELDS, "sign1", "sign2")
# fit scope -> (free parameters, minimum points; every point gives 2 equations)
SCOPES: dict[str, tuple[tuple[str, ...], int]] = {
    "base": (("base_x", "base_y"), 1),  # the paper moved: re-register it, keep offsets and lengths
    "pose": (POSE_FIELDS, 4),
    "full": (POSE_FIELDS + LENGTH_FIELDS, 7),
}


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


def fit(cfg: ArmConfig, obs: list[Observation], scope: str = "pose") -> FitResult:
    """Fit the parameters of `scope`. For 'pose' and 'full' the best of the 4 sign combinations wins (signs are
    uncertain on a fresh build); joint angles at servo=90 are kept when a sign flips so every start is near the same
    physical pose."""
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {sorted(SCOPES)}")
    names, need = SCOPES[scope]
    if len(obs) < need:
        raise ValueError(f"scope '{scope}' needs at least {need} calibration points, have {len(obs)}")
    if scope == "base":
        return _lm(cfg, obs, names)
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


# ---- paper registration from a photo: the LLM reads the paper corners (and the pen tip) in pixels ----

CORNER_ORDER = ("near_left", "near_right", "far_right", "far_left")  # near = side closest to the arm base


def homography(src: list[tuple[float, float]], dst: list[tuple[float, float]]) -> list[list[float]]:
    """3x3 projective map taking the 4 src points to the 4 dst points (h33 = 1)."""
    if len(src) != 4 or len(dst) != 4:
        raise ValueError("a homography needs exactly 4 point pairs")
    a: list[list[float]] = []
    b: list[float] = []
    for (x, y), (u, v) in zip(src, dst):
        a += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        b += [u, v]
    h = _solve(a, b)
    return [h[0:3], h[3:6], [h[6], h[7], 1.0]]


def apply_homography(h: list[list[float]], p: tuple[float, float]) -> tuple[float, float]:
    w = h[2][0] * p[0] + h[2][1] * p[1] + h[2][2]
    return (h[0][0] * p[0] + h[0][1] * p[1] + h[0][2]) / w, (h[1][0] * p[0] + h[1][1] * p[1] + h[1][2]) / w


def paper_point_from_photo(
    corners_px: dict[str, tuple[float, float]], point_px: tuple[float, float], paper_w: float, paper_h: float
) -> tuple[float, float]:
    """Pixel -> paper mm (origin = near-left corner, x along the near edge, y toward the far edge)."""
    missing = [k for k in CORNER_ORDER if k not in corners_px]
    if missing:
        raise ValueError(f"missing paper corners: {missing}")
    src = [corners_px[k] for k in CORNER_ORDER]
    dst = [(0.0, 0.0), (paper_w, 0.0), (paper_w, paper_h), (0.0, paper_h)]
    return apply_homography(homography(src, dst), point_px)


def corner_sanity(corners_px: dict[str, tuple[float, float]]) -> list[str]:
    """Warnings for corner sets that cannot be a photographed rectangle (wrong order, collinear, mirrored)."""
    pts = [corners_px[k] for k in CORNER_ORDER]
    cross = []
    for i in range(4):
        a, b, c = pts[i], pts[(i + 1) % 4], pts[(i + 2) % 4]
        cross.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
    if not (all(v > 0 for v in cross) or all(v < 0 for v in cross)):
        return ["corners do not form a convex quadrilateral in the order near_left, near_right, far_right, far_left"]
    return []


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

    def fit(self, base_cfg: ArmConfig, scope: str = "pose", last: int | None = None) -> FitResult:
        pts = self.points[-last:] if last else self.points
        res = fit(self.apply(base_cfg), pts, scope)
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
