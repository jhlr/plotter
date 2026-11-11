"""Regenerates the workshop deck (Portuguese, 1920x1080 Slides format) into workshop/deck/project/.
The arm illustrations are computed from the real arm geometry (penarm.config / kinematics), not drawn by eye:
    python workshop/build_deck.py"""
import json
import math
from pathlib import Path

from penarm.calibration import CalibrationStore
from penarm.config import DEFAULT
from penarm.kinematics import ik
from penarm.shapes import arc_points

CFG = CalibrationStore().apply(DEFAULT)
OUT = Path(__file__).parent / "deck" / "project"
DARK, CARD, EDGE, LIGHT, PAPER = "#12161F", "#1D2330", "#313A4D", "#F4F1EA", "#FFFFFF"
ORANGE, DORANGE, BLUE, INK, MUTED_D, MUTED_L = "#E8743B", "#C2501B", "#4C8DF6", "#1B1F2A", "#AEB6C4", "#4A5160"
H = "font-family:'Space Grotesk', Arial, sans-serif;font-weight:600"
MONO = "font-family:'Courier New', monospace"


def section(sid: str, bg: str, fg: str, body: str, note: str, gap: int = 48, pad: str = "96px 128px 112px") -> str:
    return (f'<section id="{sid}" data-transition="fade" style="background:{bg};color:{fg};font-family:\'Inter\', Arial, sans-serif;'
            f'padding:{pad};display:flex;flex-direction:column;gap:{gap}px">\n{body}\n<aside>{note}</aside>\n</section>\n')


def track(active: int, dark: bool) -> str:
    """Three-step progress strip: where we are in the workshop."""
    chips = []
    for i, name in enumerate(("1 · Na mão", "2 · Com a LLM", "3 · Apresentação"), 1):
        on = i == active
        bg = ORANGE if on else ("#1D2330" if dark else "#E7E2D6")
        fg = DARK if on else (MUTED_D if dark else MUTED_L)
        chips.append(f'<p style="background:{bg};color:{fg};border-radius:999px;padding:10px 28px;font-size:26px;font-weight:600">{name}</p>')
    return f'<div style="display:flex;gap:14px">{"".join(chips)}</div>'


def title(text: str, size: int = 76) -> str:
    return f'<h2 style="{H};font-size:{size}px;line-height:1.1">{text}</h2>'


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


