"""
build_manual.py
---------------
Render PDF_Studio_Manual.md into a professional reference-manual PDF.

Deliberately a small, purpose-built Markdown subset renderer (headings, tables,
lists, blockquotes, code, inline bold/code/links) rather than a heavyweight
toolchain — keeps the docs build dependency-light (reportlab only) and gives
exact control over the page furniture.
"""
import os
import re

from reportlab.lib import colors
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "..", "src", "fonts")
SRC = os.path.join(HERE, "PDF_Studio_Manual.md")
OUT = os.path.join(HERE, "PDF_Studio_Manual.pdf")

ACCENT = HexColor("#0a5ad6")
INK = HexColor("#141414")
MUTED = HexColor("#5a5a5a")
RULE = HexColor("#c8ccd2")
BAND = HexColor("#eef3fb")
CODE_BG = HexColor("#f4f5f7")
NOTE_BG = HexColor("#fff8e6")
NOTE_BAR = HexColor("#d9a441")

BODY, BOLD = "Helvetica", "Helvetica-Bold"
try:
    pdfmetrics.registerFont(TTFont("Atk", os.path.join(FONT_DIR, "AtkinsonHyperlegible-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Atk-B", os.path.join(FONT_DIR, "AtkinsonHyperlegible-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Atk-I", os.path.join(FONT_DIR, "AtkinsonHyperlegible-Italic.ttf")))
    pdfmetrics.registerFontFamily("Atk", normal="Atk", bold="Atk-B", italic="Atk-I")
    BODY, BOLD = "Atk", "Atk-B"
except Exception as e:
    print("Atkinson not loaded, using Helvetica:", e)

MONO = "Courier"

S = {
    "h1": ParagraphStyle("h1", fontName=BOLD, fontSize=19, leading=24, textColor=ACCENT,
                         spaceBefore=20, spaceAfter=9, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=14, leading=19, textColor=INK,
                         spaceBefore=14, spaceAfter=6, keepWithNext=1),
    "h3": ParagraphStyle("h3", fontName=BOLD, fontSize=12, leading=16, textColor=INK,
                         spaceBefore=10, spaceAfter=4, keepWithNext=1),
    "p": ParagraphStyle("p", fontName=BODY, fontSize=10.5, leading=16, textColor=INK,
                        spaceAfter=7),
    "li": ParagraphStyle("li", fontName=BODY, fontSize=10.5, leading=16, textColor=INK,
                         leftIndent=7 * mm, firstLineIndent=-3.5 * mm, spaceAfter=3),
    "cell": ParagraphStyle("cell", fontName=BODY, fontSize=9.5, leading=13.5, textColor=INK),
    "cellh": ParagraphStyle("cellh", fontName=BOLD, fontSize=9.5, leading=13.5, textColor=INK),
    "code": ParagraphStyle("code", fontName=MONO, fontSize=8.8, leading=12.6, textColor=INK),
    "note": ParagraphStyle("note", fontName=BODY, fontSize=10, leading=15, textColor=INK),
}


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(t):
    """Markdown inline -> reportlab markup."""
    t = esc(t)
    t = re.sub(r"`([^`]+)`",
               r'<font face="%s" size="9.3" backColor="#eef0f3"> \1 </font>' % MONO, t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<link href="\2" color="#0a5ad6">\1</link>', t)
    return t


def code_block(lines):
    txt = "<br/>".join(esc(l).replace(" ", "&nbsp;") for l in lines)
    p = Paragraph(txt, S["code"])
    t = Table([[p]], colWidths=[165 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return [t, Spacer(1, 8)]


def note_block(lines):
    txt = " ".join(lines)
    p = Paragraph(inline(txt), S["note"])
    t = Table([[p]], colWidths=[165 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NOTE_BG),
        ("LINEBEFORE", (0, 0), (0, -1), 3, NOTE_BAR),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [t, Spacer(1, 9)]


def table_block(rows):
    header, body = rows[0], rows[1:]
    ncol = len(header)
    total = 165 * mm
    if ncol == 2:
        widths = [62 * mm, 103 * mm]
    elif ncol == 3:
        widths = [52 * mm, 56 * mm, 57 * mm]
    else:
        widths = [total / ncol] * ncol
    data = [[Paragraph(inline(c), S["cellh"]) for c in header]]
    for r in body:
        r = (r + [""] * ncol)[:ncol]
        data.append([Paragraph(inline(c), S["cell"]) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BAND),
        ("LINEBELOW", (0, 0), (-1, 0), 1.1, ACCENT),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, HexColor("#f7f8fa")]),
    ]))
    return [t, Spacer(1, 10)]


def parse(md):
    story = []
    lines = md.split("\n")
    i = 0
    # Skip the source's own title block + hand-written TOC — the PDF has a cover
    # and its own generated TOC.
    try:
        i = next(n for n, l in enumerate(lines)
                 if l.strip().startswith("## 1. About")) if any(
            l.strip().startswith("## 1. About") for l in lines) else 0
    except StopIteration:
        i = 0

    while i < len(lines):
        ln = lines[i]
        st = ln.strip()

        if not st or st == "---":
            i += 1
            continue

        if st.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            story += code_block(buf)
            continue

        if st.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            story += note_block([b for b in buf if b])
            continue

        if st.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw = lines[i].strip().strip("|")
                cells = [c.strip() for c in raw.split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            if rows:
                story += table_block(rows)
            continue

        if st.startswith("#### "):
            story.append(Paragraph(inline(st[5:]), S["h3"])); i += 1; continue
        if st.startswith("### "):
            story.append(Paragraph(inline(st[4:]), S["h3"])); i += 1; continue
        if st.startswith("## "):
            head = st[3:]
            if re.match(r"^\d+\.", head) and not story == []:
                story.append(Spacer(1, 6))
            story.append(Paragraph(inline(head), S["h1"])); i += 1; continue
        if st.startswith("# "):
            story.append(Paragraph(inline(st[2:]), S["h1"])); i += 1; continue

        m = re.match(r"^(\d+)\.\s+(.*)", st)
        if m:
            story.append(Paragraph(f"<b>{m.group(1)}.</b>&nbsp;&nbsp;{inline(m.group(2))}",
                                   S["li"]))
            i += 1
            continue

        if st.startswith("- ") or st.startswith("* "):
            story.append(Paragraph("•&nbsp;&nbsp;" + inline(st[2:]), S["li"]))
            i += 1
            continue

        # paragraph: gather until blank/structural line
        buf = [st]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith(("#", "|", ">", "```", "- ", "* ", "---"))
                    or re.match(r"^\d+\.\s", nxt)):
                break
            buf.append(nxt)
            i += 1
        story.append(Paragraph(inline(" ".join(buf)), S["p"]))
    return story


def cover():
    s = [Spacer(1, 52 * mm)]
    s.append(Paragraph("PDF&nbsp;Studio",
                       ParagraphStyle("ct", fontName=BOLD, fontSize=40, leading=46,
                                      textColor=INK, spaceAfter=8)))
    s.append(Paragraph("User Manual",
                       ParagraphStyle("cs", fontName=BODY, fontSize=20, leading=26,
                                      textColor=ACCENT, spaceAfter=26)))
    rule = Table([[""]], colWidths=[60 * mm], rowHeights=[2])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT)]))
    s.append(rule)
    s.append(Spacer(1, 20))
    meta = ParagraphStyle("cm", fontName=BODY, fontSize=11.5, leading=19, textColor=MUTED)
    s.append(Paragraph("Version 2.8", meta))
    s.append(Paragraph("A free, full-featured PDF reader and editor", meta))
    s.append(Spacer(1, 14))
    s.append(Paragraph("Leon Priest &nbsp;·&nbsp; github.com/7h3v01d", meta))
    s.append(Paragraph("Apache License 2.0 — free to use, modify, and share", meta))
    s.append(PageBreak())
    return s


