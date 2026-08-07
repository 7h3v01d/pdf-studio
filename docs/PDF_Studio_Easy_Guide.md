# PDF Studio — Easy Guide

A simple guide to reading, filling in, and signing documents.

**Version 3.2.0-alpha12**

---

## Making it comfortable to read

Do this first. It changes the whole program, and it remembers your choice.

**To make the text and buttons bigger:**

1. Click **View** at the top.
2. Point to **Appearance**.
3. Under **Text Size**, choose **Large** or **Extra Large**.

**To switch between light and dark:**

1. Click **View** at the top.
2. Point to **Appearance**.
3. Choose **High-Contrast Light** (black text on white) or
   **Dark Industrial** (light text on black).

Try both. Some people find the dark screen easier on the eyes; others prefer
the light one. There is no wrong answer — pick whichever you can read most
comfortably, and the program will remember it next time.

**To make the page itself bigger:** click **Zoom +** on the toolbar, or hold
**Ctrl** and roll the mouse wheel.

---

## Opening a document

When PDF Studio starts, its red startup picture appears for about five seconds.
This is normal. The main window opens automatically when the picture fades away.

**The easy way:** if PDF Studio is your default PDF app, double-click any PDF file.
Otherwise, use **Open with → PDF Studio** or open the file from inside the program.

**From inside the program:** click **Open** on the toolbar (top-left).

You can also open **Word** documents (`.docx`) and **Excel** spreadsheets
(`.xlsx`). They may take a few seconds to appear — that is normal.

When an Office document is open, **Save** asks where to create a real PDF. The
program suggests the original folder and the same name ending in `.pdf`; it never
treats the hidden temporary conversion as your saved document.

---

## Moving around a document

| To do this | Do this |
|---|---|
| Go to the next page | Click **Next**, or press the **right arrow** key |
| Go back a page | Click **Prev**, or press the **left arrow** key |
| Jump to a page | Type the page number in the box on the toolbar, press **Enter** |
| Make the page bigger | Click **Zoom +** |
| Make the page smaller | Click **Zoom −** |
| Fit the page to the window | Click **Fit Pg** |
| Fit the width of the window | Click **Fit W** |
| Find a word | Click the **Search** box, type the word, press **Enter** |

The panel on the left shows the **Contents**, your **Bookmarks**, any **notes**
you have made, any **form fields**, and small **pictures of each page**. Click a page picture to jump
straight to it.

If the window is narrow, some right-hand toolbar groups move under **More »**.
Nothing has disappeared; widen the window and the groups return to the toolbar.

---

## Filling in a form

When a PDF already has fillable boxes, PDF Studio outlines them in light blue
and opens a **Forms** section in the panel on the left.

1. **Click** a field and type your answer.
2. Tick boxes, choose radio buttons, or select from drop-down and list fields.
3. Double-click a field in the Forms panel when you need PDF Studio to jump to it.
4. Click **Save** when finished. A `*` beside the document name means changes
   have not been saved yet.

The Forms panel can **Reset Page**, **Reset All**, or turn the blue highlights
off. **Flatten Form to Copy…** makes a separate finished copy that cannot be
edited accidentally; your original fillable PDF stays untouched.

### Let PDF Studio suggest the fields

For many scanned forms, PDF Studio can make a careful first guess:

1. Open the **Forms** section on the left.
2. Under **Smart Form Detection**, leave the setting on **Balanced**.
3. Click **Detect Current Page...**.
4. A large review window opens. Select each row to match it with the coloured
   box on the page.
5. Untick anything that looks wrong. The table shows the type, label, confidence,
   and reason for every suggestion.
6. Click **Create Checked**, then confirm.
7. If you close the window, use **Review Suggestions...** in Forms to reopen it.
8. Use Design mode to move or resize anything that needs adjustment.
9. Save the PDF.

Nothing is added until you approve it. **Clear** removes the suggestions without
changing the document. For a difficult page, try **More suggestions**; for a
cleaner, stricter result, choose **High confidence**.

### Make a scanned form fillable manually

A scanned paper form starts as a picture, but Form Designer can add real
interactive fields to it:

1. Open the **Forms** section and tick **Design mode**.
2. Pick **Text Field**, **Checkbox**, **Dropdown**, **Date**, **Yes / No**,
   **Signature**, or **Initials**.
3. Click or drag where the field belongs.
4. Click **Select** to move or resize it.
5. Use **Properties...** to name it, make it required, or enter dropdown choices
   one per line.
6. Click **Save**, turn Design mode off, and fill the new form normally.

> Keep the original scan as a backup. Signature and initials controls are
> unsigned PDF signature placeholders; PDF Studio does not yet apply
> certificate-backed signatures.

---

## Correcting words or numbers in a scan

A scanned page is a picture, so PDF Studio replaces a selected area rather than
editing hidden original letters.

1. Click **Edit Text** in the **EDIT SCAN** group at the top.
2. Drag a box closely around the word, number, or short line to change, then
   release the mouse button. The bottom status briefly says **Selection captured**.
3. A **Preparing Scanned-Text Editor** window then appears while PDF
   Studio reads only that small area. This first version reads
   English automatically; for other languages, type the replacement manually.
4. Check the recognised text and type the corrected version.
5. Leave **Auto fit** on for automatic sizing. If you choose a number instead,
   PDF Studio uses that exact point size.
6. Check the preview, then choose one of these:
   - **Reversible white-out overlay** - safest and recommended. The original scan
     stays underneath, `Ctrl+Z` works, and the replacement can be deleted from
     the Annotations list.
   - **Permanent erase + replacement** - removes everything inside the selected
     box before adding the new text. Use this only when you are sure.
