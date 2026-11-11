"""Builds the workshop deck as a .pptx on the Rec'n'Play template (Portuguese).
Backgrounds come from the template's own slides; the arm figures are the SAME drawings as build_deck.py (computed from the
real arm geometry) rendered to PNG with rsvg-convert (brew install librsvg).

    python workshop/build_pptx.py [template.pptx]        # default: ~/Downloads/[TEMPLATE] Palestras RNP.pptx
Writes workshop/oficina-braco-plotter.pptx."""
import copy
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

from build_deck import arm, BLUE, CARD, DARK, DORANGE, EDGE, FIG, INK, LIGHT, MUTED_L, ORANGE, angle_poses, label

TEMPLATE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Downloads" / "[TEMPLATE] Palestras RNP.pptx"
OUT = Path(__file__).parent / "oficina-braco-plotter.pptx"
CREAM, WINE, TPL_ORANGE = "FFF6EE", "440019", "FF5000"
# template slides (1-based) used as backgrounds
T_COVER, T_TRANS, T_IMG, T_TEXT, T_END = 2, 3, 4, 5, 11
TEMPLATE_SLIDES = 14


# ---------- figures: SVG -> PNG on a cream card ----------
def png(name: str, w: int, h: int, inner: str, tmp: Path, pad: int = 28, bg: str = f"#{CREAM}") -> Path:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w + 2 * pad}" height="{h + 2 * pad}" viewBox="0 0 {w + 2 * pad} {h + 2 * pad}">'
           f'<rect width="{w + 2 * pad}" height="{h + 2 * pad}" rx="22" fill="{bg}"/><g transform="translate({pad},{pad})">{inner}</g></svg>')
    out = tmp / f"{name}.png"
    subprocess.run(["rsvg-convert", "-f", "png", "-w", str((w + 2 * pad) * 2), "-o", str(out)], input=svg.encode(), check=True)
    return out


def chain_vertical() -> tuple[int, int, str]:
    """computer -> board -> arm, stacked, cut from the horizontal chain figure."""
    inner = FIG["chain"][2]

    def crop(x: int, y: int, w: int, h: int, at_x: int, at_y: int) -> str:
        return f'<svg x="{at_x}" y="{at_y}" width="{w}" height="{h}" viewBox="{x} {y} {w} {h}">{inner}</svg>'

    def down(y: int, text: str) -> str:
        return (f'<line x1="200" y1="{y}" x2="200" y2="{y + 52}" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>'
                f'<polygon points="200,{y + 70} 185,{y + 44} 215,{y + 44}" fill="{INK}"/>' + label(222, y + 40, text, MUTED_L, 26))

    arm_svg, _, _ = arm((50, 730), 40, -35, 1.5)
    body = (crop(120, 30, 320, 200, 20, 0) + down(205, "USB: ângulos")
            + crop(690, 60, 280, 190, 40, 270) + down(450, "2 servos") + arm_svg)
    return 400, 760, body


def doors() -> tuple[int, int, str]:
    def box(y: int, text: str, fill: str, fg: str, h: int = 100) -> str:
        return (f'<rect x="40" y="{y}" width="320" height="{h}" rx="16" fill="{fill}"/>'
                + label(200, y + h / 2 + 11, text, fg, 34, "middle"))

    def arrow(y0: int, y1: int) -> str:
        d = 1 if y1 > y0 else -1
        return (f'<line x1="200" y1="{y0}" x2="200" y2="{y1 - 16 * d}" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>'
                f'<polygon points="200,{y1} 186,{y1 - 26 * d} 214,{y1 - 26 * d}" fill="{INK}"/>')

    body = (box(0, "Seu script", CARD, LIGHT) + arrow(100, 170) + box(170, "Plotter", ORANGE, DARK, 130)
            + arrow(430, 300) + box(430, "LLM via MCP", CARD, LIGHT))
    return 400, 530, body


def angles() -> tuple[int, int, str]:
    parts, x = [], 0
    for w, h, inner, (px, py), (t1, t2) in angle_poses:
        parts.append(f'<svg x="{x}" y="0" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{inner}</svg>'
                     + label(x + w / 2, h + 38, f"({px}, {py}) mm", INK, 26, "middle")
                     + label(x + w / 2, h + 76, f"θ1 {t1:.0f}°  θ2 {t2:.0f}°", DORANGE, 28, "middle"))
        x += w + 24
    return x - 24, angle_poses[0][1] + 90, "".join(parts)


