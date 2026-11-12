"""Helpers to build the workshop deck on the Rec'n'Play template: cloning the template's slides as backgrounds, replacing their
text, code cards, figures (SVG -> PNG with rsvg-convert, brew install librsvg) and one font for every run. Used by
build_dinamica.py. The template path is argv[1], default ~/Downloads/[TEMPLATE] Palestras RNP.pptx."""
import copy
import re
import subprocess
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt


TEMPLATE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Downloads" / "[TEMPLATE] Palestras RNP.pptx"
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


FONT = "Arial"  # the template's DM Sans is embedded only for Google Slides; elsewhere it falls back to a serif, so use a font every machine has
CODE_FONT = "Consolas"


def apply_font(prs) -> None:  # type: ignore[no-untyped-def]
    """Put every text run in FONT (bold where the template used a Black/ExtraBold cut), keeping the code font as is."""
    def runs(shapes):  # type: ignore[no-untyped-def]
        for sh in shapes:
            if sh.shape_type == 6:
                yield from runs(sh.shapes)
            if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
                for p in sh.text_frame.paragraphs:
                    yield from p.runs
            if getattr(sh, "has_table", False) and sh.has_table:
                for row in sh.table.rows:
                    for cell in row.cells:
                        for p in cell.text_frame.paragraphs:
                            yield from p.runs

    for slide in prs.slides:
        for r in runs(slide.shapes):
            if r.font.name == CODE_FONT or r.font.name in ("Courier New", "Courier"):
                r.font.name = CODE_FONT
                continue
            if r.font.name and ("Black" in r.font.name or "ExtraBold" in r.font.name):
                r.font.bold = True
            r.font.name = FONT
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




