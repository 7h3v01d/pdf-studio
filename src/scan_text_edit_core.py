"""Core operations for OCR-assisted scanned-text replacement.

The module intentionally contains no Qt dependencies so the destructive and
non-destructive PDF operations can be exercised by pytest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import fitz

MODE_OVERLAY = "overlay"
MODE_REDACT = "redact"
VALID_MODES = {MODE_OVERLAY, MODE_REDACT}

ALIGN_LEFT = 0
ALIGN_CENTER = 1
ALIGN_RIGHT = 2
VALID_ALIGNMENTS = {ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT}

PDFSTUDIO_SUBJECT = "PDF Studio scan text replacement"


def inverted_fitz_matrix(matrix: fitz.Matrix) -> fitz.Matrix:
    """Return an inverted copy of a PyMuPDF matrix.

    ``Matrix.invert()`` mutates the matrix and returns an integer status code;
    it does *not* return the inverse matrix.  Keeping this detail behind one
    helper prevents valid page selections and placement points from being
    multiplied by the success code ``0`` and collapsing to the origin.
    """
    inverse = fitz.Matrix(matrix)
    status = inverse.invert()
    if status != 0:
        raise ValueError("The PDF render matrix could not be inverted.")
    return inverse


@dataclass(frozen=True)
class ScanTextReplacement:
    page_number: int
    rect: tuple[float, float, float, float]
    replacement_text: str
    original_text: str = ""
    mode: str = MODE_OVERLAY
    font_size: float = 0.0
    alignment: int = ALIGN_LEFT
    text_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    background_color: tuple[float, float, float] = (1.0, 1.0, 1.0)

    def validated(self, page_rect: fitz.Rect | Sequence[float]) -> "ScanTextReplacement":
        rect = normalise_replacement_rect(self.rect, page_rect)
        text = str(self.replacement_text).strip()
        if not text:
            raise ValueError("Replacement text cannot be empty.")
        if self.mode not in VALID_MODES:
            raise ValueError(f"Unsupported replacement mode: {self.mode}")
        if self.alignment not in VALID_ALIGNMENTS:
            raise ValueError("Unsupported text alignment.")
        return ScanTextReplacement(
            page_number=int(self.page_number),
            rect=tuple(rect),
            replacement_text=text,
            original_text=str(self.original_text or ""),
            mode=self.mode,
            font_size=float(self.font_size),
            alignment=int(self.alignment),
            text_color=normalise_color(self.text_color),
            background_color=normalise_color(self.background_color),
        )


def normalise_color(color: Iterable[float]) -> tuple[float, float, float]:
    values = tuple(float(value) for value in color)
    if len(values) != 3:
        raise ValueError("Colours must contain exactly three RGB components.")
    return tuple(max(0.0, min(1.0, value)) for value in values)  # type: ignore[return-value]


def normalise_replacement_rect(
    rect: fitz.Rect | Sequence[float],
    page_rect: fitz.Rect | Sequence[float],
    *,
    minimum_width: float = 8.0,
    minimum_height: float = 8.0,
) -> fitz.Rect:
    candidate = fitz.Rect(rect)
    bounds = fitz.Rect(page_rect)
    candidate.normalize()
    candidate &= bounds
    if candidate.is_empty or candidate.width < minimum_width or candidate.height < minimum_height:
        raise ValueError("The selected area is too small for text replacement.")
    return candidate


def fit_font_size(
    text: str,
    rect: fitz.Rect | Sequence[float],
    *,
    requested_size: float = 0.0,
    minimum: float = 4.0,
    maximum: float = 72.0,
    horizontal_padding: float = 4.0,
    vertical_padding: float = 3.0,
) -> float:
    """Return a conservative Helvetica size that fits the supplied rectangle."""
    box = fitz.Rect(rect)
    usable_width = max(1.0, box.width - horizontal_padding * 2)
    usable_height = max(1.0, box.height - vertical_padding * 2)
    lines = str(text or "").splitlines() or [""]
    font = fitz.Font(fontname="helv")

    if requested_size > 0:
        ceiling = min(float(requested_size), maximum)
    else:
        ceiling = maximum

    longest_at_one = max(font.text_length(line or " ", fontsize=1.0) for line in lines)
    width_limit = usable_width / max(longest_at_one, 0.01)
    line_height_factor = 1.25
    height_limit = usable_height / max(len(lines) * line_height_factor, 0.01)
    return round(max(minimum, min(ceiling, width_limit, height_limit)), 2)


def sample_background_rgb(image, *, border_fraction: float = 0.12) -> tuple[float, float, float]:
    """Estimate a replacement background from pixels around a cropped region.

    ``image`` is expected to be a Pillow image. The import is deliberately
    local so PDF-only operations do not require Pillow at import time.
    """
    from PIL import ImageStat

    rgb = image.convert("RGB")
    width, height = rgb.size
    if width <= 1 or height <= 1:
        return (1.0, 1.0, 1.0)

    border_x = max(1, int(width * border_fraction))
    border_y = max(1, int(height * border_fraction))
    strips = [
        rgb.crop((0, 0, width, min(border_y, height))),
        rgb.crop((0, max(0, height - border_y), width, height)),
        rgb.crop((0, 0, min(border_x, width), height)),
        rgb.crop((max(0, width - border_x), 0, width, height)),
    ]
    samples = []
    for strip in strips:
        # Pillow 12 renamed the flattened pixel iterator; keep compatibility
        # with the supported Pillow 10+ range without emitting new-version
        # deprecation warnings.
        getter = getattr(strip, "get_flattened_data", None)
        samples.extend(getter() if getter else strip.getdata())
    if not samples:
        return (1.0, 1.0, 1.0)

    # Median is resistant to dark text crossing the sampled border.
    channels = list(zip(*samples))
    medians = []
    for channel in channels:
        ordered = sorted(channel)
        medians.append(ordered[len(ordered) // 2] / 255.0)
    return normalise_color(medians)



def choose_drag_endpoint(
    start: Sequence[float],
    *candidates: Sequence[float] | None,
) -> tuple[float, float]:
    """Return the endpoint that best represents a completed drag.

    Some Windows / Qt combinations can report the mouse-release position back
    at (or very close to) the press position after a widget mouse grab is
    released. The last mouse-move position is still valid in that case. Choose
    the candidate enclosing the largest rectangle from ``start`` instead of
    blindly trusting the release event.
    """
    sx, sy = float(start[0]), float(start[1])
    valid: list[tuple[float, float]] = []
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            x, y = float(candidate[0]), float(candidate[1])
        except (TypeError, ValueError, IndexError):
            continue
        valid.append((x, y))

    if not valid:
        return sx, sy

    def score(point: tuple[float, float]) -> tuple[float, float]:
        dx = abs(point[0] - sx)
        dy = abs(point[1] - sy)
        # Rectangle area is the primary signal. Squared distance breaks ties
        # for very thin drags without changing the conservative size gate.
        return dx * dy, dx * dx + dy * dy

    return max(valid, key=score)


def drag_rectangle_is_large_enough(
    start: Sequence[float],
    end: Sequence[float],
    *,
    minimum_pixels: float = 5.0,
) -> bool:
    """Return whether a drag has useful width and height in widget pixels."""
    return (
        abs(float(start[0]) - float(end[0])) > float(minimum_pixels)
        and abs(float(start[1]) - float(end[1])) > float(minimum_pixels)
    )


def ocr_text_and_confidence(data: dict) -> tuple[str, float]:
    """Build readable OCR text and mean confidence from Tesseract TSV data.

    ``pytesseract.image_to_data(..., output_type=Output.DICT)`` already runs
    recognition. Reconstructing the text from that result avoids launching a
    second Tesseract process merely to obtain ``image_to_string`` output.
    """
    texts = list(data.get("text", []) or [])
    confidences = list(data.get("conf", []) or [])
    block_numbers = list(data.get("block_num", []) or [])
    paragraph_numbers = list(data.get("par_num", []) or [])
    line_numbers = list(data.get("line_num", []) or [])

    lines: list[list[str]] = []
    current_key = None
    accepted_confidences: list[float] = []

    for index, raw_text in enumerate(texts):
        word = str(raw_text or "").strip()
        if not word:
            continue

        key = (
            block_numbers[index] if index < len(block_numbers) else 0,
            paragraph_numbers[index] if index < len(paragraph_numbers) else 0,
            line_numbers[index] if index < len(line_numbers) else index,
        )
        if key != current_key:
            lines.append([])
            current_key = key
        lines[-1].append(word)

        if index < len(confidences):
            try:
                value = float(confidences[index])
            except (TypeError, ValueError):
                pass
            else:
                if value >= 0:
                    accepted_confidences.append(value)

    text = "\n".join(" ".join(words) for words in lines if words).strip()
    confidence = (
        sum(accepted_confidences) / len(accepted_confidences)
        if accepted_confidences
        else 0.0
    )
    return text, confidence

def apply_scan_text_replacement(
    document: fitz.Document,
    plan: ScanTextReplacement,
) -> dict:
    """Apply one replacement and return metadata about the created object.

    Overlay mode creates a single opaque FreeText annotation. It can be removed
    later and does not destroy the underlying scan. Redact mode permanently
    removes page content under the rectangle and burns replacement text in.
    """
    if not 0 <= int(plan.page_number) < document.page_count:
        raise IndexError("Replacement page is outside the document.")

    page = document.load_page(int(plan.page_number))
    clean = plan.validated(page.rect)
    rect = fitz.Rect(clean.rect)
    fontsize = fit_font_size(
        clean.replacement_text,
        rect,
        requested_size=clean.font_size,
    )

    if clean.mode == MODE_OVERLAY:
        annot = page.add_freetext_annot(
            rect,
            clean.replacement_text,
            fontsize=fontsize,
            fontname="Helv",
            text_color=clean.text_color,
            fill_color=clean.background_color,
            border_color=None,
            border_width=0,
            opacity=1,
            align=clean.alignment,
        )
        info = dict(annot.info or {})
        info.update({
            "subject": PDFSTUDIO_SUBJECT,
            "content": clean.replacement_text,
            "title": "PDF Studio",
        })
        annot.set_info(info)
        annot.update()
        return {
            "mode": MODE_OVERLAY,
            "page_number": clean.page_number,
            "rect": tuple(rect),
            "font_size": fontsize,
            "annotation_xref": annot.xref,
            "reversible": True,
        }

    redact = page.add_redact_annot(
        rect,
        text=clean.replacement_text,
        fontname="helv",
        fontsize=fontsize,
        align=clean.alignment,
        fill=clean.background_color,
        text_color=clean.text_color,
        cross_out=False,
    )
    redact.set_info(
        title="PDF Studio",
        subject=PDFSTUDIO_SUBJECT,
        content=clean.replacement_text,
    )
    redact.update()
    try:
        page.apply_redactions(images=2, graphics=1, text=0)
    except TypeError:
        # Older supported PyMuPDF builds did not expose every keyword.
        page.apply_redactions(images=2)
    return {
        "mode": MODE_REDACT,
        "page_number": clean.page_number,
        "rect": tuple(rect),
        "font_size": fontsize,
        "annotation_xref": None,
        "reversible": False,
    }


def remove_overlay_replacement(
    document: fitz.Document,
    *,
    page_number: int,
    annotation_xref: int,
) -> bool:
    """Remove a reversible overlay by xref."""
    if not 0 <= int(page_number) < document.page_count:
        return False
    page = document.load_page(int(page_number))
    annot = page.first_annot
    while annot is not None:
        next_annot = annot.next
        if annot.xref == int(annotation_xref):
            page.delete_annot(annot)
            return True
        annot = next_annot
    return False