# ---------- slide cloning and text editing ----------
def clone(prs: Presentation, src):  # type: ignore[no-untyped-def]
    dst = prs.slides.add_slide(src.slide_layout)
    for sh in list(dst.shapes):
        sh._element.getparent().remove(sh._element)
    rid = {k: dst.part.relate_to(r.target_part, r.reltype) for k, r in src.part.rels.items() if r.reltype.endswith("/image")}
    for sh in src.shapes:
        el = copy.deepcopy(sh._element)
        for node in el.iter():
            for k, v in list(node.attrib.items()):
                if k.endswith("}embed") and v in rid:
                    node.set(k, rid[v])
        dst.shapes._spTree.append(el)
    return dst


def set_text(shape, paragraphs: list[str], size: float | None = None, font: str | None = None, color: str | None = None, align=None, bold: bool = False) -> None:  # type: ignore[no-untyped-def]
    """Replace a text box's text keeping its first run's formatting. **x** makes a bold orange run."""
    tf = shape.text_frame
    p0 = tf.paragraphs[0]._p
    proto_p = copy.deepcopy(p0)
    for p in list(tf.paragraphs)[1:]:
        p._p.getparent().remove(p._p)
    proto_r = proto_p.findall("{http://schemas.openxmlformats.org/drawingml/2006/main}r")[0]
    for i, text in enumerate(paragraphs):
        p_el = p0 if i == 0 else copy.deepcopy(proto_p)
        if i:
            p0.getparent().append(p_el)
        for r in p_el.findall("{http://schemas.openxmlformats.org/drawingml/2006/main}r") + p_el.findall("{http://schemas.openxmlformats.org/drawingml/2006/main}br"):
            p_el.remove(r)
        end = p_el.find("{http://schemas.openxmlformats.org/drawingml/2006/main}endParaRPr")
        for chunk in [c for c in re.split(r"(\*\*.+?\*\*)", text) if c]:
            r = copy.deepcopy(proto_r)
            bold = chunk.startswith("**")
            r.find("{http://schemas.openxmlformats.org/drawingml/2006/main}t").text = chunk.strip("*") if bold else chunk
            if end is not None:
                end.addprevious(r)
            else:
                p_el.append(r)
            rpr = r.find("{http://schemas.openxmlformats.org/drawingml/2006/main}rPr")
            if rpr is not None and bold:
                rpr.set("b", "1")
    for p in tf.paragraphs:
        if align is not None:
            p.alignment = align
        p.space_after = Pt(6)
        for r in p.runs:
            if bold:
                r.font.bold = True
            if size:
                r.font.size = Pt(size)
            if font:
                r.font.name = font
            is_bold = r._r.find("{http://schemas.openxmlformats.org/drawingml/2006/main}rPr") is not None and r._r.find("{http://schemas.openxmlformats.org/drawingml/2006/main}rPr").get("b") == "1"
            if color:
                r.font.color.rgb = RGBColor.from_string(color)
            elif is_bold:
                r.font.color.rgb = RGBColor.from_string(TPL_ORANGE)


def drop(*shapes) -> None:  # type: ignore[no-untyped-def]
    for sh in shapes:
        sh._element.getparent().remove(sh._element)


def put_image(slide, path: Path, box: tuple[float, float, float, float]) -> None:  # type: ignore[no-untyped-def]
    """Fit the picture inside box (x, y, w, h in inches), centred."""
    from PIL import Image

    iw, ih = Image.open(path).size
    bx, by, bw, bh = box
    k = min(bw / iw, bh / ih)
    w, h = iw * k, ih * k
    slide.shapes.add_picture(str(path), Inches(bx + (bw - w) / 2), Inches(by + (bh - h) / 2), Inches(w), Inches(h))


def notes(slide, text: str) -> None:  # type: ignore[no-untyped-def]
    slide.notes_slide.notes_text_frame.text = text


CODE_FONT = "Courier New"
CODE_BG, CODE_FG = "24121B", "FFF6EE"


