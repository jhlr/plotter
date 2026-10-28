"""Residual correction mesh: the part of the arm's position error that the kinematic model cannot explain.

It is measured from a drawn rectangle. Each edge gives the distance between the ink and the commanded line along that
edge (the bottom and top edges give a vertical error, the left and right edges a horizontal one). The interior is
filled by interpolating between opposite edges, so any drawing inside the rectangle is corrected, not only its border.
The error repeats from drawing to drawing (bottom edge of two rectangles on different days: correlation 0.94, 1.3 mm
rms difference), which is what makes a correction worth having."""
from dataclasses import dataclass

import numpy as np

XY = tuple[float, float]


def _profile(t: np.ndarray, d: np.ndarray, at: float) -> float:
    """Linear interpolation of an edge profile, held constant past its ends."""
    return float(np.interp(at, t, d))


@dataclass(frozen=True)
class CorrectionMesh:
    """x0..x1 / y0..y1: the measured rectangle in page mm. Profiles are (positions along the edge, error there), where
    error = observed - commanded, in mm. bottom/top: error in y as a function of x; left/right: error in x as a
    function of y."""

    x0: float
    y0: float
    x1: float
    y1: float
    bottom: tuple[tuple[float, ...], tuple[float, ...]]
    top: tuple[tuple[float, ...], tuple[float, ...]]
    left: tuple[tuple[float, ...], tuple[float, ...]]
    right: tuple[tuple[float, ...], tuple[float, ...]]

    def error_at(self, x: float, y: float) -> XY:
        """Predicted (dx, dy) the arm lands off target at page point (x, y)."""
        v = min(1.0, max(0.0, (y - self.y0) / (self.y1 - self.y0)))
        u = min(1.0, max(0.0, (x - self.x0) / (self.x1 - self.x0)))
        dy = (1 - v) * _profile(np.array(self.bottom[0]), np.array(self.bottom[1]), x) + v * _profile(
            np.array(self.top[0]), np.array(self.top[1]), x
        )
        dx = (1 - u) * _profile(np.array(self.left[0]), np.array(self.left[1]), y) + u * _profile(
            np.array(self.right[0]), np.array(self.right[1]), y
        )
        return dx, dy

    def corrected(self, x: float, y: float) -> XY:
        """Where to aim so the pen lands on (x, y)."""
        dx, dy = self.error_at(x, y)
        return x - dx, y - dy

    def to_json(self) -> dict[str, object]:
        return {"rect": [self.x0, self.y0, self.x1, self.y1], "bottom": self.bottom, "top": self.top,
                "left": self.left, "right": self.right}

    @staticmethod
    def from_json(data: dict[str, object]) -> "CorrectionMesh":
        x0, y0, x1, y1 = (float(v) for v in data["rect"])  # type: ignore[attr-defined]

        def edge(name: str) -> tuple[tuple[float, ...], tuple[float, ...]]:
            pair: list[list[float]] = data[name]  # type: ignore[assignment]
            return tuple(float(v) for v in pair[0]), tuple(float(v) for v in pair[1])

        return CorrectionMesh(x0, y0, x1, y1, edge("bottom"), edge("top"), edge("left"), edge("right"))
