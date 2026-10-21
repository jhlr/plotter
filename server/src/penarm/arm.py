"""Owner of the draw cycle: path -> Cartesian interpolation -> IK -> link. Everything else is a primitive."""
from .config import ArmConfig
from .errors import Unreachable
from .kinematics import fk, interpolate, page_to_servos, servos_to_joints
from .link import Link


class Arm:
    def __init__(self, cfg: ArmConfig, link: Link) -> None:
        self.cfg = cfg
        self.link = link
        self.pos: tuple[float, float] | None = None  # last commanded page position (mm)
        link.set_speed(cfg.speed_dps)

    def move_to(self, x: float, y: float) -> None:
        """Straight line from the current position to (x, y); validated fully before moving."""
        start = self.pos
        pts = interpolate(start, (x, y), self.cfg.seg_mm) if start else [(x, y)]
        servos = [page_to_servos(self.cfg, px, py) for px, py in pts]  # raises before any motion
        for s1, s2 in servos:
            self.link.move(s1, s2)
        self.pos = (x, y)

    def draw_polyline(self, points: list[tuple[float, float]]) -> None:
        if not points:
            raise ValueError("empty path")
        for p in points:  # whole path validated up front: no half-drawn strokes
            page_to_servos(self.cfg, *p)
        for x, y in points:
            self.move_to(x, y)

    def tip_fk(self) -> tuple[float, float]:
        """Tip position (mm) from the servo angles the firmware reports (kinematic estimate)."""
        _, _, s1, s2 = self.link.read()
        return fk(self.cfg, *servos_to_joints(self.cfg, s1, s2))

    def state(self) -> dict[str, object]:
        adc1, adc2, s1, s2 = self.link.read()
        return {"servo_deg": (s1, s2), "pot_raw": (adc1, adc2), "tip_mm": self.tip_fk(),
                "last_commanded_mm": self.pos}


__all__ = ["Arm", "Unreachable"]
