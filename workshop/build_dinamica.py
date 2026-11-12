"""Builds THE workshop deck (Portuguese, one file) on the Rec'n'Play template: the earlier traffic-light session adapted to
the plotter arm, with the hand-drawing phase from the earlier workshop deck. Same structure and the same icon style as the original; the icons live in workshop/icons/.

    python workshop/build_dinamica.py [template.pptx]       # default: ~/Downloads/[TEMPLATE] Palestras RNP.pptx
Writes workshop/dinamica-ia-hardware.pptx. Needs rsvg-convert (brew install librsvg) for the arm illustration."""
import math
import tempfile
import textwrap
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

import pptx_helpers as bp
from pptx_helpers import CREAM, TPL_ORANGE, WINE, caption, clone, code_card, drop, notes, png, put_image, set_text
from figuras import FIG

OUT = Path(__file__).parent / "dinamica-ia-hardware.pptx"
ICONS = Path(__file__).parent / "icons"
CARD, EDGE, INK_DARK, MUTED = "FFFFFF", "EBD9CC", "24121B", "7A5A52"
ROW_A, ROW_B = "FFF0E4", "FFFFFF"


def rgb(h: str) -> RGBColor:
    return RGBColor.from_string(h)


def tb(slide, x: float, y: float, w: float, h: float, paras, size: float = 11, color: str = WINE, bold: bool = False,  # type: ignore[no-untyped-def]
       align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font: str = bp.FONT):
    """Text box. paras: str or list of str; '**x**' makes an orange bold run."""
    import re

    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, text in enumerate([paras] if isinstance(paras, str) else paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(4)
        for chunk in [c for c in re.split(r"(\*\*.+?\*\*)", text) if c]:
            r = p.add_run()
            hot = chunk.startswith("**")
            r.text = chunk.strip("*") if hot else chunk
            r.font.name, r.font.size = font, Pt(size)
            r.font.bold = bold or hot
            r.font.color.rgb = rgb(TPL_ORANGE if hot else color)
    return box


def card(slide, x: float, y: float, w: float, h: float, fill: str = CARD, line: str | None = EDGE):  # type: ignore[no-untyped-def]
    c = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    c.adjustments[0] = 0.07
    c.fill.solid()
    c.fill.fore_color.rgb = rgb(fill)
    if line:
        c.line.color.rgb = rgb(line)
        c.line.width = Pt(0.75)
    else:
        c.line.fill.background()
    c.shadow.inherit = False
    return c


def icon(slide, name: str, cx: float, y: float, w: float) -> float:  # type: ignore[no-untyped-def]
    """Picture centred on cx with width w; returns its height."""
    from PIL import Image

    path = ICONS / f"{name}.png"
    iw, ih = Image.open(path).size
    h = w * ih / iw
    slide.shapes.add_picture(str(path), Inches(cx - w / 2), Inches(y), Inches(w), Inches(h))
    return h


def arrow(slide, x1: float, y1: float, x2: float, y2: float, dashed: bool = False, head: bool = True) -> None:  # type: ignore[no-untyped-def]
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(TPL_ORANGE)
    c.line.width = Pt(1.75)
    ln = c.line._get_or_add_ln()
    if dashed:
        d = ln.makeelement(qn("a:prstDash"), {"val": "dash"})
        ln.append(d)
    if head:
        ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))


def dashed_box(slide, x: float, y: float, w: float, h: float):  # type: ignore[no-untyped-def]
    b = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    b.adjustments[0] = 0.05
    b.fill.background()
    b.line.color.rgb = rgb(TPL_ORANGE)
    b.line.width = Pt(1.25)
    b.line._get_or_add_ln().append(b.line._get_or_add_ln().makeelement(qn("a:prstDash"), {"val": "dash"}))
    b.shadow.inherit = False
    return b


def table(slide, x: float, y: float, widths: list[float], header: list[str], rows: list[list[str]], size: float = 9.5,  # type: ignore[no-untyped-def]
          row_h: float = 0.36, mono: bool = False) -> float:
    shape = slide.shapes.add_table(len(rows) + 1, len(widths), Inches(x), Inches(y), Inches(sum(widths)), Inches(row_h * (len(rows) + 1)))
    tbl = shape.table
    for j, w in enumerate(widths):
        tbl.columns[j].width = Inches(w)
    for i in range(len(rows) + 1):
        tbl.rows[i].height = Inches(row_h)
        for j in range(len(widths)):
            cell = tbl.cell(i, j)
            text = header[j] if i == 0 else rows[i - 1][j]
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(TPL_ORANGE if i == 0 else ROW_A if i % 2 else ROW_B)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            r = tf.paragraphs[0].add_run()
            r.text = text
            r.font.size = Pt(size)
            r.font.name = bp.CODE_FONT if (mono and i > 0) else bp.FONT
            r.font.bold = i == 0
            r.font.color.rgb = rgb("FFFFFF" if i == 0 else WINE)
    return row_h * (len(rows) + 1)


