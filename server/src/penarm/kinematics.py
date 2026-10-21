"""Planar 2-link inverse/forward kinematics and page <-> servo mapping."""
import math

from .config import ArmConfig


class Unreachable(ValueError):
    pass


def ik(cfg: ArmConfig, x: float, y: float) -> tuple[float, float]:
    """Page point (mm) -> joint angles (deg): (theta1 from +x, theta2 relative to link 1)."""
    dx, dy = x - cfg.base_x, y - cfg.base_y
    r2 = dx * dx + dy * dy
    c2 = (r2 - cfg.l1**2 - cfg.l2**2) / (2 * cfg.l1 * cfg.l2)
    if not -1.0 <= c2 <= 1.0:
        raise Unreachable(f"({x:.1f},{y:.1f}) outside arm reach")
    t2 = math.acos(c2) * (-1 if cfg.elbow_up else 1)
    t1 = math.atan2(dy, dx) - math.atan2(cfg.l2 * math.sin(t2), cfg.l1 + cfg.l2 * math.cos(t2))
    return math.degrees(t1), math.degrees(t2)


def fk(cfg: ArmConfig, t1_deg: float, t2_deg: float) -> tuple[float, float]:
    t1, t12 = math.radians(t1_deg), math.radians(t1_deg + t2_deg)
    return (
        cfg.base_x + cfg.l1 * math.cos(t1) + cfg.l2 * math.cos(t12),
        cfg.base_y + cfg.l1 * math.sin(t1) + cfg.l2 * math.sin(t12),
    )


def joints_to_servos(cfg: ArmConfig, t1: float, t2: float) -> tuple[float, float]:
    s1 = cfg.offset1 + t1 / cfg.sign1
    s2 = cfg.offset2 + t2 / cfg.sign2
    if not (0.0 <= s1 <= 180.0 and 0.0 <= s2 <= 180.0):
        raise Unreachable(f"servo angles ({s1:.1f},{s2:.1f}) out of 0-180 range")
    return s1, s2


def servos_to_joints(cfg: ArmConfig, s1: float, s2: float) -> tuple[float, float]:
    return cfg.sign1 * (s1 - cfg.offset1), cfg.sign2 * (s2 - cfg.offset2)


def page_to_servos(cfg: ArmConfig, x: float, y: float) -> tuple[float, float]:
    if not (0.0 <= x <= cfg.page_w and 0.0 <= y <= cfg.page_h):
        raise Unreachable(f"({x:.1f},{y:.1f}) outside page {cfg.page_w}x{cfg.page_h}")
    return joints_to_servos(cfg, *ik(cfg, x, y))


def interpolate(
    p0: tuple[float, float], p1: tuple[float, float], step: float
) -> list[tuple[float, float]]:
    """Points along p0->p1 (excluding p0, including p1) spaced <= step mm."""
    n = max(1, math.ceil(math.dist(p0, p1) / step))
    return [(p0[0] + (p1[0] - p0[0]) * i / n, p0[1] + (p1[1] - p0[1]) * i / n) for i in range(1, n + 1)]
