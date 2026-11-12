"""Builds the "IA e hardware" session deck (Portuguese) on the Rec'n'Play template: the earlier traffic-light session,
adapted to the plotter arm. Same structure and the same icon style as the original; the icons live in workshop/icons/.

    python workshop/build_dinamica.py [template.pptx]       # default: ~/Downloads/[TEMPLATE] Palestras RNP.pptx
Writes workshop/dinamica-ia-hardware.pptx. Needs rsvg-convert (brew install librsvg) for the arm illustration."""
import tempfile
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

import build_pptx as bp
from build_pptx import CREAM, TPL_ORANGE, WINE, caption, clone, code_card, drop, notes, png, put_image, set_text
from build_deck import FIG

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

    def base(tag: str, title: str, note: str):  # type: ignore[no-untyped-def]
        """Text-slide background with a small tag, a title and an empty canvas (x 0.66-6.9, y 1.4-5.2)."""
        s = clone(prs, tpl[bp.T_TEXT - 1])
        _, t, b, _logo = list(s.shapes)
        drop(b)
        t.width = Inches(6.4)
        t.top = Inches(0.66)
        set_text(t, [title], size=24 if len(title) <= 26 else 20, bold=True)
        tb(s, 0.66, 0.42, 5, 0.2, tag, size=8, color=TPL_ORANGE, bold=True)
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
        tb(s, 0.66, 0.42, 5, 0.2, tag, size=8, color=TPL_ORANGE, bold=True)
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

    # 1 cover
    s = clone(prs, tpl[bp.T_COVER - 1])
    _, t, sub = list(s.shapes)
    set_text(t, ["QUANDO A IA", "SAI DA TELA:", "UM AGENTE", "QUE DESENHA"], size=28, bold=True)
    t.top, t.width, t.height = Inches(2.35), Inches(5.0), Inches(2.3)
    sub.top, sub.width = Inches(4.75), Inches(5.0)
    set_text(sub, ["Integrando agentes de IA com hardware: um braço plotter."], size=14)
    notes(s, "Abertura. Hoje um agente de IA vai controlar um braço físico que desenha. O foco é o que muda quando a IA sai da tela.")

    # 2 agenda
    text("AGENDA", "O QUE VAMOS FAZER HOJE?", [
        "**01 · O que é um agente?** Como um LLM controla hardware sozinho.",
        "**02 · A arquitetura** Os componentes de um agente com hardware.",
        "**03 · Setup e modo direto** Você desenha, linha por linha.",
        "**04 · LLM sem abstração** A LLM manda ângulos crus de servo.",
        "**05 · LLM com abstração** A mesma LLM, com as ferramentas do MCP.",
        "**06 · Debate** Cada grupo apresenta o que viu."],
        "Seis blocos. Do 03 ao 05 são mão na massa, com o braço real.", 12)

    # 01 fundamentos
    divider("01", "O que é um agente?", "Autonomia para controlar o hardware.", "Primeiro o conceito, sem hardware.")

    s = base("01 · FUNDAMENTOS", "O QUE É UM AGENTE?", "O modelo roda num servidor. Os clientes (chat, CLI, desktop) falam com ele. Só os clientes que têm acesso ao computador conseguem agir sobre o hardware. Hoje usamos o opencode, um cliente de linha de comando.")
    h = icon(s, "modelo", 1.45, 2.05, 1.05)
    tb(s, 0.65, 2.05 + h + 0.08, 1.6, 0.5, ["**Model**", "LLM Server"], size=10, align=PP_ALIGN.CENTER, color=WINE)
    h = icon(s, "web", 5.3, 1.35, 1.1)
    tb(s, 4.6, 1.35 + h + 0.05, 1.5, 0.5, ["**WEB Client**", "(chat)"], size=9, align=PP_ALIGN.CENTER)
    dashed_box(s, 3.35, 3.0, 3.55, 2.2)
    h = icon(s, "cli", 4.25, 3.2, 1.1)
    tb(s, 3.55, 3.2 + h + 0.05, 1.4, 0.4, ["**CLI Client**", "(opencode)"], size=9, align=PP_ALIGN.CENTER)
    icon(s, "desktop", 5.95, 3.2, 1.1)
    tb(s, 5.3, 3.2 + h + 0.05, 1.3, 0.4, ["**Desktop Client**"], size=9, align=PP_ALIGN.CENTER)
    tb(s, 3.5, 4.9, 3.3, 0.25, "Acesso ao computador", size=8, color=TPL_ORANGE)
    arrow(s, 2.3, 2.6, 3.2, 1.95)
    arrow(s, 2.3, 2.9, 3.5, 3.55)

    s = base("01 · FUNDAMENTOS", "O QUE É UM AGENTE?", "Agente = modelo + ferramentas + laço. As instruções (AGENTS.md) dizem ao modelo como se comportar. No braço: o modelo pensa, chama draw_line, olha o resultado e pensa de novo.")
    for i, (n, ttl, d) in enumerate([("1", "Instruções para o Modelo", "LLM que lê o contexto e decide o próximo passo"),
                                     ("2", "Ferramentas", "O que o agente pode fazer no mundo físico"),
                                     ("3", "Laço", "“Pensa” → chama ferramenta → lê o resultado → “pensa” de novo")]):
        x = 0.66 + i * 2.1
        card(s, x, 1.5, 1.95, 1.75)
        tb(s, x + 0.15, 1.62, 0.5, 0.4, n, size=20, color=TPL_ORANGE, bold=True)
        tb(s, x + 0.15, 2.1, 1.7, 0.4, ttl, size=11, bold=True)
        tb(s, x + 0.15, 2.58, 1.7, 0.6, d, size=8.5, color=MUTED)
    tb(s, 0.66, 3.6, 6.2, 0.3, "AGENTE = MODELO + FERRAMENTAS + LAÇO", size=14, bold=True)
    tb(s, 0.66, 4.1, 6.2, 0.5, "As **instruções** (AGENTS.md) dizem ao modelo como se comportar.", size=14)

    s = base("01 · FUNDAMENTOS", "AS INSTRUÇÕES: AGENTS.md", "O opencode lê o AGENTS.md ao iniciar. Ele já vem pronto no repositório: tem as regras e uma seção por fase, e o aluno diz a fase no começo do prompt.")
    caption(s, 0.66, 1.4, 6.0, "AGENTS.md (trecho)")
    code_card(s, 0.66, 1.75, 6.2, [
        "# AGENTS.md: workshop rules", "",
        "You help students in a one-hour workshop where they",
        "draw with a 2-servo pen-plotter arm.", "",
        "The student starts each message with the stage:", "SETUP, FASE 2 or FASE 3. Follow only that section.", "",
        "## Rules (all stages)",
        "- Work in numbered steps, one at a time.",
        "- Ask \"Posso seguir para a etapa N+1?\" and WAIT.",
        "- Do not invent steps. Never flash or calibrate.", "",
        "## FASE 3: with the penarm tools (5 steps)"], 10.5)

    s = base("01 · FUNDAMENTOS", "POR QUE HARDWARE É DIFERENTE?", "Três palavras para o resto da aula: latência, segurança (aqui, o alcance do braço) e estado físico (a tinta no papel não volta).")
    table(s, 0.66, 1.55, [1.8, 2.4], ["SOFTWARE", "HARDWARE"], [
        ["Desfazer é fácil", "a tinta já está no papel"],
        ["esperar 5 s é OK", "o braço só se move quando o traço começa"],
        ["tamanho é só um número", "o braço alcança só 134 × 48 mm"],
        ["erro = exceção", "erro = folha riscada"]], row_h=0.55)
    card(s, 5.0, 1.55, 1.9, 2.4, fill="FFF0E4", line=None)
    tb(s, 5.15, 1.7, 1.65, 0.4, "Três palavras para hoje", size=10, bold=True, color=MUTED)
    tb(s, 5.15, 2.25, 1.65, 1.5, ["• Latência", "• Segurança", "• Estado físico"], size=11)

    # 02 arquitetura
    divider("02", "Arquitetura", "Como os componentes estão organizados.", "Cinco componentes, do modelo ao hardware.")

    s = base("02 · ARQUITETURA", "OS COMPONENTES", "Agente: o modelo com instruções, em laço. Ferramenta: o que o agente pode chamar. Gateway: a camada que protege e traduz. Protocolo: as mensagens combinadas. Device: o hardware.")
    cols = [("agente", "Agente", "Instruções para um LLM, em linguagem natural, que roda em laço e controla o device."),
            ("ferramenta", "Ferramenta", "Comandos que o cliente executa e que dão acesso ao device."),
            ("gateway", "Gateway", "Fica entre a ferramenta e o device: abstrai o hardware e implementa a segurança."),
            (None, "Protocolo", "Conjunto de mensagens com meio físico, sintaxe e semântica definidas."),
            ("device", "Device", "O hardware que age no mundo: placa, atuadores e sensores.")]
    for i, (ic, name, d) in enumerate(cols):
        cx = 0.66 + 0.62 + i * 1.25
        if ic:
            icon(s, ic, cx, 1.95, 0.85)
        else:
            a = s.shapes.add_shape(MSO_SHAPE.LEFT_RIGHT_ARROW, Inches(cx - 0.45), Inches(2.2), Inches(0.9), Inches(0.45))
            a.fill.solid()
            a.fill.fore_color.rgb = rgb(TPL_ORANGE)
            a.line.fill.background()
            a.shadow.inherit = False
        tb(s, cx - 0.6, 3.15, 1.2, 0.3, name, size=10.5, bold=True, align=PP_ALIGN.CENTER)
        tb(s, cx - 0.62, 3.5, 1.24, 1.5, d, size=8.5, color=MUTED, align=PP_ALIGN.CENTER)

    divider("", "O QUE VAMOS FAZER", "Um agente de IA controla um braço que desenha. Como implementamos, e quais restrições e cuidados devemos ter.", "O exemplo desta sessão.")

    s = base("02 · ARQUITETURA", "NOSSO CONTEXTO", "O opencode lê o AGENTS.md e chama as ferramentas do servidor MCP penarm. O servidor é a única coisa que fala com a placa, pela serial. Se dois programas abrirem a porta, o segundo falha.")
    nodes = [("agente", "opencode\n+ AGENTS.md"), ("ferramenta", "ferramentas\n(MCP penarm)"), ("gateway", "Plotter"), (None, "serial"), ("braco", "Arduino\n+ braço")]
    for i, (ic, label) in enumerate(nodes):
        cx = 0.66 + 0.62 + i * 1.25
        if ic:
            icon(s, ic, cx, 1.65, 0.85)
        else:
            a = s.shapes.add_shape(MSO_SHAPE.LEFT_RIGHT_ARROW, Inches(cx - 0.45), Inches(1.85), Inches(0.9), Inches(0.45))
            a.fill.solid()
            a.fill.fore_color.rgb = rgb(TPL_ORANGE)
            a.line.fill.background()
            a.shadow.inherit = False
        tb(s, cx - 0.62, 2.7, 1.24, 0.5, label.split("\n"), size=9.5, bold=True, align=PP_ALIGN.CENTER)
    card(s, 1.0, 3.55, 5.6, 1.15, fill="FFF0E4", line=None)
    tb(s, 1.2, 3.7, 5.2, 0.9, ["Um só processo fala com a placa: **o servidor MCP**.",
                               "O agente só vê as ferramentas: draw_line, draw_shape, canvas_info..."], size=11)

    s = base("02 · ARQUITETURA", "COMO IMPLEMENTAMOS", "A folha é pequena de propósito: formas simples e grandes funcionam melhor. O Plotter converte cada ponto (x, y) em dois ângulos de servo e recusa o que sai da folha.")
    card(s, 0.66, 1.5, 2.9, 3.2)
    tb(s, 0.9, 1.7, 2.5, 0.4, "A folha", size=14, bold=True)
    tb(s, 0.9, 2.2, 2.5, 2.4, ["134 × 48 mm", "Origem embaixo, à esquerda; x para a direita, y para cima.",
                               "**Um traço só:** o braço não levanta a caneta.", "Formas simples e grandes."], size=10.5)
    card(s, 3.75, 1.5, 3.15, 3.2, fill=INK_DARK, line=None)
    tb(s, 4.0, 1.7, 2.7, 0.4, "A implementação", size=14, bold=True, color=TPL_ORANGE)
    tb(s, 4.0, 2.2, 2.7, 2.4, ["• Arduino Uno + 2 servos SG90", "• Ombro: elo de 108 mm", "• Cotovelo: elo de 106 mm",
                               "• Cada ponto vira 2 ângulos (cinemática inversa)", "• O Plotter recusa o que sai da folha"], size=10.5, color=CREAM)

    s = clone(prs, tpl[bp.T_IMG - 1])
    _, t, b, cap, panel, ph = list(s.shapes)
    drop(cap, ph)
    t.width = Inches(4.5)
    set_text(t, ["O BRAÇO POR DENTRO"], size=24)
    b.width, b.height = Inches(4.45), Inches(3.9)
    set_text(b, ["**1 Ombro:** servo 1, elo de 108 mm.", "**2 Cotovelo:** servo 2, elo de 106 mm.", "**3 Ponta:** a caneta, que não levanta."], size=17)
    put_image(s, anatomy, (5.5, 0.45, 4.2, 4.7))
    notes(s, "Vista de cima. θ1 vem do eixo x; θ2 é medido a partir do elo 1. O cotovelo sempre dobra para a esquerda.")

    s = base("02 · ARQUITETURA", "O PROTOCOLO SERIAL (TEXTO)", "Texto simples pela USB, 57600 baud. Cada comando recebe uma resposta. É o que o servidor MCP escreve na porta; o agente nunca vê isso.")
    table(s, 0.66, 1.55, [2.7, 3.5], ["PC ⇒ Arduino", "Resposta"], [
        ["?", "OK penarm 1 adcmax=… boot=…"],
        ["A 100 140  (vá para os ângulos)", "OK  (quando chegou)"],
        ["Q 7 95.5 120 20  (próximo ponto)", "OK <livres>  ou  FULL"],
        ["X  (aborta)", "OK  (segura a pose)"],
        ["comando fora de ordem", "ERR seq <esperado>"]], size=9, mono=True, row_h=0.42)
    tb(s, 0.66, 4.3, 6.2, 0.5, "Se a placa fica muda, o servidor reconecta sozinho e sincroniza a pose.", size=10, color=MUTED)

    # 03 setup e modo direto
    divider("03", "Setup e modo direto", "Você desenha, linha por linha.", "Antes do agente, vocês desenham à mão com o mesmo Plotter.")

    s = base("03 · SETUP E MODO DIRETO", "SETUP: 5 PASSOS", "Montagem e firmware já estão prontos. O setup.py cria o ambiente, instala o penarm e escreve a porta do braço no opencode.json. O opencode precisa abrir dentro da pasta plotter e fica aberto até o fim, sem reiniciar.")
    steps = [("Repositório", "git clone https://github.com/jhlr/plotter && cd plotter"), ("Ambiente Python", "python setup.py  (Windows: py setup.py)"),
             ("Abrir o opencode", "opencode, dentro da pasta (a chave já está no opencode.json)"), ("Primeiro quadrado", "SETUP: confira a instalação e desenhe o primeiro quadrado."),
             ("Vamos rodar", "plugue UMA placa USB antes do setup.py")]
    for i, (a, b2) in enumerate(steps):
        y = 1.5 + i * 0.68
        o = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.66), Inches(y), Inches(0.36), Inches(0.36))
        o.fill.solid()
        o.fill.fore_color.rgb = rgb(TPL_ORANGE)
        o.line.fill.background()
        o.shadow.inherit = False
        o.text_frame.text = str(i + 1)
        r = o.text_frame.paragraphs[0].runs[0]
        r.font.size, r.font.bold, r.font.name = Pt(11), True, bp.FONT
        r.font.color.rgb = rgb("FFFFFF")
        o.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
        tb(s, 1.2, y, 1.9, 0.36, a, size=10.5, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        tb(s, 3.1, y, 3.8, 0.36, b2, size=9, color=MUTED, anchor=MSO_ANCHOR.MIDDLE, font=bp.CODE_FONT)

    s = base("03 · SETUP E MODO DIRETO", "AS CAMADAS, UMA POR UMA", "O Plotter confere cada pedido antes de mexer o braço. Quando o pedido não cabe na folha, ele recusa com uma mensagem que diz o que fazer. É essa mensagem que o agente vai ler depois.")
    h1 = code_card(s, 0.66, 1.5, 6.2, ["p.draw_line(10, 10, 60, 10)      # cabe na folha: desenha", "p.draw_line(0, 0, 500, 0)       # longe demais?"], 11)
    code_card(s, 0.66, 1.5 + h1 + 0.25, 6.2, ["Unreachable: the drawing's bounding box (0,0)-(500,0) mm", "does not fit the canvas (134 x 48 mm): shrink it or move it"], 10.5)

    s = base("03 · SETUP E MODO DIRETO", "EXERCÍCIO: MODO DIRETO", "Fase à mão. Cada grupo escreve as linhas e roda no braço. Dica: cada linha começa onde a anterior terminou, senão a caneta viaja riscando.")
    card(s, 0.66, 1.5, 6.2, 2.1)
    tb(s, 0.9, 1.65, 5.8, 1.9, ["Sua tarefa é **desenhar uma casa com telhado**, só com draw_line:",
                                "• Quais pontos? (a folha tem 134 × 48 mm)", "• Em que ordem, para a caneta não levantar?", "• Ensaie com dry_run=True antes."], size=14)
    h = code_card(s, 0.66, 3.85, 6.2, ["p.draw_line(50, 30, 50, 6)", "p.draw_line(50, 6, 90, 6)   # ... continue"], 11)

    s = base("03 · SETUP E MODO DIRETO", "EXERCÍCIO: MODO DIRETO", "Momento de olhar o resultado e comparar com o plano.")
    card(s, 0.66, 1.5, 6.2, 2.4)
    tb(s, 0.9, 1.65, 5.8, 2.2, ["Observe:", "• Quanto tempo você levou para chegar nos pontos certos?", "• O traço saiu como o planejado?", "• Sobrou risco de viagem?", "• Você leu a mensagem de erro?"], size=14)

    # 04 sem abstração
    divider("04", "LLM sem abstração", "Só ângulos crus de servo.", "A LLM fala com a placa no protocolo dela, sem o MCP e sem o Plotter.")

    s = base("04 · SEM ABSTRAÇÃO", "O PROTOCOLO NA PRÁTICA", "raw.py manda uma linha do protocolo e mostra a resposta. Não há (x, y), nem milímetros, nem folha: só dois ângulos de servo. E os ângulos dos servos não são os ângulos do braço: cada horn tem seu offset e seu sentido.")
    code_card(s, 0.66, 1.5, 6.2, ["python examples/raw.py \"A 100 140\"", "", "# A <servo1> <servo2>   ângulos de 0 a 180", "# OK   quando o braço chegou"], 11)
    card(s, 0.66, 3.2, 6.2, 1.5)
    tb(s, 0.9, 3.35, 5.8, 1.3, ["**Sem (x, y). Sem milímetros. Sem folha.**", "Só dois ângulos de servo.",
                                "E o ângulo do servo não é o ângulo do braço: cada horn tem o seu offset."], size=13)

    s = base("04 · SEM ABSTRAÇÃO", "EXERCÍCIO: SEM ABSTRAÇÃO", "No mesmo opencode: o prompt começa com FASE 2 e o agente só usa o raw.py. Deixe errar: o objetivo é sentir o que falta.")
    h1 = code_card(s, 0.66, 1.5, 6.2, ["> FASE 2: desenhe um quadrado."], 11)
    card(s, 0.66, 1.5 + h1 + 0.2, 6.2, 2.1)
    tb(s, 0.9, 1.5 + h1 + 0.35, 5.8, 1.9, ["Sua tarefa: **fazer a LLM desenhar um quadrado**, sem ajudá-la com contas.", "Observe:", "• Quantos pedidos até sair um quadrado?",
                                            "• O que a LLM chutou: ângulos, escala, folha?", "• Onde a caneta caiu?"], size=12)

    s = base("04 · SEM ABSTRAÇÃO", "E A SEGURANÇA?", "Sem abstração ninguém protege a folha. A placa só confere 0 a 180. O limite da folha mora no Plotter, uma camada que o modelo não pode mudar. O prompt não é uma barreira.")
    code_card(s, 0.66, 1.5, 6.2, ["python examples/raw.py \"A 170 20\"   # a placa aceita: 0 a 180"], 11)
    card(s, 0.66, 2.7, 6.2, 1.9)
    tb(s, 0.9, 2.85, 5.8, 1.7, ["Sem abstração, quem protege a folha? **Ninguém.**", "**O prompt não é uma barreira de segurança.**",
                                "A segurança fica em uma camada que o modelo **não pode mudar**: o Plotter."], size=13)

    # 05 com abstração
    divider("05", "LLM com abstração", "As ferramentas do MCP.", "O mesmo pedido, agora com as ferramentas do Plotter.")

    s = base("05 · COM ABSTRAÇÃO (MCP)", "O QUE O AGENTE ENXERGA: opencode.json", "O arquivo diz ao opencode como abrir o servidor MCP. O agente conhece as ferramentas que ele expõe e mais nada do braço.")
    code_card(s, 0.66, 1.5, 6.2, ["{", "  \"mcp\": {", "    \"penarm\": {", "      \"type\": \"local\",", "      \"command\": [", "        \"python\", \"-c\",", "        \"from penarm.server import main; main()\"", "      ],", "      \"environment\": { \"PENARM_PORT\": \"COM3\" }", "    }", "  }", "}"], 10)
    tb(s, 0.66, 4.75, 6.2, 0.4, "Por que o agente não fala direto com a porta serial?", size=12, color=MUTED)

    # como melhorar
    divider("", "COMO MELHORAR?", "Tire o LLM do laço rápido. O Plotter roda o traço: rápido, determinístico, seguro. O LLM escolhe as formas: lento, flexível.", "Ferramentas de alto nível, como draw_shape, deixam o modelo decidir o quê, e o código decide como.")

    s = base("05 · COM ABSTRAÇÃO (MCP)", "EXERCÍCIO: COM O MCP", "No mesmo opencode: o prompt começa com FASE 3. O grupo só pede o desenho em português. A ferramenta draw_shape tem coração, casa não: o agente precisa combinar linhas. Ele consulta canvas_info e ensaia com dry_run.")
    h1 = code_card(s, 0.66, 1.5, 6.2, ["> FASE 3: desenhe uma casa grande", "  com telhado."], 11)
    card(s, 0.66, 1.5 + h1 + 0.2, 6.2, 2.0)
    tb(s, 0.9, 1.5 + h1 + 0.35, 5.8, 1.8, ["Sua tarefa: **o mesmo pedido, agora com as ferramentas**.", "Observe:", "• A LLM chamou canvas_info e dry_run sozinha?", "• Quantos pedidos até a casa sair?", "• O que ela não precisou saber desta vez?"], size=11.5)

    s = base("05 · COM ABSTRAÇÃO (MCP)", "LATÊNCIA", "Cada decisão do modelo leva segundos. Cada rodada custa tokens e pode falhar (rede, provedor). Para parar o braço na hora existe a ferramenta stop().")
    card(s, 0.66, 1.5, 6.2, 2.0)
    tb(s, 0.9, 1.65, 5.8, 1.8, ["• O modelo leva **segundos** por decisão", "• Um servo reage em **milissegundos**", "• Cada rodada custa tokens e pode **falhar** (rede, Centopeia)"], size=14)
    tb(s, 0.66, 3.85, 6.2, 0.6, "E se o agente precisar parar o braço **agora**?", size=13)

    # 06 debate
    divider("06", "Debate", "Cada grupo apresenta o que viu.", "Último bloco.")

    s = base("06 · DEBATE", "DEBATE DOS GRUPOS", "Cada grupo fala por 2 minutos. Fechar com: a abstração é o que torna o hardware pilotável pela LLM.")
    card(s, 0.66, 1.5, 6.2, 3.2)
    tb(s, 0.9, 1.65, 5.8, 3.0, ["• O que mudou da fase sem abstração para a com abstração? Contem pedidos e erros.",
                                "• Onde a LLM errou sem abstração, e por quê?", "• O que mais deveria virar ferramenta?",
                                "• Quanto esforço deu cada fase: código, ângulos, uma frase?"], size=13)

    # para levar
    s = clone(prs, tpl[bp.T_END - 1])
    _, body, title, _logo = list(s.shapes)
    title.width = Inches(4.6)
    set_text(title, ["PARA LEVAR"], size=22, bold=True)
    body.width, body.height = Inches(4.6), Inches(3.4)
    set_text(body, ["**1.** Agente = modelo + ferramentas + laço.", "**2.** Sem abstração, a LLM precisa saber tudo: ângulos, limites, escala.",
                    "**3.** Segurança fora do modelo.", "**4.** Com o MCP, o LLM escolhe o quê; o sistema executa o como.",
                    "**5.** Erros com mensagens úteis ajudam o agente a se corrigir."], size=13)
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