def svg_wrap(w: int, h: int, inner: str, label: str, css_w: int) -> str:
    return (f'<svg aria-label="{label}" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'style="width:{css_w}px;height:{round(css_w * h / w)}px">{inner}</svg>')


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


def to_page_px(x: float, y: float, k: float, h: float) -> tuple[float, float]:
    return x * k, h - y * k


def card(inner: str, dark: bool, flex: str = "1") -> str:
    bg, bd = (CARD, EDGE) if dark else (PAPER, "#DAD5C9")
    return f'<div style="flex:{flex};display:flex;flex-direction:column;gap:18px;background:{bg};padding:44px;border:2px solid {bd};border-radius:20px">{inner}</div>'


def icon(name: str, color: str, size: int = 72) -> str:
    return f'<x-icon name="{name}" style="color:{color};width:{size}px;height:{size}px"></x-icon>'


def h3(text: str, color: str | None = None, size: int = 46) -> str:
    c = f";color:{color}" if color else ""
    return f'<h3 style="{H};font-size:{size}px{c}">{text}</h3>'


def para(text: str, color: str, size: int = 32) -> str:
    return f'<p style="font-size:{size}px;line-height:1.4;color:{color}">{text}</p>'


def code(lines: list[tuple[str, int]], size: int = 32) -> str:
    rows = "".join(f'<p style="{MONO};font-size:{size}px;color:{"#F4F1EA" if ind >= 0 else MUTED_D};padding:0 0 0 {abs(ind) * 48}px;white-space:pre">{t}</p>' for t, ind in lines)
    return f'<div style="display:flex;flex-direction:column;gap:12px;background:{DARK};padding:40px;border-radius:20px">{rows}</div>'


slides: dict[str, str] = {}
FIG: dict[str, tuple[int, int, str]] = {}  # name -> (width, height, inner svg): reused by build_pptx.py

# 1 cover
k = 2.0
tip = to_page_px(116, 200, 1.0, 0)
cover_arm, _, ctip = arm((300, 520), 118, -72, 1.55)
heart = "M{0} {1} C{2} {3} {4} {5} {6} {7} C{8} {9} {10} {11} {12} {13} Z"
cover_svg = svg_wrap(560, 560, (
    f'<rect x="30" y="30" width="500" height="380" rx="24" fill="{LIGHT}"/>'
    f'<path d="M{ctip[0]:.0f} {ctip[1] + 70:.0f} C{ctip[0] - 80:.0f} {ctip[1] + 10:.0f} {ctip[0] - 60:.0f} {ctip[1] - 70:.0f} {ctip[0]:.0f} {ctip[1] - 35:.0f} '
    f'C{ctip[0] + 60:.0f} {ctip[1] - 70:.0f} {ctip[0] + 80:.0f} {ctip[1] + 10:.0f} {ctip[0]:.0f} {ctip[1] + 70:.0f} Z" fill="none" stroke="{DORANGE}" stroke-width="8" stroke-linejoin="round"/>'
    + cover_arm), "Braço de dois elos desenhando um coração em uma folha", 560)
slides["cover"] = section("cover", DARK, LIGHT, (
    f'<div style="position:absolute;left:1180px;top:200px">{cover_svg}</div>'
    f'<p style="{H};font-size:32px;letter-spacing:4px;color:{ORANGE}">OFICINA · ARDUINO + MCP</p>'
    f'<h1 style="{H};font-size:108px;line-height:1.04;width:1020px">Um braço, dois servos, uma LLM</h1>'
    f'<p style="font-size:40px;line-height:1.35;color:{MUTED_D};width:1000px">Primeiro você manda o braço desenhar com código. Depois, só pede em português.</p>'
), "Abertura. O mesmo braço desenha de dois jeitos: escrevendo código ou pedindo em português. No fim, comparamos o esforço.", 36, "128px 128px 160px")

# 2 what: the chain computer -> board -> arm
def arrow(x0: float, x1: float, y: float, text: str) -> str:
    return (f'<line x1="{x0}" y1="{y}" x2="{x1 - 14}" y2="{y}" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>'
            f'<polygon points="{x1},{y} {x1 - 26},{y - 15} {x1 - 26},{y + 15}" fill="{INK}"/>'
            + label((x0 + x1) / 2, y - 26, text, MUTED_L, 28, "middle"))


arm_px, _, _ = arm((1330, 262), 100, -70, 1.15)
chain = (
    f'<rect x="170" y="40" width="220" height="150" rx="14" fill="{DARK}" stroke="{INK}" stroke-width="6"/>'
    f'<rect x="130" y="190" width="300" height="26" rx="8" fill="{INK}"/>'
    + label(280, 138, "&lt;/&gt;", ORANGE, 64, "middle")
    + f'<rect x="700" y="70" width="264" height="170" rx="16" fill="{BLUE}"/>'
    + "".join(f'<rect x="{724 + i * 22}" y="78" width="14" height="22" fill="{DARK}"/>' for i in range(10))
    + f'<rect x="760" y="130" width="80" height="60" rx="6" fill="{DARK}"/><rect x="870" y="140" width="64" height="40" rx="6" fill="{DARK}"/>'
    + label(832, 224, "UNO", LIGHT, 30, "middle")
    + arrow(450, 680, 150, "USB: ângulos")
    + arrow(984, 1214, 150, "2 servos")
    + arm_px
)
def part(n: str, t: str, d: str) -> str:
    return (f'<div style="flex:1;display:flex;flex-direction:column;gap:14px"><p style="{H};font-size:30px;color:{DORANGE}">{n}</p>'
            f'{h3(t, None, 48)}{para(d, MUTED_L, 32)}</div>')


FIG["chain"] = (1664, 300, chain)
slides["what"] = section("what", LIGHT, INK, (
    title("Três peças")
    + f'<div style="background:{PAPER};border:2px solid #DAD5C9;border-radius:20px;padding:32px 40px">'
    + svg_wrap(1664, 300, chain, "Computador, placa Arduino e braço ligados em sequência", 1560) + '</div>'
    + '<div style="display:flex;gap:56px">'
    + part("SOFTWARE", "Python + MCP", "A classe Plotter planeja o traço. Você chama no Python ou a LLM chama como ferramenta.")
    + part("PLACA", "Arduino Uno", "Recebe os ângulos pela serial e move os servos com tempo e suavidade.")
    + part("BRAÇO", "2 elos, 2 servos", "SG90 e peças impressas em 3D. Sem levantar a caneta: um traço contínuo.")
    + '</div>'
), "Três peças em cadeia: o computador manda ângulos pela USB, o Arduino gira os servos, o braço desenha. Os braços já estão montados e calibrados antes da aula.", 40)

# 3 anatomy
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
slides["anatomy"] = section("anatomy", DARK, LIGHT, (
    title("Anatomia do braço")
    + '<div style="display:flex;gap:56px;align-items:center">'
    + svg_wrap(900, 720, anat, "Braço de dois elos visto de cima, com os ângulos theta 1 e theta 2", 1000)
    + '<div style="flex:1;display:flex;flex-direction:column;gap:36px">'
    + "".join(
        f'<div style="display:flex;gap:24px;align-items:center"><p style="flex:none;width:64px;height:64px;border-radius:50%;background:{ORANGE};color:{DARK};{H};font-size:38px;text-align:center;line-height:64px">{n}</p>'
        f'<div>{h3(t, None, 38)}{para(d, MUTED_D, 28)}</div></div>'
        for n, t, d in ((1, "Ombro (servo 1)", "gira o elo 1, de 108 mm. O ângulo θ1 vem do eixo x."), (2, "Cotovelo (servo 2)", "gira o elo 2, de 106 mm. θ2 é medido a partir do elo 1."), (3, "Ponta: a caneta", "onde o papel é marcado. Não levanta."))
    ) + '</div></div>'
), "Vista de cima. Dois servos, dois elos. Cada ponto do papel corresponde a um par de ângulos (θ1, θ2). O cotovelo sempre dobra para a esquerda.", 36)

# 4 angles: same arm, three target points (inverse kinematics from the real config)
targets = [(70, 165), (118, 196), (172, 158)]
kk = 1.55
panels = []
angle_poses: list[tuple[int, int, str, tuple[int, int], tuple[float, float]]] = []
for tx_, ty_ in targets:
    t1, t2 = ik(CFG, tx_, ty_)
    pw, ph = 230 * kk, 250 * kk
    bpx = to_page_px(CFG.base_x, CFG.base_y, kk, ph)
    pose, _, tipx = arm(bpx, t1, t2, kk)
    inner = (f'<rect width="{pw:.0f}" height="{ph:.0f}" rx="12" fill="{LIGHT}"/>'
             f'<rect x="{24 * kk:.0f}" y="{ph - 201 * kk:.0f}" width="{175 * kk:.0f}" height="{48 * kk:.0f}" fill="none" stroke="{DORANGE}" stroke-width="3" stroke-dasharray="8 6"/>'
             + pose)
    angle_poses.append((round(pw), round(ph), inner, (tx_, ty_), (t1, t2)))
    panels.append(
        f'<div style="flex:1;display:flex;flex-direction:column;gap:16px;align-items:center;background:{CARD};padding:28px;border:2px solid {EDGE};border-radius:20px">'
        + svg_wrap(round(pw), round(ph), inner, f"Braço na posição x {tx_}, y {ty_}", 480)
        + f'<p style="{MONO};font-size:30px;color:{LIGHT}">ponto ({tx_}, {ty_}) mm</p>'
        + f'<p style="{H};font-size:36px;color:{ORANGE}">θ1 = {t1:.0f}°   θ2 = {t2:.0f}°</p></div>')
slides["angles"] = section("angles", DARK, LIGHT, (
    title("Cada ponto do papel tem dois ângulos")
    + f'<div style="display:flex;gap:28px">{"".join(panels)}</div>'
    + para("Você pede uma posição (x, y). O Plotter calcula os ângulos (cinemática inversa) e o Arduino gira os servos. A área tracejada é a folha onde dá para desenhar.", MUTED_D, 32)
), "Os ângulos aqui são calculados pelo mesmo código do braço (ik em kinematics.py), para os três pontos mostrados.", 28)

# 5 sheet: the board, the reach, the usable canvas
kk = 1.7
pw, ph = 230 * kk, 330 * kk
bpx = to_page_px(CFG.base_x, CFG.base_y, kk, ph)
reach = (CFG.l1 + CFG.l2) * kk
pose, _, _ = arm(bpx, 112, -60, kk)
sheet_inner = (
    f'<defs><clipPath id="pg"><rect width="{pw:.0f}" height="{ph:.0f}" rx="12"/></clipPath></defs>'
    f'<rect width="{pw:.0f}" height="{ph:.0f}" rx="12" fill="{LIGHT}"/>'
    f'<circle cx="{bpx[0]:.1f}" cy="{bpx[1]:.1f}" r="{reach:.1f}" fill="none" stroke="{BLUE}" stroke-width="3" stroke-dasharray="10 8" clip-path="url(#pg)"/>'
    f'<rect x="{24 * kk:.0f}" y="{ph - 201 * kk:.0f}" width="{175 * kk:.0f}" height="{48 * kk:.0f}" fill="{ORANGE}" fill-opacity="0.25" stroke="{DORANGE}" stroke-width="4"/>'
    + pose
    + f'<line x1="14" y1="{ph - 14:.0f}" x2="14" y2="{ph - 90:.0f}" stroke="{INK}" stroke-width="3"/><line x1="14" y1="{ph - 14:.0f}" x2="90" y2="{ph - 14:.0f}" stroke="{INK}" stroke-width="3"/>'
    + label(100, ph - 20, "x", INK, 26) + label(22, ph - 96, "y", INK, 26)
)
FIG["sheet"] = (round(pw), round(ph), sheet_inner)
slides["sheet"] = section("sheet", LIGHT, INK, (
    title("A folha: onde o braço alcança")
    + '<div style="display:flex;gap:64px;align-items:center">'
    + svg_wrap(round(pw), round(ph), sheet_inner, "Folha com o alcance do braço e o retângulo útil", 560)
    + '<div style="flex:1;display:flex;flex-direction:column;gap:30px">'
    + para(f'<b>Origem</b> no canto inferior esquerdo do retângulo útil. <b>x</b> vai para a direita, <b>y</b> para cima, tudo em milímetros.', INK, 36)
    + para("<b>Retângulo laranja</b>: a área que o braço alcança por inteiro. Hoje: <b>175 × 48 mm</b>. Fora dele, o código recusa.", INK, 36)
    + para("<b>Círculo azul</b>: o alcance máximo (os dois elos esticados, 214 mm).", INK, 36)
    + para("Para saber o tamanho na hora: <b>p.canvas.w</b> e <b>p.canvas.h</b>.", MUTED_L, 32)
    + '</div></div>'
), "Origem no canto inferior esquerdo do retângulo. Todos os desenhos usam essas coordenadas.", 32)

# 6 doors
slides["doors"] = section("doors", DARK, LIGHT, (
    title("Uma classe, duas portas", 80)
    + '<div style="display:flex;align-items:center;gap:28px">'
    + card(icon("Code", BLUE) + h3("Seu script") + para('p.draw_shape("heart", …)', MUTED_D, 30), True)
    + f'<x-shape kind="arrow-right" style="background:{BLUE};width:88px;height:56px"></x-shape>'
    + f'<div style="flex:1;display:flex;flex-direction:column;gap:16px;background:{ORANGE};padding:44px;border-radius:20px">{icon("Settings", DARK)}{h3("Plotter", DARK, 56)}{para("valida, planeja e move", DARK, 30)}</div>'
    + f'<x-shape kind="arrow-left" style="background:{BLUE};width:88px;height:56px"></x-shape>'
    + card(icon("Chat", BLUE) + h3("LLM via MCP") + para("ferramenta draw_shape", MUTED_D, 30), True)
    + '</div>' + para("O mesmo código desenha nos dois casos. Só muda quem escreve a chamada.", MUTED_D, 40)
), "Não há duas implementações. O servidor MCP só expõe os métodos da classe Plotter como ferramentas.", 64)

# 7 plan
def phase(n: int, name: str, mins: str, text: str) -> str:
    return card(f'<p style="width:88px;height:88px;border-radius:50%;background:{ORANGE};color:{DARK};{H};font-size:52px;text-align:center;line-height:88px">{n}</p>'
                + h3(name, None, 52) + f'<p style="font-size:30px;font-weight:600;color:{DORANGE}">{mins}</p>' + para(text, MUTED_L), False)


slides["plan"] = section("plan", LIGHT, INK, (
    title("A oficina em 3 fases")
    + '<div style="display:flex;gap:32px">'
    + phase(1, "Na mão", "20 min", "Cada grupo escreve o código e o braço desenha.")
    + phase(2, "Com a LLM", "20 min", "O mesmo grupo pede o desenho em português. Mesmo braço.")
    + phase(3, "Apresentação", "20 min", "Cada grupo mostra um desenho e conta como chegou nele.")
    + '</div>'
    + f'<div style="display:flex;height:20px;border-radius:10px;overflow:hidden"><div style="flex:1;background:{ORANGE}"></div><div style="flex:1;background:{BLUE}"></div><div style="flex:1;background:{DORANGE}"></div></div>'
), "Uma hora, com o braço real desde o início. Os braços já estão pré-calibrados e cada grupo tem folhas limpas.", 56)

# 8 rules
slides["rules"] = section("rules", DARK, LIGHT, (
    title("Regras do jogo", 80)
    + '<div style="display:flex;gap:32px">'
    + card(icon("Link", ORANGE) + h3("Um traço só", ORANGE, 52) + para("O braço não levanta a caneta: toda viagem entre formas marca o papel.", MUTED_D, 34), True)
    + card(icon("Search", ORANGE) + h3("Sempre ensaie", ORANGE, 52) + para("dry_run=True mostra tamanho, tempo e um desenho em ASCII antes de mexer o braço.", MUTED_D, 34), True)
    + card(icon("CheckCircle", ORANGE) + h3("Folha limpa", ORANGE, 52) + para("Riscou demais? Troque a folha. O desenho novo precisa de papel limpo.", MUTED_D, 34), True)
    + '</div>'
), "As três regras que já custaram tempo na prática. A primeira é uma limitação do braço; as outras duas são hábitos.", 64)

# 9 hard (phase 1)
slides["hard"] = section("hard", LIGHT, INK, (
    track(1, False) + title("Fase 1: na mão", 76)
    + '<div style="display:flex;gap:32px">'
    + f'<div style="flex:1.4;display:flex;flex-direction:column;gap:20px">'
    + code([("from penarm import Plotter, find_port", 0), ("", 0), ("with Plotter(find_port()) as p:", 0),
            ("p.draw_shape(\"rectangle\", 35, 24, 50, 30)", 1), ("p.draw_arc(100, 12, 20, 0, 180)", 1)], 30)
    + para("Rode com <b>python examples/phase1.py</b>. Troque os números e rode de novo.", MUTED_L, 32) + '</div>'
    + card(h3("Desafios", DORANGE, 44) + "".join(para(t, INK, 32) for t in (
        "1. Um quadrado de 30 mm.", "2. Uma casa: quadrado + triângulo.", "3. Uma estrela com 7 pontas.", "4. Seu desenho, combinando formas.")), False)
    + '</div>'
), "Cada grupo roda o código no braço real, depois muda números e formas. O papel útil tem 175 por 48 mm: tudo precisa caber. Sem levantar a caneta, formas consecutivas se ligam por uma linha.", 40)

# 10 predict / 11 reveal
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
snippet = code([("p.draw_polyline([[10,10],[25,40],[40,10],[55,40]])", 0), ("p.draw_arc(95, 25, 15, 0, 360)", 0)], 30)
slides["predict"] = section("predict", DARK, LIGHT, (
    track(1, True) + title("Antes de rodar: o que vai sair?", 72)
    + snippet
    + f'<div style="display:flex;gap:24px;align-items:center">{icon("Lightbulb", ORANGE, 88)}{para("Desenhe no caderno. Dica: o braço não levanta a caneta.", LIGHT, 44)}</div>'
), "Pausa de 1 minuto. Cada grupo desenha no caderno o que acha que vai sair, antes de mostrar o resultado.", 48)
FIG["reveal"] = (round(175 * kk + 40), round(ph + 40), reveal_inner)
slides["reveal"] = section("reveal", DARK, LIGHT, (
    track(1, True) + title("Saiu isto", 72)
    + svg_wrap(round(175 * kk + 40), round(ph + 40), reveal_inner, "Zigue-zague, linha de ligação e círculo", 1500)
    + para("Zigue-zague, depois a <b>linha de ligação</b> até o círculo: o braço não levantou a caneta.", MUTED_D, 38)
), "Resultado calculado a partir dos pontos reais. A linha reta entre as formas é a viagem do braço.", 36)

# 12 easy (phase 2)
def chip(t: str) -> str:
    return f'<p style="background:{CARD};border:2px solid {EDGE};border-radius:999px;padding:14px 28px;font-size:30px">{t}</p>'


house_inner = (
    f'<rect width="385" height="106" rx="8" fill="{LIGHT}"/><path d="M40 95 L40 50 L75 14 L110 50 L110 95 Z M110 50 L40 50" fill="none" stroke="{DORANGE}" stroke-width="4" stroke-linejoin="round"/>'
               f'<circle cx="290" cy="53" r="30" fill="none" stroke="{DORANGE}" stroke-width="4"/>'
)
FIG["house"] = (385, 106, house_inner)
slides["easy"] = section("easy", DARK, LIGHT, (
    track(2, True) + title("Fase 2: com a LLM", 76)
    + '<div style="display:flex;gap:40px;align-items:center">'
    + f'<div style="flex:1;display:flex;flex-direction:column;gap:36px"><p style="{H};font-size:54px;font-weight:500;line-height:1.2;color:{ORANGE}">“Desenha uma casa com telhado e uma estrela no céu.”</p>'
    + f'<div style="display:flex;gap:14px">{chip("1. canvas_info")}{chip("2. dry_run")}{chip("3. desenha")}</div>'
    + para("A LLM descobre o tamanho do papel, testa o desenho e só então move o braço.", MUTED_D, 34) + '</div>'
    + f'<div style="flex:1;background:{CARD};padding:32px;border:2px solid {EDGE};border-radius:20px">'
    + svg_wrap(385, 106, house_inner, "Casa e estrela", 640)
    + '</div></div>'
), "O mesmo braço, agora sem código. A LLM escolhe as formas, o tamanho e a posição.", 40)

# 13 compare
slides["compare"] = section("compare", LIGHT, INK, (
    title("O mesmo desenho, dois caminhos", 72)
    + '<div style="display:flex;gap:32px">'
    + card(h3("Fase 1: você escolhe cada número", DORANGE, 40)
           + code([("p.draw_polyline([[10,10],[25,40],", 0), ("   [40,10],[55,40]])", 0), ("p.draw_shape(\"star\", cx=100, cy=25,", 0), ("   size=30, sides=7)", 0)], 28)
           + para("Você decide posições, tamanhos e ordem.", MUTED_L, 32), False)
    + card(h3("Fase 2: você descreve a ideia", DORANGE, 40)
           + f'<div style="background:{DARK};padding:40px;border-radius:20px"><p style="font-size:34px;line-height:1.4;color:{LIGHT}">“Um zigue-zague e uma estrela de 7 pontas ao lado. Ensaie antes.”</p></div>'
           + para("A LLM escolhe os números, ensaia e chama os mesmos métodos.", MUTED_L, 32), False)
    + '</div>' + para("O passo criativo mudou de mãos. O braço, o papel e as regras são os mesmos.", INK, 40)
), "Contar linhas e números escolhidos na fase 1 e comparar com a fase 2.", 48)

# 14 prompts
slides["prompts"] = section("prompts", DARK, LIGHT, (
    track(2, True) + title("Ideias de pedido", 72)
    + '<div style="display:flex;gap:28px;flex-wrap:wrap">'
    + "".join(f'<div style="flex:1 1 760px;background:{CARD};border:2px solid {EDGE};border-radius:20px;padding:40px"><p style="{H};font-size:40px;color:{ORANGE}">“{t}”</p></div>' for t in (
        "Um gato de uma linha só.", "Meu nome em letra cursiva, bem grande.", "Uma espiral que termina em estrela.", "Uma paisagem: sol, montanha e rio."))
    + '</div>'
    + para("Se saiu torto, peça ajuste: “maior”, “mais para a esquerda”, “sem a segunda estrela”.", MUTED_D, 36)
), "Cada grupo escolhe um pedido, ou inventa o seu. Pedir sempre para ensaiar antes. Se o desenho sair do papel, o código recusa e a LLM corrige.", 48)

# 15 show (phase 3)
slides["show"] = section("show", ORANGE, DARK, (
    track(3, False) + title("Fase 3: cada grupo apresenta", 76)
    + '<div style="display:flex;gap:32px">'
    + card(icon("Chat", DORANGE) + h3("O que vocês pediram?") + para("Mostrem o prompt e o desenho que saiu no braço.", MUTED_L), False)
    + card(icon("Lightbulb", DORANGE) + h3("O que a LLM fez que vocês não pensariam?") + para("Uma forma, uma posição, uma ideia.", MUTED_L), False)
    + card(icon("Warning", DORANGE) + h3("O que deu errado?") + para("E como vocês corrigiram o pedido.", MUTED_L), False)
    + '</div>'
), "Três minutos por grupo. Pedir que a turma compare o esforço da fase 1 (código) com o da fase 2 (um pedido).", 48)

# 16 wrap
slides["wrap"] = section("wrap", DARK, LIGHT, (
    title("O que o braço mostrou", 80)
    + '<div style="display:flex;flex-direction:column;gap:28px">'
    + "".join(f'<div style="display:flex;gap:28px;align-items:center;background:{CARD};border:2px solid {EDGE};border-radius:20px;padding:36px 44px">'
             f'<p style="flex:none;{H};font-size:64px;color:{ORANGE}">{n}</p><p style="font-size:38px;line-height:1.35">{t}</p></div>'
             for n, t in (("1", "O código é a interface: a LLM chama as mesmas funções que você chamou."),
                          ("2", "A parte criativa (o que desenhar e em quais números) é o que a LLM assume."),
                          ("3", "No mundo físico, regras contam: alcance, papel, uma caneta que não levanta."))) + '</div>'
), "Fechamento. Voltar às duas portas: o mesmo Plotter, dois jeitos de chamar.", 40)

ORDER = ["cover", "what", "anatomy", "angles", "sheet", "doors", "plan", "rules", "hard", "predict", "reveal", "easy", "compare", "prompts", "show", "wrap"]
assert set(ORDER) == set(slides)


def main() -> None:
    (OUT / "slides").mkdir(parents=True, exist_ok=True)
    for sid in ORDER:
        (OUT / "slides" / f"{sid}.html").write_text(slides[sid])
    deck = {"v": 4, "createdOnFiles": {"v": 1, "at": "2026-11-10T15:00:00Z"}, "lists": "css", "title": "Oficina: braço plotter com LLM", "order": ORDER,
            "sections": {"s1": {"description": "A ideia e as peças.", "start": "cover"},
                         "s2": {"description": "Como o braço enxerga o papel.", "start": "anatomy"},
                         "s3": {"description": "A dinâmica e as regras.", "start": "plan"},
                         "s4": {"description": "Fase 1: na mão.", "start": "hard"},
                         "s5": {"description": "Fase 2: com a LLM.", "start": "easy"},
                         "s6": {"description": "Fase 3: apresentações.", "start": "show"}},
            "faces": {"space-grotesk": {"family": "Space Grotesk", "href": "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300..700&display=swap"},
                      "inter": {"family": "Inter", "href": "https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap"}},
            "designSystems": []}
    (OUT / "deck.json").write_text(json.dumps(deck, ensure_ascii=False) + "\n")
    print("wrote", len(ORDER), "slides to", OUT)


if __name__ == "__main__":
    main()
