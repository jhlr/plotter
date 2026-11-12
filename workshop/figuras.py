"""The two figures the workshop deck draws from the real arm geometry (penarm.config), not by eye: FIG["anatomy"] (the two
links and their angles) and FIG["reveal"] (what the phase 1 example draws). Each is (width, height, inner svg); the deck
renders them to PNG with rsvg-convert."""
import math

from penarm.calibration import CalibrationStore
from penarm.config import DEFAULT
from penarm.shapes import arc_points

CFG = CalibrationStore().apply(DEFAULT)
DARK, CARD, EDGE, LIGHT = "#12161F", "#1D2330", "#313A4D", "#F4F1EA"
ORANGE, DORANGE, BLUE, MUTED_D = "#E8743B", "#C2501B", "#4C8DF6", "#AEB6C4"

# ---------- arm drawing, from the real kinematics ----------
def arm(base: tuple[float, float], t1: float, t2: float, k: float, ghost: bool = False, colors: tuple[str, str] = (BLUE, ORANGE)) -> tuple[str, tuple[float, float], tuple[float, float]]:
    """SVG for the two links. base in px; t1 from +x, t2 relative to link 1 (deg); k = px per mm. Returns svg, elbow px, tip px."""
    a1, a12 = math.radians(t1), math.radians(t1 + t2)
    ex, ey = base[0] + k * CFG.l1 * math.cos(a1), base[1] - k * CFG.l1 * math.sin(a1)
    tx, ty = ex + k * CFG.l2 * math.cos(a12), ey - k * CFG.l2 * math.sin(a12)
    op = ' opacity="0.35"' if ghost else ""
    w1, w2 = 12 * k / 2.4, 10 * k / 2.4
    svg = (f'<g{op}><line x1="{base[0]:.1f}" y1="{base[1]:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{colors[0]}" stroke-width="{w1:.1f}" stroke-linecap="round"/>'
           f'<line x1="{ex:.1f}" y1="{ey:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" stroke="{colors[1]}" stroke-width="{w2:.1f}" stroke-linecap="round"/>'
           f'<circle cx="{base[0]:.1f}" cy="{base[1]:.1f}" r="{9 * k / 2.4:.1f}" fill="#1D2330" stroke="{LIGHT}" stroke-width="3"/>'
           f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="{8 * k / 2.4:.1f}" fill="#1D2330" stroke="{LIGHT}" stroke-width="3"/>'
           f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="{4 * k / 2.4:.1f}" fill="{DARK}"/></g>')
    return svg, (ex, ey), (tx, ty)


def arc_marker(c: tuple[float, float], r: float, a0: float, a1: float, color: str) -> str:
    """Arc from angle a0 to a1 (deg, math orientation) around px point c."""
    p0 = (c[0] + r * math.cos(math.radians(a0)), c[1] - r * math.sin(math.radians(a0)))
    p1 = (c[0] + r * math.cos(math.radians(a1)), c[1] - r * math.sin(math.radians(a1)))
    sweep = 0 if a1 > a0 else 1
    return f'<path d="M{p0[0]:.1f} {p0[1]:.1f} A{r} {r} 0 0 {sweep} {p1[0]:.1f} {p1[1]:.1f}" fill="none" stroke="{color}" stroke-width="4"/>'


def label(x: float, y: float, text: str, color: str, size: int = 30, anchor: str = "start") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}" font-size="{size}" font-weight="700" text-anchor="{anchor}" font-family="Space Grotesk, Arial, sans-serif">{text}</text>'


def badge(x: float, y: float, n: int) -> str:
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="22" fill="{ORANGE}"/>'
            f'<text x="{x:.1f}" y="{y + 9:.1f}" fill="{DARK}" font-size="26" font-weight="700" text-anchor="middle" font-family="Space Grotesk, Arial, sans-serif">{n}</text>')


FIG: dict[str, tuple[int, int, str]] = {}  # name -> (width, height, inner svg): used by build_dinamica.py

# anatomy: the two links, base to elbow to pen
base = (300.0, 610.0)
a_svg, el, tp = arm(base, 108, -78, 3.0)
anat = (
    f'<rect x="60" y="30" width="760" height="420" rx="16" fill="{LIGHT}"/>'
    f'<line x1="{base[0]}" y1="{base[1]}" x2="{base[0] + 330}" y2="{base[1]}" stroke="{MUTED_D}" stroke-width="3" stroke-dasharray="10 8"/>'
    + a_svg
    + arc_marker(base, 110, 0, 108, ORANGE) + label(base[0] + 118, base[1] - 70, "θ1", ORANGE, 38)
    + f'<line x1="{el[0]:.1f}" y1="{el[1]:.1f}" x2="{el[0] + (el[0] - base[0]) * 0.45:.1f}" y2="{el[1] + (el[1] - base[1]) * 0.45:.1f}" stroke="{MUTED_D}" stroke-width="3" stroke-dasharray="10 8"/>'
    + arc_marker(el, 90, 108, 108 - 78, ORANGE) + label(el[0] + 30, el[1] - 84, "θ2", ORANGE, 38)
    + f'<rect x="{base[0] - 90}" y="{base[1] + 16}" width="180" height="62" rx="10" fill="{CARD}" stroke="{EDGE}" stroke-width="3"/>'
    + label(base[0], base[1] + 56, "Arduino", LIGHT, 26, "middle")
    + badge(base[0] - 70, base[1] - 56, 1) + badge(el[0] - 54, el[1] - 4, 2) + badge(tp[0] + 56, tp[1] - 12, 3)
)
FIG["anatomy"] = (900, 720, anat)

# reveal: the zigzag and the circle of the phase 1 example
poly = [[10, 10], [25, 40], [40, 10], [55, 40]]
circ = arc_points(95, 25, 15, 0, 360)
kk = 3.4
ph = 48 * kk
pp = lambda x, y: f"{x * kk + 20:.1f},{ph - y * kk + 20:.1f}"  # noqa: E731
path_pts = [tuple(p) for p in poly] + [tuple(p) for p in circ]
reveal_inner = (f'<rect width="{175 * kk + 40:.0f}" height="{ph + 40:.0f}" rx="12" fill="{LIGHT}"/>'
                f'<polyline points="{" ".join(pp(*p) for p in poly)}" fill="none" stroke="{DORANGE}" stroke-width="5" stroke-linejoin="round"/>'
                f'<polyline points="{pp(*poly[-1])} {pp(*path_pts[len(poly)])}" fill="none" stroke="{DORANGE}" stroke-width="5" stroke-dasharray="3 0"/>'
                f'<polyline points="{" ".join(pp(*p) for p in path_pts[len(poly):])}" fill="none" stroke="{DORANGE}" stroke-width="5"/>')
FIG["reveal"] = (round(175 * kk + 40), round(ph + 40), reveal_inner)