def code_card(slide, x: float, y: float, w: float, lines: list[str], size: float = 11.5, font: str = CODE_FONT) -> float:  # type: ignore[no-untyped-def]
    """Dark rounded card with light monospace text. Returns its height in inches."""
    h = (size * 1.45 / 72) * len(lines) + 0.4
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    card.adjustments[0] = 0.06
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor.from_string(CODE_BG)
    card.line.fill.background()
    card.shadow.inherit = False
    tf = card.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.2)
    for i, line in enumerate(lines):
        par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        par.alignment = PP_ALIGN.LEFT
        run = par.add_run()
        run.text = line or " "
        run.font.name, run.font.size = font, Pt(size)
        run.font.color.rgb = RGBColor.from_string(CODE_FG)
    return h


def caption(slide, x: float, y: float, w: float, text: str, size: float = 15) -> None:  # type: ignore[no-untyped-def]
    run = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.35)).text_frame.paragraphs[0].add_run()
    run.text = text
    run.font.name, run.font.size, run.font.bold = "DM Sans", Pt(size), True
    run.font.color.rgb = RGBColor.from_string(TPL_ORANGE)


def main() -> None:
    prs = Presentation(str(TEMPLATE))
    tpl = list(prs.slides)
    tmp = Path(tempfile.mkdtemp())
    img = {
        "chain": png("chain", *chain_vertical(), tmp), "anatomy": png("anatomy", *FIG["anatomy"], tmp, bg="#FFF6EE"),
        "angles": png("angles", *angles(), tmp), "sheet": png("sheet", *FIG["sheet"], tmp), "doors": png("doors", *doors(), tmp),
        "reveal": png("reveal", *FIG["reveal"], tmp), "house": png("house", *FIG["house"], tmp),
    }
    PANEL = (5.5, 0.45, 4.2, 4.7)

    def image_slide(title: str, body: list[str], figure: str | None, note: str, size: float = 14, code_lines: list[str] | None = None):  # type: ignore[no-untyped-def]
        s = clone(prs, tpl[T_IMG - 1])
        _, t, b, cap, panel, ph = list(s.shapes)
        drop(cap, ph)
        t.width = Inches(4.5)
        set_text(t, [title], size=28 if len(title) <= 14 else 24 if len(title) <= 18 else 21)
        b.width = Inches(4.45)
        b.height = Inches(3.9)
        set_text(b, body, size=size)
        if code_lines:  # code on a dark card, the prose goes below it
            b.top = Inches(1.45 + code_card(s, 0.55, 1.45, 4.65, code_lines) + 0.2)
        if figure:
            put_image(s, img[figure], PANEL)
        notes(s, note)
        return s, panel

    def text_slide(title: str, body: list[str], note: str, size: float = 15):  # type: ignore[no-untyped-def]
        s = clone(prs, tpl[T_TEXT - 1])
        _, t, b, _logo = list(s.shapes)
        t.width = Inches(6.6)
        set_text(t, [title], size=26 if len(title) <= 24 else 22, bold=True)
        b.width = Inches(6.6)
        b.height = Inches(3.2)
        set_text(b, body, size=size)
        notes(s, note)
        return s

    def transition(top: str, sub: str, note: str) -> None:
        s = clone(prs, tpl[T_TRANS - 1])
        _, box = list(s.shapes)
        set_text(box, [top, sub], bold=True)
        ps = box.text_frame.paragraphs
        for p, sz in zip(ps, (42, 24)):
            for r in p.runs:
                r.font.size = Pt(sz)
        notes(s, note)

    # 1 cover
    s = clone(prs, tpl[T_COVER - 1])
    _, t, sub = list(s.shapes)
    set_text(t, ["UM BRAÇO,", "DOIS SERVOS,", "UMA LLM"], size=34, bold=True)
    t.top, t.width, t.height = Inches(2.6), Inches(5.4), Inches(1.9)
    sub.top, sub.width = Inches(4.55), Inches(4.6)
    set_text(sub, ["Oficina Arduino + MCP: primeiro na mão, depois com a IA."], size=16)
    notes(s, "Abertura. O mesmo braço desenha de dois jeitos: escrevendo código ou pedindo em português. No fim, comparamos o esforço.")
    # 2-6 how the arm works
    image_slide("TRÊS PEÇAS", ["**Software**", "Python + MCP planejam o traço.", "**Placa**", "Arduino Uno: recebe os ângulos pela USB.", "**Braço**", "2 elos e 2 servos SG90 desenham."], "chain",
                "Três peças em cadeia. O software (a classe Plotter) planeja o traço; você chama no Python ou a LLM chama como ferramenta. Os braços já estão montados e calibrados antes da aula.", 20)
    image_slide("ANATOMIA DO BRAÇO", ["**1 Ombro:** servo 1, elo de 108 mm.", "**2 Cotovelo:** servo 2, elo de 106 mm.", "**3 Ponta:** a caneta, que não levanta.", "Cada ponto (x, y) vira **dois ângulos**: o Plotter calcula (cinemática inversa)."], "anatomy",
                "Vista de cima. O ângulo θ1 vem do eixo x; θ2 é medido a partir do elo 1. O cotovelo sempre dobra para a esquerda. O Plotter converte cada ponto do papel em um par de ângulos (ik em kinematics.py) e o Arduino gira os servos.", 17)
    image_slide("A FOLHA", ["Origem no canto inferior esquerdo do retângulo útil. x vai para a direita, y para cima, em mm.",
                           "**Retângulo laranja:** o que o braço alcança por inteiro, hoje 175 × 48 mm. Fora dele, o código recusa.",
                           "**Círculo azul:** o alcance máximo, 214 mm."], "sheet",
                "Todos os desenhos usam essas coordenadas. p.canvas.w e p.canvas.h dão o tamanho na hora.", 13)
    # 7-8 dynamics and rules
    text_slide("A OFICINA EM 3 FASES", ["**1 · Na mão (20 min):** cada grupo escreve o código e o braço desenha.",
                                       "**2 · Com a LLM (20 min):** o mesmo grupo pede o desenho em português, no mesmo braço.",
                                       "**3 · Apresentação (20 min):** cada grupo mostra um desenho e conta como chegou nele."],
               "Uma hora, com o braço real desde o início. Todos os braços já estão calibrados.")
    text_slide("REGRAS DO JOGO", ["**Um traço só:** o braço não levanta a caneta; toda viagem entre formas marca o papel.",
                                 "**Sempre ensaie:** dry_run=True mostra tamanho, tempo e um desenho em ASCII antes de mexer o braço.",
                                 "**Formas simples e grandes:** o braço não tem resolução para detalhes. Poucos cantos, 30 mm ou mais.",
                                 "**Folha limpa:** riscou demais? Troque a folha."],
               "As regras que já custaram tempo na prática. O braço é de baixa resolução: servo SG90 e caneta no vidro dão traço tremido em coisa pequena.")
    # phase 1
    s, panel = image_slide("FASE 1: NA MÃO", ["Rode: python examples/phase1.py", "Da mais simples à mais rica."], None,
                           "Cada grupo roda o código, depois muda números e formas. O papel útil tem 175 por 48 mm: tudo precisa caber.", 15,
                           code_lines=["with Plotter(find_port()) as p:", "  # 1 reta", "  p.draw_line(10, 10, 60, 10)", "  # 2 uma reta depois da outra", "  p.draw_line(60, 10, 60, 40)", "  p.draw_line(60, 40, 10, 40)", "  # 3 arco", "  p.draw_arc(100, 24, 20, 0, 180)", "  # 4 forma pronta", "  p.draw_shape(\"triangle\", 100, 24, 36)"])
    tb = s.shapes.add_textbox(Inches(5.6), Inches(0.8), Inches(4.0), Inches(4.0))
    set_text_new = tb.text_frame
    set_text_new.word_wrap = True
    for i, line in enumerate(["DESAFIOS", "1. Uma reta de 40 mm.", "2. Um quadrado só com draw_line.", "3. Um triângulo grande.", "4. Uma casa com telhado, num traço só."]):
        p = set_text_new.paragraphs[0] if i == 0 else set_text_new.add_paragraph()
        r = p.add_run()
        r.text = line
        r.font.name = "DM Sans ExtraBold" if i == 0 else "DM Sans"
        r.font.bold = i == 0
        r.font.size = Pt(26 if i == 0 else 18)
        r.font.color.rgb = RGBColor.from_string(CREAM)
        p.space_after = Pt(12)
    s, panel = image_slide("O QUE VAI SAIR?", ["Desenhe no caderno antes de rodar.", "Dica: cada linha começa onde a anterior terminou."], None,
                           "Pausa de 1 minuto. Cada grupo desenha no caderno o que acha que vai sair.", 16,
                           code_lines=["p.draw_line(10, 10, 25, 40)", "p.draw_line(25, 40, 40, 10)", "p.draw_line(40, 10, 55, 40)", "p.draw_arc(95, 25, 15, 0, 360)"])
    q = s.shapes.add_textbox(Inches(5.3), Inches(1.0), Inches(4.5), Inches(3.5))
    p = q.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = "?"
    r.font.name, r.font.size, r.font.bold = "DM Sans Black", Pt(200), True
    r.font.color.rgb = RGBColor.from_string(CREAM)
    image_slide("SAIU ISTO", ["Zigue-zague, depois a linha de ligação até o círculo: o braço não levantou a caneta."], "reveal",
                "Resultado calculado a partir dos pontos reais.", 15)
    # phase 2
    image_slide("FASE 2: COM A LLM", ["**“Desenha uma casa grande com telhado.”**", "**Ideias simples:** um coração, uma casa, um sol (círculo com raios), uma seta.",
                                     "Saiu torto? Peça ajuste: “maior”, “mais para a esquerda”."], "house",
                "A LLM escolhe as formas, o tamanho e a posição.", 14)
    s = clone(prs, tpl[T_TEXT - 1])
    _, t, b, _logo = list(s.shapes)
    t.width = Inches(6.6)
    set_text(t, ["O MESMO DESENHO, DOIS CAMINHOS"], size=22, bold=True)
    t.top = Inches(0.7)
    caption(s, 0.66, 1.6, 6.5, "Fase 1: você escolhe cada número")
    h1 = code_card(s, 0.66, 1.98, 6.4, ["p.draw_line(10, 10, 25, 40); p.draw_line(25, 40, 40, 10)", "p.draw_shape(\"triangle\", cx=100, cy=24, size=36)"], 11)
    y2 = 1.98 + h1 + 0.2
    caption(s, 0.66, y2, 6.5, "Fase 2: você descreve a ideia")
    h2 = code_card(s, 0.66, y2 + 0.38, 6.4, ["“Um zigue-zague e um triângulo grande ao lado. Ensaie antes.”"], 12, "DM Sans")
    b.top, b.width, b.height = Inches(y2 + 0.38 + h2 + 0.15), Inches(6.4), Inches(0.8)
    set_text(b, ["O passo criativo mudou de mãos. O braço, o papel e as regras são os mesmos."], size=14)
    notes(s, "Contar linhas e números escolhidos na fase 1 e comparar com a fase 2.")
    # phase 3
    text_slide("CADA GRUPO APRESENTA", ["**O que vocês pediram?** Mostrem o prompt e o desenho que saiu no braço.",
                                       "**O que a LLM fez que vocês não pensariam?** Uma forma, uma posição, uma ideia.",
                                       "**O que deu errado?** E como vocês corrigiram o pedido."],
               "Pedir que a turma compare o esforço da fase 1 (código) com o da fase 2 (um pedido).")
    # close
    s = clone(prs, tpl[T_END - 1])
    _, body, title, _logo = list(s.shapes)
    title.width = Inches(4.6)
    set_text(title, ["O QUE O BRAÇO MOSTROU"], size=22, bold=True)
    body.width = Inches(4.6)
    body.height = Inches(3.2)
    set_text(body, ["**1.** O código é a interface: a LLM chama as mesmas funções que você chamou.",
                    "**2.** A parte criativa, o que desenhar e em quais números, é o que a LLM assume.",
                    "**3.** No mundo físico, regras contam: alcance, papel, uma caneta que não levanta."], size=14)
    notes(s, "Fechamento. Voltar às duas portas: o mesmo Plotter, dois jeitos de chamar.")

    ids = prs.slides._sldIdLst
    for sld in list(ids)[:TEMPLATE_SLIDES]:
        prs.part.drop_rel(sld.rId)
        ids.remove(sld)
    prs.save(str(OUT))
    print("wrote", OUT, len(prs.slides), "slides")


if __name__ == "__main__":
    main()