7. Click **Apply Replacement**.

For a permanent replacement, PDF Studio makes you use **Save As** with a new
filename. This protects the original and writes a clean edited copy. If OCR cannot
read the area or ends unexpectedly, the editor still opens so you can type the
replacement yourself.

> Draw a tight box. Permanent mode can remove parts of nearby lines or pictures
> that touch the selection. Start with the reversible option when unsure.

---

## Signing a document

You have two ways to add your signature. **Both work the same once it's on the
page** — it becomes part of the document when you save.

### Way 1 — Use a picture of your signature (recommended)

If you have a photo or scan of your signature saved on the computer:

**The quickest way:** simply **drag the picture file onto the page** and drop it
where you want the signature to go. Done.

**Or, using the menu:**

1. Click **✍ Signature** on the toolbar.
2. Choose **Import image file**.
3. Click **Choose image…** and pick your signature picture.
4. Leave **Remove white background** ticked — this hides the white paper around
   your signature so only the ink shows.
5. Click **Add Signature**.
6. **Click the spot on the page** where the signature should go. If you click
   inside a signature field, PDF Studio fits the signature neatly inside it.

### Way 2 — Draw it with the mouse

1. Click **✍ Signature** on the toolbar.
2. Make sure **Draw signature** is selected.
3. Draw your signature in the white box using the mouse. Change **Thickness**
   or **Ink Colour** at any time; the drawing updates to match.
   (If you don't like it, click **Clear** and try again.)
4. Click **Add Signature**.
5. **Click the spot on the page** where the signature should go. A signature
   field is detected automatically and the signature is fitted inside it.

### Then save it

Click **Save**. The signature is now part of the document.

> **Tip:** Made a mistake? Press **Ctrl + Z** to undo it.

---

## Marking up a document

Click any of these buttons on the toolbar, then use the mouse on the page:

- **📌 Note** — click the page to leave a small sticky-note icon. Click the
  icon later to read the note; its text does not cover the page.
- **Highlight** — drag across text to highlight it.
- **Underline** — drag across text to underline it.
- **Strikethrough** — drag across text to cross it out.
- **✏ Draw** — draw freely on the page with the mouse.
- **Eraser** — remove marks you have made.

The coloured **◉** button changes the colour.

When you are finished with a tool, press the **Esc** key (top-left of the
keyboard) to put it down.

Remember to click **Save** when you are done.

---

## Turning a PDF page into a picture

This is useful for posters, flyers, or any website that asks for a PNG or JPG
instead of a PDF.

1. Open the PDF and go to the page you want.
2. Click **File → Export As → Image Files…**.
3. Choose **Current page**.
4. Choose a format:
   - **PNG** — best default for posters, text, and sharp graphics.
   - **JPEG** — smaller file, good for photographs.
   - **WebP** — small modern image for websites.
   - **TIFF** — high-quality print or archive work.
   - **BMP** — large, simple Windows bitmap.
   - **GIF** — limited-colour static image; it is not animated.
5. Leave the resolution at **300 DPI** for a printable poster, or use **150 DPI**
   for ordinary screen use.
6. Click **Export**, choose the filename, and save.

To convert several pages, choose **All pages** or type a page range such as
`1-3, 6`. PDF Studio creates one numbered picture for each page.

---

## Saving and printing

| To do this | Do this |
|---|---|
| Save your changes | Click **Save**, or press **Ctrl + S** |
| Save as a new file (keep the original) | **File → Save As…** |
| Check before printing | **File → Print Preview…** |
| Print | Click **Print**, or press **Ctrl + P** |

If the title bar at the top shows a **\*** , you have unsaved changes.

---

## If something goes wrong

**I made a mistake.**
Press **Ctrl + Z** to undo. You can press it several times to undo more.

**A message says “Save Rollback Incomplete”.**
Stop and do not delete the recovery folder shown in the message. It contains
original copies that may be needed to repair the save. Open **Help → Diagnostics…**
and send Leon the report plus the recovery-folder location.

**The text is too small to read.**
See *"Making it comfortable to read"* at the top of this guide. Choose
**Extra Large**.

**I can't see the buttons clearly.**
Try the other colour scheme: **View → Appearance**, and switch between
**High-Contrast Light** and **Dark Industrial**.

**I accidentally turned on a marking tool and now the mouse does odd things.**
Press the **Esc** key to put the tool down.

**A Word document won't open.**
It may take a few seconds — please wait. If it still won't open, the computer
may need Microsoft Word or LibreOffice installed. Ask Leon.

---

## The most useful keys

| Key | What it does |
|---|---|
| **Ctrl + S** | Save |
| **Ctrl + Z** | Undo |
| **Ctrl + P** | Print |
| **Ctrl + F** | Find a word |
| **Left / Right arrows** | Previous / next page |
| **Ctrl + +** | Bigger |
| **Ctrl + −** | Smaller |
| **Esc** | Put down the current tool |

---

*PDF Studio is free software. There is nothing to buy, no trial, and nothing
will ever expire.*


## Getting help with a problem

1. Click **Help**.
2. Click **Diagnostics…**.
3. Click **Copy Diagnostics** and paste the report into your support message.

The report does not copy the words or pictures from your PDF. It does include technical file paths, so look over it before sharing. You can also click **Open Log Folder** to find PDF Studio's bounded troubleshooting logs.


## If PDF Studio says recovery copies remain

The new PDF has been saved, but Windows could not remove a private original backup.
Choose **Retry Deletion** after closing antivirus, preview, sync, or backup software
that may be using the folder. Choose **Open Recovery Folder** to inspect the exact
location. Do not treat a redaction as securely complete until PDF Studio confirms the
recovery copies were removed.
