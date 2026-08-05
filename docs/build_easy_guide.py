"""
build_easy_guide.py
-------------------
Render the large-print "Easy Guide" PDF for a low-vision reader.

Design choices (deliberate, for macular degeneration):
  * Atkinson Hyperlegible throughout (designed for low vision)
  * 16pt body, 15pt tables, generous leading (~1.55x) and paragraph spacing
  * Pure black on white — maximum contrast
  * Short line length; no multi-column; no italics for emphasis (bold only)
  * Wide margins so the eye can find the start of each line
"""
import os

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle, KeepTogether)

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "..", "src", "fonts")
OUT = os.path.join(HERE, "PDF_Studio_Easy_Guide.pdf")

ACCENT = HexColor("#0a5ad6")   # same blue family as the app's light theme
RULE = HexColor("#9a9a9a")
BAND = HexColor("#eef3fb")

# ── Fonts ────────────────────────────────────────────────────────────────────
BODY_FONT, BOLD_FONT = "Helvetica", "Helvetica-Bold"
try:
    pdfmetrics.registerFont(
        TTFont("Atkinson", os.path.join(FONT_DIR, "AtkinsonHyperlegible-Regular.ttf")))
    pdfmetrics.registerFont(
        TTFont("Atkinson-Bold", os.path.join(FONT_DIR, "AtkinsonHyperlegible-Bold.ttf")))
    BODY_FONT, BOLD_FONT = "Atkinson", "Atkinson-Bold"
except Exception as e:  # fall back to a built-in face rather than fail
    print("Atkinson font not loaded, using Helvetica:", e)

# ── Styles — large print ─────────────────────────────────────────────────────
S_TITLE = ParagraphStyle("t", fontName=BOLD_FONT, fontSize=30, leading=36,
                         textColor=black, spaceAfter=6)
S_SUB = ParagraphStyle("s", fontName=BODY_FONT, fontSize=16, leading=24,
                       textColor=HexColor("#333333"), spaceAfter=20)
S_H1 = ParagraphStyle("h1", fontName=BOLD_FONT, fontSize=22, leading=28,
                      textColor=ACCENT, spaceBefore=22, spaceAfter=10,
                      keepWithNext=1)
S_H2 = ParagraphStyle("h2", fontName=BOLD_FONT, fontSize=17, leading=23,
                      textColor=black, spaceBefore=14, spaceAfter=6,
                      keepWithNext=1)
S_BODY = ParagraphStyle("b", fontName=BODY_FONT, fontSize=16, leading=25,
                        textColor=black, alignment=TA_LEFT, spaceAfter=10)
S_STEP = ParagraphStyle("step", parent=S_BODY, leftIndent=10 * mm,
                        firstLineIndent=-6 * mm, spaceAfter=8)
S_BULLET = ParagraphStyle("bul", parent=S_BODY, leftIndent=8 * mm,
                          firstLineIndent=-4 * mm, spaceAfter=7)
S_TIP = ParagraphStyle("tip", parent=S_BODY, fontSize=15, leading=23,
                       leftIndent=6 * mm, rightIndent=4 * mm,
                       spaceBefore=4, spaceAfter=10)
S_CELL = ParagraphStyle("c", fontName=BODY_FONT, fontSize=15, leading=21,
                        textColor=black)
S_CELLB = ParagraphStyle("cb", fontName=BOLD_FONT, fontSize=15, leading=21,
                         textColor=black)


def H1(t): return Paragraph(t, S_H1)
def H2(t): return Paragraph(t, S_H2)
def P(t): return Paragraph(t, S_BODY)
def STEP(n, t): return Paragraph(f"<b>{n}.</b>&nbsp;&nbsp;{t}", S_STEP)
def BUL(t): return Paragraph(f"•&nbsp;&nbsp;{t}", S_BULLET)


def TIP(t):
    tbl = Table([[Paragraph(t, S_TIP)]], colWidths=[150 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
    ]))
    return tbl


def TWOCOL(rows, w1=72 * mm, w2=78 * mm, header=None):
    data = []
    if header:
        data.append([Paragraph(f"<b>{header[0]}</b>", S_CELLB),
                     Paragraph(f"<b>{header[1]}</b>", S_CELLB)])
    for a, b in rows:
        data.append([Paragraph(a, S_CELL), Paragraph(b, S_CELL)])
    t = Table(data, colWidths=[w1, w2], repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, RULE),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [white, HexColor("#f5f7fa")]),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), BAND),
                  ("LINEBELOW", (0, 0), (-1, 0), 1.2, ACCENT)]
    t.setStyle(TableStyle(style))
    return t