def main() -> None:
    prs = Presentation(str(bp.TEMPLATE))
    tpl = list(prs.slides)
    tmp = Path(tempfile.mkdtemp())
    anatomy = png("anatomy", *FIG["anatomy"], tmp, bg="#FFF6EE")
    reveal = png("reveal", *FIG["reveal"], tmp)

    def base(tag: str, title: str, note: str):  # type: ignore[no-untyped-def]
        """Text-slide background with a small tag, a title and an empty canvas (x 0.66-6.9, y 1.4-5.2)."""
        s = clone(prs, tpl[bp.T_TEXT - 1])
        _, t, b, _logo = list(s.shapes)
        drop(b)
        t.width = Inches(6.4)
        t.top = Inches(0.66)
        set_text(t, [title], size=24 if len(title) <= 26 else 20, bold=True)
        tb(s, 0.66, 0.42, 6, 0.2, tag, size=10, color=TPL_ORANGE, bold=True)
        notes(s, note)
        return s

    def text(tag: str, title: str, body: list[str], note: str, size: float = 13):  # type: ignore[no-untyped-def]
        s = clone(prs, tpl[bp.T_TEXT - 1])
        _, t, b, _logo = list(s.shapes)
        t.width = b.width = Inches(6.4)
        t.top = Inches(0.66)
        b.top, b.height = Inches(1.45), Inches(3.6)
        set_text(t, [title], size=24 if len(title) <= 26 else 20, bold=True)
        set_text(b, body, size=size)
        tb(s, 0.66, 0.42, 6, 0.2, tag, size=10, color=TPL_ORANGE, bold=True)
        notes(s, note)
        return s

    def divider(num: str, title: str, sub: str, note: str) -> None:
        s = clone(prs, tpl[bp.T_TRANS - 1])
        _, box = list(s.shapes)
        set_text(box, [num, title, sub], bold=True)
        for p, sz in zip(box.text_frame.paragraphs, (40, 28, 15)):
            for r in p.runs:
                r.font.size = Pt(sz)
        notes(s, note)

    def panel(s, y: float, paras: list[str], size: float = 14, x: float = 0.66, w: float = 6.2, fill: str = CARD) -> float:  # type: ignore[no-untyped-def]
        """White card sized to its text (estimated from the wrap), with the text inside. Returns the card's bottom edge."""
        cpl = (w - 0.4) * 72 / (size * 0.52)  # characters per line
        lines = sum(max(1, math.ceil(len(p.replace("**", "")) / cpl)) for p in paras)
        h = lines * size * 1.3 / 72 + len(paras) * 0.1 + 0.4
        card(s, x, y, w, h, fill=fill, line=EDGE if fill == CARD else None)
        tb(s, x + 0.2, y + 0.2, w - 0.4, h - 0.3, paras, size=size)
        return y + h

    def wrap(line: str, width: int = 56) -> list[str]:
        return textwrap.wrap(line, width) or [""]

    # 1 cover
    s = clone(prs, tpl[bp.T_COVER - 1])
    _, t, sub = list(s.shapes)
    set_text(t, ["QUANDO A IA SAI DA TELA:", "UM AGENTE QUE DESENHA"], size=28, bold=True)
    t.left, t.top, t.width, t.height = Inches(2.1), Inches(0.55), Inches(6.2), Inches(1.4)
    sub.left, sub.top, sub.width = Inches(2.1), Inches(1.95), Inches(5.8)
    set_text(sub, ["Agentes de IA com hardware: um braço plotter."], size=14)
    people = [("Tiago Barros", ["Principal Technical Manager - LEAP", "Pesquisador e Professor - CESAR School"]),
              ("Henrique \"Mineiro\" Foresti", ["Pesquisador e Professor", "CESAR School"]),
              ("Fernando Carvalho", ["Pesquisador e Professor - CESAR School", "Professor - UPE"]),
              ("João Rietra", ["Mestrando e Pesquisador", "CESAR School"])]
    for i, (name, roles) in enumerate(people):
        tb(s, 0.66 + (i % 2) * 2.75, 3.95 + (i // 2) * 0.62, 2.7, 0.55, [f"**{name}**"] + roles, size=8.5, color=CREAM)
    tb(s, 0.66, 5.3, 5.4, 0.2, "LEAP: Laboratório de Experimentação, Aprendizagem e Performance", size=7, color=CREAM)
    notes(s, "Abertura. Hoje um agente de IA vai controlar um braço físico que desenha um quadrado, de três jeitos. O foco é o que muda quando a IA sai da tela.")

    # 2 agenda
    text("AGENDA", "O QUE VAMOS FAZER HOJE?", [
        "**01 · O que é um agente?** Como um LLM controla hardware sozinho.",
        "**02 · Arquitetura** Os componentes de um agente com hardware.",
        "**03 · Fase 1: na mão** Você escreve o código do quadrado.",
        "**04 · Fase 2: LLM sem abstração** A LLM manda ângulos crus de servo.",
        "**05 · Fase 3: LLM com abstração** A mesma LLM, com as ferramentas do MCP.",
        "**06 · Debate** O mesmo quadrado, três caminhos."],
        "Seis blocos. O desenho é sempre o mesmo, um quadrado, para dar para comparar. Meta: uma hora.", 14)

    # 01 fundamentos
    divider("01", "O que é um agente?", "Autonomia para controlar o hardware.", "Primeiro o conceito, sem hardware.")

    s = base("01 · FUNDAMENTOS", "O QUE É UM AGENTE?", "O modelo roda num servidor. Os clientes (chat, CLI, desktop) falam com ele. Só os clientes que têm acesso ao computador conseguem agir sobre o hardware. Hoje usamos o opencode, um cliente de linha de comando.")
    h = icon(s, "modelo", 1.45, 2.05, 1.05)
    tb(s, 0.65, 2.05 + h + 0.08, 1.6, 0.5, ["**Model**", "LLM Server"], size=11, align=PP_ALIGN.CENTER, color=WINE)
    h = icon(s, "web", 5.3, 1.35, 1.1)
    tb(s, 4.6, 1.35 + h + 0.05, 1.5, 0.5, ["**WEB Client**", "(chat)"], size=10, align=PP_ALIGN.CENTER)
    dashed_box(s, 3.35, 3.0, 3.55, 2.2)
    h = icon(s, "cli", 4.25, 3.2, 1.1)
    tb(s, 3.55, 3.2 + h + 0.05, 1.4, 0.4, ["**CLI Client**", "(opencode)"], size=10, align=PP_ALIGN.CENTER)
    icon(s, "desktop", 5.95, 3.2, 1.1)
    tb(s, 5.3, 3.2 + h + 0.05, 1.3, 0.4, ["**Desktop Client**"], size=10, align=PP_ALIGN.CENTER)
    tb(s, 3.5, 4.9, 3.3, 0.25, "Acesso ao computador", size=10, color=TPL_ORANGE)
    arrow(s, 2.3, 2.6, 3.2, 1.95)
    arrow(s, 2.3, 2.9, 3.5, 3.55)

    s = base("01 · FUNDAMENTOS", "O QUE É UM AGENTE?", "Agente = modelo + ferramentas + laço. As instruções (AGENTS.md) dizem ao modelo como se comportar. No braço: o modelo pensa, chama draw_line, olha o resultado e pensa de novo.")
    for i, (n, ttl, d) in enumerate([("1", "Modelo", "LLM que lê o contexto e decide o próximo passo"),
                                     ("2", "Ferramentas", "O que o agente pode fazer no mundo físico"),
                                     ("3", "Laço", "Pensa, chama uma ferramenta, lê o resultado, pensa de novo")]):
        x = 0.66 + i * 2.1
        card(s, x, 1.5, 1.95, 1.85)
        tb(s, x + 0.15, 1.6, 0.5, 0.4, n, size=20, color=TPL_ORANGE, bold=True)
        tb(s, x + 0.15, 2.1, 1.7, 0.4, ttl, size=13, bold=True)
        tb(s, x + 0.15, 2.5, 1.7, 0.8, d, size=10.5, color=MUTED)
    tb(s, 0.66, 3.7, 6.2, 0.4, "AGENTE = MODELO + FERRAMENTAS + LAÇO", size=16, bold=True)
    tb(s, 0.66, 4.3, 6.2, 0.6, "As **instruções** (AGENTS.md) dizem ao modelo como se comportar.", size=14)

    s = base("01 · FUNDAMENTOS", "AS INSTRUÇÕES: AGENTS.md", "O opencode lê o AGENTS.md ao iniciar. Ele já vem pronto no repositório: tem as regras e uma seção por fase. O aluno diz a fase na primeira mensagem e ela vale até ele citar outra.")
    caption(s, 0.66, 1.4, 6.0, "AGENTS.md (trecho)")
    code_card(s, 0.66, 1.8, 6.2, [
        "# AGENTS.md: workshop", "",
        "You help students in a one-hour workshop where they",
        "draw with a 2-servo pen-plotter arm. Reply in Portuguese.", "",
        "The student starts the session with a stage:",
        "SETUP, FASE 2 or FASE 3. Follow only that section.", "",
        "## Rules (all stages)",
        "- Work in numbered steps, one at a time.",
        "- Ask \"Posso seguir para a etapa N+1?\" and WAIT."], 11.5)

    s = base("01 · FUNDAMENTOS", "POR QUE HARDWARE É DIFERENTE?", "Três palavras para o resto da aula: latência, segurança (aqui, o alcance do braço) e estado físico (a tinta no papel não volta).")
    table(s, 0.66, 1.5, [2.0, 2.5], ["SOFTWARE", "HARDWARE"], [
        ["Desfazer é fácil", "a tinta já está no papel"],
        ["cada pedido leva segundos", "o servo reage em milissegundos"],
        ["tamanho é só um número", "o braço alcança só a folha"],
        ["erro = exceção", "erro = folha riscada"]], size=12, row_h=0.62)
    card(s, 5.35, 1.5, 1.55, 2.5, fill="FFF0E4", line=None)
    tb(s, 5.48, 1.62, 1.3, 0.5, "Três palavras", size=11, bold=True, color=MUTED)
    tb(s, 5.48, 2.2, 1.35, 1.6, ["• Latência", "• Segurança", "• Estado físico"], size=12)

    # 02 arquitetura
    divider("02", "Arquitetura", "Como os componentes estão organizados.", "Cinco componentes, do modelo ao hardware.")

    s = base("02 · ARQUITETURA", "OS COMPONENTES", "Agente: modelo, ferramentas e laço. Ferramenta: o que o agente pode chamar. Gateway: a camada que protege e traduz. Protocolo: as mensagens combinadas. Device: o hardware.")
    cols = [("agente", "Agente", "Modelo que usa ferramentas em laço."),
            ("ferramenta", "Ferramenta", "O que o agente pode chamar."),
            ("gateway", "Gateway", "Abstrai o hardware e confere cada pedido."),
            (None, "Protocolo", "As mensagens combinadas com o hardware."),
            ("device", "Device", "Placa, servos e sensores.")]
    for i, (ic, name, d) in enumerate(cols):
        cx = 0.66 + 0.62 + i * 1.25
        if ic:
            icon(s, ic, cx, 1.85, 0.85)
        else:
            a = s.shapes.add_shape(MSO_SHAPE.LEFT_RIGHT_ARROW, Inches(cx - 0.45), Inches(2.1), Inches(0.9), Inches(0.45))
            a.fill.solid()
            a.fill.fore_color.rgb = rgb(TPL_ORANGE)
            a.line.fill.background()
            a.shadow.inherit = False
        tb(s, cx - 0.62, 3.05, 1.24, 0.3, name, size=12, bold=True, align=PP_ALIGN.CENTER)
        tb(s, cx - 0.6, 3.45, 1.2, 1.4, d, size=10.5, color=MUTED, align=PP_ALIGN.CENTER)

    s = base("02 · ARQUITETURA", "NOSSO CONTEXTO", "O opencode lê o AGENTS.md e chama as ferramentas do servidor MCP penarm. MCP (Model Context Protocol) é um padrão para o agente descobrir e chamar as ferramentas de um programa. O servidor MCP é a única coisa que fala com a placa, pela serial.")
    nodes = [("agente", "opencode\n+ AGENTS.md"), ("ferramenta", "ferramentas\n(MCP penarm)"), ("gateway", "Plotter\n(gateway)"), (None, "serial"), ("braco", "Arduino\n+ braço")]
    for i, (ic, label) in enumerate(nodes):
        cx = 0.66 + 0.62 + i * 1.25
        if ic:
            icon(s, ic, cx, 1.55, 0.85)
        else:
            a = s.shapes.add_shape(MSO_SHAPE.LEFT_RIGHT_ARROW, Inches(cx - 0.45), Inches(1.75), Inches(0.9), Inches(0.45))
            a.fill.solid()
            a.fill.fore_color.rgb = rgb(TPL_ORANGE)
            a.line.fill.background()
            a.shadow.inherit = False
        tb(s, cx - 0.62, 2.6, 1.24, 0.6, label.split("\n"), size=10.5, bold=True, align=PP_ALIGN.CENTER)
        if i < len(nodes) - 1 and ic:
            arrow(s, cx + 0.5, 2.0, cx + 0.78, 2.0)
    panel(s, 3.5, ["**MCP** (Model Context Protocol): um padrão para o agente descobrir e chamar as ferramentas de um programa.",
                   "Um só processo fala com a placa: **o servidor MCP**."], 12, fill="FFF0E4")

    s = base("02 · ARQUITETURA", "COMO IMPLEMENTAMOS", "A folha é pequena de propósito: formas simples e grandes funcionam melhor. O tamanho depende da calibração de cada braço: o canvas_info diz. O Plotter converte cada ponto (x, y) em dois ângulos de servo e recusa o que sai da folha.")
    card(s, 0.66, 1.5, 2.95, 3.3)
    tb(s, 0.9, 1.7, 2.5, 0.4, "A folha", size=16, bold=True)
    tb(s, 0.9, 2.2, 2.55, 2.5, ["O tamanho vem do **canvas_info** (por exemplo, 134 × 48 mm).", "Origem embaixo, à esquerda; x para a direita, y para cima.",
                                "**Um traço só:** o braço não levanta a caneta."], size=12)
    card(s, 3.75, 1.5, 3.15, 3.3, fill=INK_DARK, line=None)
    tb(s, 4.0, 1.7, 2.7, 0.4, "A implementação", size=16, bold=True, color=TPL_ORANGE)
    tb(s, 4.0, 2.2, 2.7, 2.5, ["• Arduino Uno + 2 servos SG90", "• Dois elos de uns 10 cm", "• Cada ponto vira 2 ângulos (cinemática inversa)", "• O Plotter recusa o que sai da folha"], size=12, color=CREAM)

    s = clone(prs, tpl[bp.T_IMG - 1])
    _, t, b, cap, panel_, ph = list(s.shapes)
    drop(cap, ph)
    t.width = Inches(4.5)
    set_text(t, ["O BRAÇO POR DENTRO"], size=24)
    b.width, b.height = Inches(4.45), Inches(3.9)
    set_text(b, ["**1 Ombro:** servo 1 e o primeiro elo.", "**2 Cotovelo:** servo 2 e o segundo elo.", "**3 Ponta:** a caneta, que não levanta."], size=17)
    put_image(s, anatomy, (5.5, 0.45, 4.2, 4.7))
    notes(s, "Vista de cima. θ1 vem do eixo x; θ2 é medido a partir do elo 1. O cotovelo sempre dobra para a esquerda.")

    s = base("02 · ARQUITETURA", "O PROTOCOLO SERIAL (TEXTO)", "Texto simples pela USB, 57600 baud. Cada comando recebe uma resposta. É o que o servidor MCP escreve na porta; na fase 2 a LLM escreve isso, sem o servidor.")
    table(s, 0.66, 1.5, [2.8, 3.4], ["PC ⇒ Arduino", "Resposta"], [
        ["?", "OK penarm 1 ..."],
        ["R", "R adc1 adc2 servo1 servo2"],
        ["A 100 140", "OK (quando chegou)"],
        ["X", "OK (aborta)"],
        ["A 300 300", "ERR angles"]], size=12, mono=True, row_h=0.5)
    tb(s, 0.66, 4.7, 6.2, 0.4, "Se a placa fica muda, o servidor reconecta sozinho.", size=12, color=MUTED)

    # 03 fase 1
    divider("03", "Fase 1: na mão", "Você escreve o código do quadrado.", "Antes do agente, vocês desenham à mão com o mesmo Plotter.")

    s = base("FASE 1 · NA MÃO", "SETUP NO SEU COMPUTADOR", "Montagem, firmware e calibração já estão prontos. A placa precisa estar plugada ANTES do setup.py, que grava a porta e o Python do ambiente no opencode.json. O opencode abre dentro da pasta plotter e fica aberto até o fim.")
    h1 = code_card(s, 0.66, 1.5, 6.2, ["git clone https://github.com/jhlr/plotter", "cd plotter", "python3 setup.py", "opencode"], 14)
    panel(s, 1.5 + h1 + 0.25, ["Plugue **uma** placa USB **antes** do setup.py.", "Windows: **py** no lugar de python3, um comando por linha.",
                               "O opencode fica aberto até o fim, sem reiniciar."], 13, fill="FFF0E4")

    s = base("FASE 1 · NA MÃO", "O PRIMEIRO QUADRADO", "No opencode o aluno cola o prompt de SETUP. O agente confere o simulador e, se a caneta e a folha estiverem no lugar, desenha um quadrado no braço. A fase 1 de verdade vem depois.")
    h1 = code_card(s, 0.66, 1.5, 6.2, ["> SETUP: confira a instalação e", "  desenhe o primeiro quadrado."], 14)
    panel(s, 1.5 + h1 + 0.25, ["O agente confere o simulador, pergunta se a caneta e a folha estão no lugar e desenha.", "Ele pergunta **Posso seguir?** entre as etapas: responda sim."], 13, fill="FFF0E4")

    s = base("FASE 1 · NA MÃO", "REGRAS DO JOGO", "As regras que já custaram tempo na prática. O braço é de baixa resolução: servo SG90 e caneta no vidro dão traço tremido em coisa pequena.")
    panel(s, 1.5, ["**Um traço só:** o braço não levanta a caneta; toda viagem entre formas marca o papel.",
                   "**Sempre ensaie:** dry_run=True mostra tamanho, tempo e um desenho em ASCII antes de mexer o braço.",
                   "**Formas simples e grandes:** poucos cantos, 30 mm ou mais. O braço não tem resolução para detalhes.",
                   "**Folha limpa:** riscou demais? Troque a folha.",
                   "**Parar o braço:** corte a fonte externa de 5 V. Nenhum programa para um movimento em andamento."], 13)

    s = base("FASE 1 · NA MÃO", "O PLOTTER CONFERE CADA PEDIDO", "O Plotter confere cada pedido antes de mexer o braço. Quando o pedido não cabe na folha, ele recusa com uma mensagem que diz o que fazer. É essa mensagem que o agente vai ler depois.")
    h1 = code_card(s, 0.66, 1.5, 6.2, ["p.draw_line(x, y, x + 30, y)   # cabe na folha: desenha", "p.draw_line(0, 0, 500, 0)       # longe demais?"], 11.5)
    code_card(s, 0.66, 1.5 + h1 + 0.25, 6.2, wrap("Unreachable: the drawing's bounding box (0,0)-(500,0) mm does not fit the canvas (134 x 48 mm): shrink it or move it", 56), 11.5)

    s = base("FASE 1 · NA MÃO", "O QUE VAI SAIR?", "Pausa de 1 minuto. Cada grupo desenha no caderno o que acha que vai sair, antes de rodar.")
    h1 = code_card(s, 0.66, 1.5, 6.2, ["p.draw_line(10, 10, 25, 40)", "p.draw_line(25, 40, 40, 10)", "p.draw_line(40, 10, 55, 40)", "p.draw_arc(95, 25, 15, 0, 360)"], 13)
    tb(s, 0.66, 1.5 + h1 + 0.3, 6.2, 1.2, ["Desenhe no caderno antes de rodar.", "Dica: cada linha começa onde a anterior terminou."], size=14)

    s = clone(prs, tpl[bp.T_IMG - 1])
    _, t_, b_, cap_, panel_, ph_ = list(s.shapes)
    drop(cap_, ph_)
    t_.width = Inches(4.5)
    set_text(t_, ["SAIU ISTO"], size=24)
    b_.width, b_.height = Inches(4.45), Inches(3.9)
    set_text(b_, ["Zigue-zague, depois a linha de ligação até o círculo: o braço não levantou a caneta."], size=16)
    put_image(s, reveal, (5.5, 0.45, 4.2, 4.7))
    notes(s, "Resultado calculado a partir dos pontos reais. A linha de ligação aparece porque o braço não levanta a caneta.")

    s = base("FASE 1 · NA MÃO", "FASE 1: SEU TERMINAL", "O opencode ocupa o primeiro terminal. A fase 1 roda num segundo terminal, na pasta plotter, com o ambiente ativado. O p do script é o braço: with Plotter(...) as p.")
    h1 = code_card(s, 0.66, 1.5, 6.2, ["# segundo terminal, na pasta plotter", "source .venv/bin/activate      # Windows: .venv\\Scripts\\activate", "python examples/phase1.py"], 11.5)
    panel(s, 1.5 + h1 + 0.25, ["Abra **examples/phase1.py** no seu editor.", "O **p** é o braço: with Plotter(...) as p.", "Cada rodada desenha o que está no arquivo."], 13, fill="FFF0E4")

    s = base("FASE 1 · NA MÃO", "EXERCÍCIO: O QUADRADO", "Fase à mão. O alvo é o mesmo nas três fases: um quadrado de 30 mm no meio da folha. Dica: cada linha começa onde a anterior terminou.")
    bottom = panel(s, 1.5, ["Sua tarefa: **desenhar um quadrado de 30 mm**, só com draw_line.", "• Em que ordem, para a caneta não levantar?", "• Ensaie com dry_run=True antes.", "• Conte quantas linhas de código você escreveu."], 13)
    code_card(s, 0.66, bottom + 0.25, 6.2, ["p.draw_line(x, y, x + lado, y)", "p.draw_line(x + lado, y, ...)  # continue"], 12)

    # 04 fase 2
    divider("04", "Fase 2: LLM sem abstração", "Só ângulos crus de servo.", "A LLM fala com a placa no protocolo dela, sem o MCP e sem o Plotter.")

    s = base("FASE 2 · SEM ABSTRAÇÃO", "O PROTOCOLO NA PRÁTICA", "raw.py manda linhas do protocolo e mostra a resposta. Não há (x, y), nem milímetros, nem folha: só dois ângulos de servo. E os ângulos dos servos não são os ângulos do braço: cada horn tem seu offset e seu sentido. O script recusa ângulos fora da faixa segura.")
    h1 = code_card(s, 0.66, 1.5, 6.2, ["python examples/raw.py \"R\"", "python examples/raw.py \"A 100 140\"", "", "# R: onde estão os servos   A: vá para esses ângulos"], 11.5)
    panel(s, 1.5 + h1 + 0.25, ["**Sem (x, y). Sem milímetros. Sem folha.**", "Só dois ângulos de servo.", "O ângulo do servo não é o ângulo do braço."], 13, fill="FFF0E4")

    s = base("FASE 2 · SEM ABSTRAÇÃO", "EXERCÍCIO: SEM ABSTRAÇÃO", "No mesmo opencode: o prompt começa com FASE 2 e o agente só usa o raw.py. O alvo é o mesmo quadrado. Deixe errar: o objetivo é sentir o que falta.")
    h1 = code_card(s, 0.66, 1.5, 6.2, ["> FASE 2: desenhe um quadrado."], 14)
    panel(s, 1.5 + h1 + 0.25, ["Sua tarefa: **fazer a LLM desenhar o mesmo quadrado**, sem ajudá-la com contas.", "Observe:", "• Quantos pedidos até sair um quadrado?",
                               "• O que a LLM chutou: ângulos, escala, folha?", "• Onde a caneta caiu?"], 13)

    s = base("FASE 2 · SEM ABSTRAÇÃO", "E A SEGURANÇA?", "Sem abstração ninguém protege a folha: a placa só confere 0 a 180. O raw.py tem uma guarda de ângulos, mas é uma proteção do script, não do modelo. O limite da folha mora no Plotter, uma camada que o modelo não pode mudar. Aqui a separação entre as fases é só um combinado no prompt: um modelo pode escorregar. Parar o braço: cortar a fonte de 5 V.")
    panel(s, 1.5, ["Sem abstração, quem protege a folha? **Só o script.**", "**O prompt não é uma barreira de segurança.** Nesta oficina, ficar longe das ferramentas na fase 2 é só um combinado.",
                   "A segurança que vale fica em uma camada que o modelo **não pode mudar**: o Plotter."], 13)

    # 05 fase 3
    divider("05", "Fase 3: LLM com abstração", "As ferramentas do MCP.", "O mesmo pedido, agora com as ferramentas do Plotter.")

    s = base("FASE 3 · COM ABSTRAÇÃO (MCP)", "O QUE O AGENTE ENXERGA", "O opencode lê o opencode.json só para abrir o servidor. O modelo enxerga o que o servidor publica: o nome de cada ferramenta, os parâmetros, uma descrição em texto e as mensagens de erro. A descrição é o manual que ele lê.")
    caption(s, 0.66, 1.35, 6.2, "O modelo recebe, para cada ferramenta:")
    h1 = code_card(s, 0.66, 1.7, 6.2, ["draw_line(x1, y1, x2, y2, dry_run=false)"] + wrap("Draw a straight line from (x1, y1) to (x2, y2). With no pen-up, the tip first travels to (x1, y1) touching.", 56), 11)
    caption(s, 0.66, 1.7 + h1 + 0.1, 6.2, "E, se o pedido não cabe, uma mensagem que ensina:")
    code_card(s, 0.66, 1.7 + h1 + 0.45, 6.2, wrap("Unreachable: ... does not fit the canvas (134 x 48 mm): shrink it or move it", 56), 11)

    divider("", "COMO MELHORAR?", "Tire o LLM do laço rápido. O Plotter roda o traço: rápido, determinístico, seguro. O LLM escolhe as formas: lento, flexível.", "Ferramentas de alto nível, como draw_shape, deixam o modelo decidir o quê, e o código decide como.")

    s = base("FASE 3 · COM ABSTRAÇÃO (MCP)", "EXERCÍCIO: COM O MCP", "No mesmo opencode: o prompt começa com FASE 3. O alvo é o mesmo quadrado; depois, uma casa. O agente consulta canvas_info e ensaia com dry_run.")
    h1 = code_card(s, 0.66, 1.5, 6.2, ["> FASE 3: desenhe um quadrado."], 14)
    panel(s, 1.5 + h1 + 0.25, ["Sua tarefa: **o mesmo quadrado, agora com as ferramentas**. Depois peça uma casa com telhado.", "Observe:", "• A LLM chamou canvas_info e dry_run sozinha?",
                               "• Quantos pedidos até o quadrado sair?", "• O que ela não precisou saber desta vez?"], 13)

    s = base("FASE 3 · COM ABSTRAÇÃO (MCP)", "LATÊNCIA", "Cada decisão do modelo leva segundos. Cada rodada custa tokens e pode falhar (rede, provedor). O agente não consegue parar um movimento em andamento: quem para o braço é uma pessoa, cortando a fonte de 5 V.")
    bottom = panel(s, 1.5, ["• O modelo leva **segundos** por decisão", "• Um servo reage em **milissegundos**", "• Cada rodada custa tokens e pode **falhar** (rede, Centopeia)"], 14)
    tb(s, 0.66, bottom + 0.3, 6.2, 0.9, ["E se o braço precisar parar **agora**?", "Quem para é **você**: corte a fonte de 5 V."], size=14)

    # 06 debate
    divider("06", "Debate", "O mesmo quadrado, três caminhos.", "Último bloco.")

    s = base("06 · DEBATE", "O MESMO QUADRADO, TRÊS CAMINHOS", "Contar linhas e números escolhidos nas três fases e comparar esforço, erros e o que cada fase exigiu saber.")
    caption(s, 0.66, 1.4, 6.2, "Fase 1: você escolhe cada número", 12)
    h1 = code_card(s, 0.66, 1.75, 6.2, ["p.draw_line(x, y, x + 30, y)", "p.draw_line(x + 30, y, x + 30, y + 30)  # ..."], 11)
    y2 = 1.75 + h1 + 0.15
    caption(s, 0.66, y2, 6.2, "Fase 2: a LLM escolhe ângulos crus", 12)
    h2 = code_card(s, 0.66, y2 + 0.35, 6.2, ["python examples/raw.py \"A 100 140\" \"A 98 120\"  # ..."], 11)
    y3 = y2 + 0.35 + h2 + 0.15
    caption(s, 0.66, y3, 6.2, "Fase 3: você descreve a ideia", 12)
    code_card(s, 0.66, y3 + 0.35, 6.2, ["> FASE 3: desenhe um quadrado."], 11)

    s = base("06 · DEBATE", "DEBATE DOS GRUPOS", "Cada grupo fala por 2 minutos. Fechar com: a abstração é o que torna o hardware pilotável pela LLM.")
    panel(s, 1.5, ["• O que mudou da fase 2 para a fase 3? Contem pedidos e erros.", "• Onde a LLM errou sem abstração, e por quê?", "• O que mais deveria virar ferramenta?",
                   "• Quanto esforço deu cada fase: código, ângulos, uma frase?"], 14)

    # para levar
    s = clone(prs, tpl[bp.T_END - 1])
    _, body, title, _logo = list(s.shapes)
    title.width = Inches(4.6)
    set_text(title, ["PARA LEVAR"], size=22, bold=True)
    body.width, body.height = Inches(4.6), Inches(3.4)
    set_text(body, ["**1.** Agente = modelo + ferramentas + laço.", "**2.** Sem abstração, a LLM precisa saber tudo: ângulos, limites, escala.",
                    "**3.** Segurança fora do modelo.", "**4.** Com o MCP, o LLM escolhe o quê; o sistema executa o como.",
                    "**5.** Erros com mensagens úteis ajudam o agente a se corrigir."], size=14)
    notes(s, "Fechamento: voltar às cinco ideias.")

    divider("", "PERGUNTAS?", "", "Abrir para perguntas.")

    ids = prs.slides._sldIdLst
    for sld in list(ids)[:bp.TEMPLATE_SLIDES]:
        prs.part.drop_rel(sld.rId)
        ids.remove(sld)
    bp.apply_font(prs)
    prs.save(str(OUT))
    print("wrote", OUT, len(prs.slides), "slides")


if __name__ == "__main__":
    main()