def contents_page(md):
    s = [Paragraph("Contents", S["h1"]), Spacer(1, 4)]
    rows = []
    for line in md.split("\n"):
        st = line.strip()
        m = re.match(r"^##\s+(\d+)\.\s+(.*)$", st)
        if m:
            rows.append([m.group(1), inline(m.group(2))])
    data = [[Paragraph(f"<b>{n}</b>", S["cell"]), Paragraph(t, S["cell"])] for n, t in rows]
    t = Table(data, colWidths=[12 * mm, 153 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#e2e5e9")),
    ]))
    s.append(t)
    s.append(PageBreak())
    return s


def _later(canvas, doc):
    canvas.saveState()
    canvas.setFont(BODY, 8.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(22 * mm, 285 * mm, "PDF Studio — User Manual")
    canvas.drawRightString(188 * mm, 285 * mm, "Version 2.8")
    canvas.setStrokeColor(HexColor("#dfe3e8"))
    canvas.line(22 * mm, 282 * mm, 188 * mm, 282 * mm)
    canvas.line(22 * mm, 16 * mm, 188 * mm, 16 * mm)
    canvas.drawCentredString(105 * mm, 11 * mm, str(canvas.getPageNumber()))
    canvas.restoreState()


def _cover_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(ACCENT)
    canvas.rect(0, 287 * mm, 210 * mm, 10 * mm, stroke=0, fill=1)
    canvas.restoreState()


def build():
    md = open(SRC, encoding="utf-8").read()
    doc = BaseDocTemplate(OUT, pagesize=A4,
                          leftMargin=22 * mm, rightMargin=22 * mm,
                          topMargin=26 * mm, bottomMargin=22 * mm,
                          title="PDF Studio - User Manual", author="Leon Priest")
    fr = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[fr], onPage=_cover_page),
        PageTemplate(id="body", frames=[fr], onPage=_later),
    ])
    story = cover()
    story.append(__import__("reportlab.platypus", fromlist=["NextPageTemplate"]).NextPageTemplate("body"))
    story += contents_page(md)
    story += parse(md)
    doc.build(story)
    print("Wrote", OUT)


if __name__ == "__main__":
    build()