def _page(canvas, doc):
    canvas.saveState()
    canvas.setFont(BODY_FONT, 11)
    canvas.setFillColor(HexColor("#666666"))
    canvas.drawString(20 * mm, 12 * mm, "PDF Studio — Easy Guide")
    canvas.drawRightString(190 * mm, 12 * mm, f"Page {canvas.getPageNumber()}")
    canvas.setStrokeColor(HexColor("#cccccc"))
    canvas.line(20 * mm, 16 * mm, 190 * mm, 16 * mm)
    canvas.restoreState()


def build():
    doc = BaseDocTemplate(OUT, pagesize=A4,
                          leftMargin=22 * mm, rightMargin=22 * mm,
                          topMargin=20 * mm, bottomMargin=22 * mm,
                          title="PDF Studio - Easy Guide", author="Leon Priest")
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="n")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=_page)])

    s = []
    s.append(Paragraph("PDF Studio", S_TITLE))
    s.append(Paragraph("Easy Guide — reading, filling in, and signing documents",
                       S_SUB))

    # 1. Comfort
    s.append(H1("Making it comfortable to read"))
    s.append(P("Do this first. It changes the whole program, and it remembers "
               "your choice."))
    s.append(H2("To make the text and buttons bigger"))
    s.append(STEP(1, "Click <b>View</b> at the top."))
    s.append(STEP(2, "Point to <b>Appearance</b>."))
    s.append(STEP(3, "Under <b>Text Size</b>, choose <b>Large</b> or "
                     "<b>Extra Large</b>."))
    s.append(H2("To switch between light and dark"))
    s.append(STEP(1, "Click <b>View</b>, then point to <b>Appearance</b>."))
    s.append(STEP(2, "Choose <b>High-Contrast Light</b> (black text on white) "
                     "or <b>Dark Industrial</b> (light text on black)."))
    s.append(TIP("Try both. Some people find the dark screen easier on the "
                 "eyes; others prefer the light one. There is no wrong answer — "
                 "pick whichever you can read most comfortably. The program "
                 "will remember it next time."))
    s.append(P("<b>To make the page itself bigger:</b> click <b>Zoom +</b> on "
               "the toolbar, or hold <b>Ctrl</b> and roll the mouse wheel."))

    # 2. Opening
    s.append(H1("Opening a document"))
    s.append(P("<b>The easy way:</b> double-click any PDF file. It will open in "
               "PDF Studio."))
    s.append(P("<b>From inside the program:</b> click <b>Open</b> on the "
               "toolbar, at the top-left."))
    s.append(P("You can also open <b>Word</b> documents and <b>Excel</b> "
               "spreadsheets. They may take a few seconds to appear — that is "
               "normal."))

    # 3. Moving around
    s.append(H1("Moving around a document"))
    s.append(TWOCOL([
        ("Go to the next page", "Click <b>Next</b>, or press the <b>right arrow</b> key"),
        ("Go back a page", "Click <b>Prev</b>, or press the <b>left arrow</b> key"),
        ("Jump to a page", "Type the page number in the toolbar box, press <b>Enter</b>"),
        ("Make the page bigger", "Click <b>Zoom +</b>"),
        ("Make the page smaller", "Click <b>Zoom -</b>"),
        ("Fit the whole page", "Click <b>Fit Pg</b>"),
        ("Fit the width", "Click <b>Fit W</b>"),
        ("Find a word", "Click <b>Search</b>, type the word, press <b>Enter</b>"),
    ], header=("To do this", "Do this")))
    s.append(Spacer(1, 10))
    s.append(P("The panel on the left shows the <b>Contents</b>, your "
               "<b>Bookmarks</b>, any <b>notes</b>, any <b>form fields</b>, and "
               "small <b>pictures of each page</b>. Click a page picture or form "
               "field to jump straight to it."))

    # 4. Forms
    s.append(H1("Filling in a form"))
    s.append(P("When a PDF already has fillable boxes, PDF Studio outlines them "
               "in light blue and opens a <b>Forms</b> section on the left."))
    s.append(STEP(1, "<b>Click</b> a field and type your answer."))
    s.append(STEP(2, "Tick boxes, choose radio buttons, or select from drop-down "
                     "and list fields."))
    s.append(STEP(3, "Double-click a field in the <b>Forms</b> panel when you want "
                     "PDF Studio to jump to it."))
    s.append(STEP(4, "Click <b>Save</b> when finished. A <b>*</b> beside the name "
                     "means changes are not saved yet."))
    s.append(P("The Forms panel can <b>Reset Page</b>, <b>Reset All</b>, or turn "
               "the blue highlights off."))
    s.append(TIP("<b>Flatten Form to Copy…</b> makes a separate finished copy "
                 "that cannot be edited accidentally. Your original fillable "
                 "PDF stays untouched."))
    s.append(H2("Let PDF Studio suggest the fields"))
    s.append(P("For many scanned forms, PDF Studio can make a careful first guess."))
    s.append(STEP(1, "Open the <b>Forms</b> section on the left."))
    s.append(STEP(2, "Under <b>Smart Form Detection</b>, leave the setting on "
                     "<b>Balanced</b>."))
    s.append(STEP(3, "Click <b>Detect Current Page...</b>."))
    s.append(STEP(4, "A large review window opens. Select each row to match it "
                     "with the coloured box on the page."))
    s.append(STEP(5, "Untick anything that looks wrong. The table shows the type, "
                     "label, confidence, and reason for every suggestion."))
    s.append(STEP(6, "Click <b>Create Checked</b>, then confirm."))
    s.append(STEP(7, "If you close the window, use <b>Review Suggestions...</b> "
                     "in Forms to reopen it."))
    s.append(STEP(8, "Use Design mode to move or resize anything that needs adjustment."))
    s.append(STEP(9, "Save the PDF."))
    s.append(TIP("Nothing is added until you approve it. <b>Clear</b> removes the "
                 "suggestions without changing the document. Try <b>More suggestions</b> "
                 "for a difficult page or <b>High confidence</b> for a stricter result."))

    s.append(H2("Make a scanned form fillable manually"))
    s.append(P("A scanned paper form starts as a picture. Form Designer can add "
               "real interactive fields to it."))
    s.append(STEP(1, "Open the <b>Forms</b> section and tick <b>Design mode</b>."))
    s.append(STEP(2, "Pick <b>Text Field</b>, <b>Checkbox</b>, <b>Dropdown</b>, "
                     "<b>Date</b>, <b>Yes / No</b>, <b>Signature</b>, or <b>Initials</b>."))
    s.append(STEP(3, "Click or drag where the field belongs."))
    s.append(STEP(4, "Click <b>Select</b>. Drag a field to move it, or drag the small "
                     "square at its lower-right corner to resize it."))
    s.append(STEP(5, "Click <b>Properties...</b> to name the field, make it required, "
                     "or enter dropdown choices one per line."))
    s.append(STEP(6, "Click <b>Save</b>, turn Design mode off, and fill the new form."))
    s.append(TIP("Keep the original scan as a backup. Signature and initials controls "
                 "are unsigned PDF signature placeholders; PDF Studio does not yet "
                 "apply certificate-backed signatures."))

    # 5. Scanned-text correction
    s.append(H1("Correcting words or numbers in a scan"))
    s.append(P("A scanned page is a picture. PDF Studio replaces a selected "
               "area rather than pretending the original letters are editable."))
    s.append(STEP(1, "Click <b>Edit Text</b> in the <b>EDIT SCAN</b> group."))
    s.append(STEP(2, "Drag a tight box around the word, number, or short line, "
                     "then release the mouse button."))
    s.append(STEP(3, "A <b>Preparing Scanned-Text Editor</b> window appears "
                     "immediately while PDF Studio reads only that selected area. "
                     "This first version reads English automatically; for other "
                     "languages, type the replacement manually."))
    s.append(STEP(4, "Check the recognised text and type the corrected version."))
    s.append(STEP(5, "Leave <b>Auto fit</b> on unless the preview is too large "
                     "or too small."))
    s.append(STEP(6, "Choose <b>Reversible white-out overlay</b> for the safest "
                     "correction, or permanent mode only when you are sure."))
    s.append(STEP(7, "Click <b>Apply Replacement</b>."))
    s.append(TIP("The reversible choice keeps the original scan underneath, "
                 "works with Ctrl+Z, and can be removed from Annotations. "
                 "Permanent mode forces Save As under a new filename so the "
                 "original remains safe."))
    s.append(P("If OCR cannot read the area or ends unexpectedly, the editor "
               "still opens so you can type the replacement manually."))

    # 6. Signing
    s.append(H1("Signing a document"))
    s.append(P("You have two ways to add your signature. Both work the same "
               "once it is on the page — it becomes part of the document when "
               "you save."))

    s.append(H2("Way 1 — Use a picture of your signature (recommended)"))
    s.append(P("If you have a photo or scan of your signature saved on the "
               "computer:"))
    s.append(TIP("<b>The quickest way:</b> simply <b>drag the picture file onto "
                 "the page</b> and drop it where you want the signature to go. "
                 "That's all — it is placed for you."))
    s.append(P("<b>Or, using the button:</b>"))
    s.append(STEP(1, "Click <b>Signature</b> on the toolbar."))
    s.append(STEP(2, "Choose <b>Import image file</b>."))
    s.append(STEP(3, "Click <b>Choose image\u2026</b> and pick your signature "
                     "picture."))
    s.append(STEP(4, "Leave <b>Remove white background</b> ticked. This hides "
                     "the white paper around your signature so only the ink "
                     "shows."))
    s.append(STEP(5, "Click <b>Add Signature</b>."))
    s.append(STEP(6, "<b>Click the spot on the page</b> where the signature "
                     "should go."))

    s.append(H2("Way 2 — Draw it with the mouse"))
    s.append(STEP(1, "Click <b>Signature</b> on the toolbar."))
    s.append(STEP(2, "Make sure <b>Draw signature</b> is selected."))
    s.append(STEP(3, "Draw your signature in the white box using the mouse. If "
                     "you don't like it, click <b>Clear</b> and try again."))
    s.append(STEP(4, "Click <b>Add Signature</b>."))
    s.append(STEP(5, "<b>Click the spot on the page</b> where it should go."))

    s.append(H2("Then save it"))
    s.append(P("Click <b>Save</b>. The signature is now part of the document."))
    s.append(TIP("Made a mistake? Press <b>Ctrl + Z</b> to undo it."))

    # 7. Markup
    s.append(H1("Marking up a document"))
    s.append(P("Click any of these buttons on the toolbar, then use the mouse "
               "on the page:"))
    s.append(BUL("<b>Note</b> — click the page to leave a sticky note."))
    s.append(BUL("<b>Highlight</b> — drag across text to highlight it."))
    s.append(BUL("<b>Underline</b> — drag across text to underline it."))
    s.append(BUL("<b>Strikethrough</b> — drag across text to cross it out."))
    s.append(BUL("<b>Draw</b> — draw freely on the page with the mouse."))
    s.append(BUL("<b>Eraser</b> — remove marks you have made."))
    s.append(P("The coloured <b>colour</b> button changes the colour."))
    s.append(TIP("When you are finished with a tool, press the <b>Esc</b> key "
                 "(top-left of the keyboard) to put it down."))
    s.append(P("Remember to click <b>Save</b> when you are done."))

    # 8. Save / print
    s.append(H1("Saving and printing"))
    s.append(TWOCOL([
        ("Save your changes", "Click <b>Save</b>, or press <b>Ctrl + S</b>"),
        ("Save as a new file<br/>(keep the original)", "<b>File &gt; Save As...</b>"),
        ("Check before you print", "<b>File &gt; Print Preview...</b>"),
        ("Print", "Click <b>Print</b>, or press <b>Ctrl + P</b>"),
    ], header=("To do this", "Do this")))
    s.append(Spacer(1, 8))
    s.append(TIP("<b>Print Preview</b> shows you exactly what will come out of "
                 "the printer <i>before</i> you print it \u2014 a good way to "
                 "avoid wasting paper."))
    s.append(Spacer(1, 10))
    s.append(P("If the title bar at the top shows a <b>*</b>, you have unsaved "
               "changes."))

    # 9. Troubleshooting
    s.append(H1("If something goes wrong"))
    s.append(H2("I made a mistake."))
    s.append(P("Press <b>Ctrl + Z</b> to undo. You can press it several times "
               "to undo more."))
    s.append(H2("The text is too small to read."))
    s.append(P("See <b>Making it comfortable to read</b> at the start of this "
               "guide, and choose <b>Extra Large</b>."))
    s.append(H2("I can't see the buttons clearly."))
    s.append(P("Try the other colour scheme: <b>View &gt; Appearance</b>, and "
               "switch between <b>High-Contrast Light</b> and "
               "<b>Dark Industrial</b>."))
    s.append(H2("The mouse is doing something odd on the page."))
    s.append(P("A marking tool is probably still switched on. Press the "
               "<b>Esc</b> key to put it down."))
    s.append(H2("A Word document won't open."))
    s.append(P("It may take a few seconds — please wait. If it still won't "
               "open, the computer may need Microsoft Word or LibreOffice "
               "installed. Ask Leon."))

    # 10. Keys
    s.append(H1("The most useful keys"))
    s.append(TWOCOL([
        ("<b>Ctrl + S</b>", "Save"),
        ("<b>Ctrl + Z</b>", "Undo"),
        ("<b>Ctrl + P</b>", "Print"),
        ("<b>Ctrl + F</b>", "Find a word"),
        ("<b>Left / Right arrows</b>", "Previous / next page"),
        ("<b>Ctrl + +</b>", "Bigger"),
        ("<b>Ctrl + -</b>", "Smaller"),
        ("<b>Esc</b>", "Put down the current tool"),
    ], header=("Key", "What it does")))
    s.append(Spacer(1, 16))
    s.append(TIP("PDF Studio is free. There is nothing to buy, no trial, and "
                 "nothing will ever expire."))

    doc.build(s)
    print("Wrote", OUT)


if __name__ == "__main__":
    build()
