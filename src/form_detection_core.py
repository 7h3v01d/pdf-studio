"""Conservative OCR-assisted form-field suggestion engine.

The detector never mutates a PDF.  It combines recognised text with vector or
raster line/box geometry and returns reviewable suggestions.  The GUI must ask
the user to approve suggestions before creating genuine AcroForm widgets.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from collections.abc import Iterable, Sequence
from typing import Any

import fitz


@dataclass(frozen=True)
class OCRWord:
    text: str
    rect: tuple[float, float, float, float]
    confidence: float = 1.0
    source: str = "native"

    @property
    def fitz_rect(self) -> fitz.Rect:
        return fitz.Rect(self.rect)


@dataclass(frozen=True)
class GraphicPrimitive:
    kind: str  # hline, vline, box
    rect: tuple[float, float, float, float]
    confidence: float = 1.0
    source: str = "vector"

    @property
    def fitz_rect(self) -> fitz.Rect:
        return fitz.Rect(self.rect)


@dataclass(frozen=True)
class FieldSuggestion:
    suggestion_id: str
    page: int
    kind: str  # text, checkbox, date, signature, initials
    rect: tuple[float, float, float, float]
    label: str
    name: str
    confidence: float
    rationale: str
    source: str
    multiline: bool = False

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


_LABEL_RULES: tuple[tuple[re.Pattern[str], str, float, bool], ...] = (
    (re.compile(r"\b(date of birth|birth date|dob)\b", re.I), "date", 0.93, False),
    (re.compile(r"\b(date|dated|expiry date|issue date)\b", re.I), "date", 0.88, False),
    (re.compile(r"\b(initials?|initial here)\b", re.I), "initials", 0.94, False),
    (re.compile(r"\b(signature|signed by|sign here)\b", re.I), "signature", 0.96, False),
    (re.compile(r"\b(comments?|notes?|details?|description|reason)\b", re.I), "text", 0.84, True),
    (re.compile(
        r"\b(full name|first name|given name|surname|last name|name|address|"
        r"street|suburb|city|state|postcode|postal code|zip|phone|mobile|"
        r"telephone|email|company|organisation|organization|account|reference|"
        r"invoice|amount|occupation|position|title|country)\b",
        re.I,
    ), "text", 0.83, False),
)


def _clean_label_text(text: str) -> str:
    clean = " ".join(str(text).split()).strip()
    # OCR often mistakes a nearby box edge for [, ], |, or _.
    clean = re.sub(r"[\s\[\]\|_]+$", "", clean).strip()
    # Isolated O / 0 is a common OCR reading of an adjacent empty checkbox.
    clean = re.sub(r"\s+[O0]$", "", clean, flags=re.I).strip()
    return clean.rstrip(":").strip()


def _slug(text: str, fallback: str = "field") -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", _clean_label_text(text).lower()).strip("_")
    return value[:48] or fallback


def _rect_tuple(rect: fitz.Rect) -> tuple[float, float, float, float]:
    return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))


def _intersection_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    denominator = min(max(a.get_area(), 1e-6), max(b.get_area(), 1e-6))
    return inter.get_area() / denominator


def _iou(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    union = a.get_area() + b.get_area() - inter.get_area()
    return inter.get_area() / max(union, 1e-6)


def words_from_native(page: fitz.Page) -> list[OCRWord]:
    words: list[OCRWord] = []
    for item in page.get_text("words") or []:
        if len(item) < 5:
            continue
        text = str(item[4]).strip()
        if not text:
            continue
        words.append(
            OCRWord(
                text=text,
                rect=(float(item[0]), float(item[1]), float(item[2]), float(item[3])),
                confidence=1.0,
                source="native",
            )
        )
    return words


def words_from_tesseract_data(
    data: dict[str, Sequence[Any]],
    image_size: tuple[int, int],
    page_rect: fitz.Rect,
    *,
    minimum_confidence: float = 30.0,
) -> list[OCRWord]:
    """Map pytesseract ``Output.DICT`` data into PDF coordinates."""
    image_width, image_height = image_size
    if image_width <= 0 or image_height <= 0:
        return []
    sx = page_rect.width / image_width
    sy = page_rect.height / image_height
    result: list[OCRWord] = []
    texts = data.get("text", [])
    for index, raw_text in enumerate(texts):
        text = str(raw_text or "").strip()
        if not text:
            continue
        try:
            raw_conf = float(data.get("conf", [])[index])
        except (ValueError, TypeError, IndexError):
            raw_conf = -1.0
        if raw_conf < minimum_confidence:
            continue
        try:
            left = float(data["left"][index])
            top = float(data["top"][index])
            width = float(data["width"][index])
            height = float(data["height"][index])
        except (KeyError, ValueError, TypeError, IndexError):
            continue
        rect = fitz.Rect(
            page_rect.x0 + left * sx,
            page_rect.y0 + top * sy,
            page_rect.x0 + (left + width) * sx,
            page_rect.y0 + (top + height) * sy,
        )
        if rect.is_empty:
            continue
        result.append(
            OCRWord(
                text=text,
                rect=_rect_tuple(rect),
                confidence=max(0.0, min(1.0, raw_conf / 100.0)),
                source="ocr",
            )
        )
    return result


def vector_graphics_from_page(page: fitz.Page) -> list[GraphicPrimitive]:
    """Extract useful horizontal lines, vertical lines, and rectangles."""
    primitives: list[GraphicPrimitive] = []
    for drawing in page.get_drawings() or []:
        for item in drawing.get("items", []):
            if not item:
                continue
            kind = item[0]
            if kind == "l" and len(item) >= 3:
                p1, p2 = item[1], item[2]
                dx = abs(float(p2.x) - float(p1.x))
                dy = abs(float(p2.y) - float(p1.y))
                if dx >= 18.0 and dy <= 1.5:
                    rect = fitz.Rect(min(p1.x, p2.x), min(p1.y, p2.y) - 0.5,
                                     max(p1.x, p2.x), max(p1.y, p2.y) + 0.5)
                    primitives.append(GraphicPrimitive("hline", _rect_tuple(rect)))
                elif dy >= 12.0 and dx <= 1.5:
                    rect = fitz.Rect(min(p1.x, p2.x) - 0.5, min(p1.y, p2.y),
                                     max(p1.x, p2.x) + 0.5, max(p1.y, p2.y))
                    primitives.append(GraphicPrimitive("vline", _rect_tuple(rect)))
            elif kind == "re" and len(item) >= 2:
                rect = fitz.Rect(item[1])
                if rect.width >= 8.0 and rect.height >= 8.0:
                    primitives.append(GraphicPrimitive("box", _rect_tuple(rect)))
    return _dedupe_graphics(primitives)


def _scan_dark_runs(
    data: bytes,
    width: int,
    height: int,
    *,
    min_run: int,
    max_gap: int = 1,
    density: float = 0.88,
) -> list[tuple[int, int, int]]:
    """Return ``(row, start, end)`` dark runs from a 0/1 byte image."""
    runs: list[tuple[int, int, int]] = []
    for row_index in range(height):
        row = data[row_index * width:(row_index + 1) * width]
        start = -1
        dark_count = 0
        gap = 0
        for column, value in enumerate(row):
            if value:
                if start < 0:
                    start = column
                dark_count += 1
                gap = 0
            elif start >= 0:
                gap += 1
                if gap > max_gap:
                    end = column - gap + 1
                    length = end - start
                    if length >= min_run and dark_count / max(length, 1) >= density:
                        runs.append((row_index, start, end))
                    start = -1
                    dark_count = 0
                    gap = 0
        if start >= 0:
            end = width
            length = end - start
            if length >= min_run and dark_count / max(length, 1) >= density:
                runs.append((row_index, start, end))
    return runs


def _merge_row_runs(
    runs: Sequence[tuple[int, int, int]],
    *,
    row_tolerance: int = 3,
    endpoint_tolerance: int = 5,
) -> list[tuple[int, int, int, int]]:
    """Merge adjacent scan rows into ``(x0, y0, x1, y1)`` bands."""
    merged: list[list[int]] = []
    for row, start, end in sorted(runs):
        matched = None
        for candidate in reversed(merged[-30:]):
            if row - candidate[3] > row_tolerance:
                continue
            overlap = min(end, candidate[2]) - max(start, candidate[0])
            if overlap >= min(end - start, candidate[2] - candidate[0]) * 0.65 or (
                abs(start - candidate[0]) <= endpoint_tolerance
                and abs(end - candidate[2]) <= endpoint_tolerance
            ):
                matched = candidate
                break
        if matched is None:
            merged.append([start, row, end, row])
        else:
            matched[0] = min(matched[0], start)
            matched[2] = max(matched[2], end)
            matched[3] = row
    return [tuple(item) for item in merged]


def raster_graphics_from_image(
    image,
    page_rect: fitz.Rect,
    *,
    threshold: int = 175,
) -> list[GraphicPrimitive]:
    """Detect long lines and outlined boxes in a rendered page image.

    This intentionally uses Pillow and byte scans instead of OpenCV so form
    detection does not add another large deployment dependency.
    """
    from PIL import Image

    gray = image.convert("L")
    binary = gray.point(lambda value: 1 if value < threshold else 0, mode="L")
    width, height = binary.size
    if width <= 0 or height <= 0:
        return []

    minimum_horizontal = max(24, int(width * 0.035))
    binary_bytes = binary.tobytes()
    horizontal_runs = _scan_dark_runs(
        binary_bytes, width, height, min_run=minimum_horizontal
    )
    horizontal_bands = _merge_row_runs(horizontal_runs)
    # A separate strict short-run pass is used only to reconstruct outlined
    # boxes, including small checkbox squares. It is not exposed as blank lines.
    short_horizontal_runs = _scan_dark_runs(
        binary_bytes, width, height,
        min_run=max(12, int(width * 0.009)), max_gap=0, density=0.94,
    )
    short_horizontal_bands = _merge_row_runs(
        short_horizontal_runs, row_tolerance=3, endpoint_tolerance=3
    )

    transposed = binary.transpose(Image.Transpose.TRANSPOSE)
    transposed_bytes = transposed.tobytes()
    vertical_runs = _scan_dark_runs(
        transposed_bytes, height, width,
        min_run=max(16, int(height * 0.012)),
    )
    vertical_bands_raw = _merge_row_runs(vertical_runs)
    short_vertical_runs = _scan_dark_runs(
        transposed_bytes, height, width,
        min_run=max(12, int(height * 0.009)), max_gap=0, density=0.94,
    )
    short_vertical_bands_raw = _merge_row_runs(
        short_vertical_runs, row_tolerance=3, endpoint_tolerance=3
    )
    # Transposed coordinates: (original y0, original x0, original y1, original x1)
    vertical_bands = [
        (band[1], band[0], band[3], band[2]) for band in vertical_bands_raw
    ]
    short_vertical_bands = [
        (band[1], band[0], band[3], band[2])
        for band in short_vertical_bands_raw
    ]

    sx = page_rect.width / width
    sy = page_rect.height / height
    primitives: list[GraphicPrimitive] = []
    for x0, y0, x1, y1 in horizontal_bands:
        if x1 - x0 < minimum_horizontal:
            continue
        rect = fitz.Rect(
            page_rect.x0 + x0 * sx,
            page_rect.y0 + y0 * sy,
            page_rect.x0 + x1 * sx,
            page_rect.y0 + max(y1 + 1, y0 + 1) * sy,
        )
        primitives.append(GraphicPrimitive("hline", _rect_tuple(rect), 0.72, "raster"))

    for x0, y0, x1, y1 in vertical_bands:
        if y1 - y0 < max(16, int(height * 0.012)):
            continue
        rect = fitz.Rect(
            page_rect.x0 + x0 * sx,
            page_rect.y0 + y0 * sy,
            page_rect.x0 + max(x1 + 1, x0 + 1) * sx,
            page_rect.y0 + y1 * sy,
        )
        primitives.append(GraphicPrimitive("vline", _rect_tuple(rect), 0.68, "raster"))

    # Build outlined rectangles from strict short-run geometry so small
    # checkboxes are not lost to the longer blank-line threshold.
    h_lines = [
        GraphicPrimitive(
            "hline",
            _rect_tuple(fitz.Rect(
                page_rect.x0 + x0 * sx, page_rect.y0 + y0 * sy,
                page_rect.x0 + x1 * sx, page_rect.y0 + max(y1 + 1, y0 + 1) * sy,
            )),
            0.70, "raster",
        )
        for x0, y0, x1, y1 in short_horizontal_bands
    ]
    v_lines = [
        GraphicPrimitive(
            "vline",
            _rect_tuple(fitz.Rect(
                page_rect.x0 + x0 * sx, page_rect.y0 + y0 * sy,
                page_rect.x0 + max(x1 + 1, x0 + 1) * sx, page_rect.y0 + y1 * sy,
            )),
            0.68, "raster",
        )
        for x0, y0, x1, y1 in short_vertical_bands
    ]
    boxes: list[GraphicPrimitive] = []
    for top_index, top in enumerate(h_lines):
        tr = top.fitz_rect
        if tr.width < 9.0 or tr.width > page_rect.width * 0.85:
            continue
        for bottom in h_lines[top_index + 1:]:
            br = bottom.fitz_rect
            height_points = br.y0 - tr.y0
            if height_points < 8.0:
                continue
            if height_points > 65.0:
                break
            if abs(tr.x0 - br.x0) > 4.5 or abs(tr.x1 - br.x1) > 4.5:
                continue
            left_found = False
            right_found = False
            for vertical in v_lines:
                vr = vertical.fitz_rect
                spans = vr.y0 <= tr.y1 + 3.0 and vr.y1 >= br.y0 - 3.0
                if not spans:
                    continue
                if abs(vr.x0 - tr.x0) <= 4.5:
                    left_found = True
                if abs(vr.x0 - tr.x1) <= 4.5:
                    right_found = True
                if left_found and right_found:
                    break
            if left_found and right_found:
                box_rect = fitz.Rect(tr.x0, tr.y0, tr.x1, br.y1)
                boxes.append(GraphicPrimitive("box", _rect_tuple(box_rect), 0.82, "raster"))
                break

    return _dedupe_graphics(primitives + boxes)


def _dedupe_graphics(primitives: Iterable[GraphicPrimitive]) -> list[GraphicPrimitive]:
    result: list[GraphicPrimitive] = []
    for candidate in sorted(primitives, key=lambda item: item.confidence, reverse=True):
        rect = candidate.fitz_rect
        duplicate = False
        for existing in result:
            if candidate.kind != existing.kind:
                continue
            if _iou(rect, existing.fitz_rect) >= 0.75:
                duplicate = True
                break
        if not duplicate:
            result.append(candidate)
    return result


@dataclass
class _TextLine:
    text: str
    rect: fitz.Rect
    confidence: float
    source: str


def _group_words_into_lines(words: Sequence[OCRWord]) -> list[_TextLine]:
    ordered = sorted(words, key=lambda word: (word.fitz_rect.y0, word.fitz_rect.x0))
    lines: list[list[OCRWord]] = []
    for word in ordered:
        rect = word.fitz_rect
        center = (rect.y0 + rect.y1) / 2.0
        target: list[OCRWord] | None = None
        best_distance = math.inf
        for line in reversed(lines[-12:]):
            line_rect = fitz.Rect(line[0].fitz_rect)
            for item in line[1:]:
                line_rect |= item.fitz_rect
            line_center = (line_rect.y0 + line_rect.y1) / 2.0
            tolerance = max(3.0, min(rect.height, line_rect.height) * 0.65)
            distance = abs(center - line_center)
            if distance <= tolerance and distance < best_distance:
                target = line
                best_distance = distance
        if target is None:
            lines.append([word])
        else:
            target.append(word)

    result: list[_TextLine] = []
    for words_in_line in lines:
        words_in_line.sort(key=lambda word: word.fitz_rect.x0)
        rect = fitz.Rect(words_in_line[0].fitz_rect)
        for word in words_in_line[1:]:
            rect |= word.fitz_rect
        text = " ".join(word.text for word in words_in_line).strip()
        confidence = sum(word.confidence for word in words_in_line) / len(words_in_line)
        source = "native" if all(word.source == "native" for word in words_in_line) else "ocr"
        if text:
            result.append(_TextLine(text, rect, confidence, source))
    return result


def _classify_label(text: str) -> tuple[str, float, bool] | None:
    clean = " ".join(text.replace("_", " ").split())
    for pattern, kind, confidence, multiline in _LABEL_RULES:
        if pattern.search(clean):
            return kind, confidence, multiline
    # Short labels ending in a colon are useful, but less certain.
    if clean.rstrip().endswith(":") and 1 <= len(clean.split()) <= 6:
        return "text", 0.70, False
    return None


def _nearest_graphic_for_label(
    label: _TextLine,
    graphics: Sequence[GraphicPrimitive],
    page_rect: fitz.Rect,
) -> GraphicPrimitive | None:
    candidates: list[tuple[float, GraphicPrimitive]] = []
    lr = label.rect
    for primitive in graphics:
        gr = primitive.fitz_rect
        if primitive.kind == "vline":
            continue
        # Prefer geometry immediately to the right on the same baseline.
        horizontal_gap = gr.x0 - lr.x1
        vertical_overlap = min(gr.y1, lr.y1 + 8.0) - max(gr.y0, lr.y0 - 8.0)
        if -3.0 <= horizontal_gap <= page_rect.width * 0.48 and vertical_overlap >= -3.0:
            distance = max(0.0, horizontal_gap) + abs(gr.y0 - lr.y0) * 1.5
            if primitive.kind == "box":
                distance -= 18.0
            candidates.append((distance, primitive))
            continue
        # Or directly underneath the label.
        vertical_gap = gr.y0 - lr.y1
        horizontal_overlap = min(gr.x1, lr.x1 + 45.0) - max(gr.x0, lr.x0 - 5.0)
        if -2.0 <= vertical_gap <= 28.0 and horizontal_overlap >= 5.0:
            distance = max(0.0, vertical_gap) * 1.2 + abs(gr.x0 - lr.x0)
            if primitive.kind == "box":
                distance -= 18.0
            candidates.append((distance + 12.0, primitive))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _field_rect_from_graphic(
    graphic: GraphicPrimitive,
    kind: str,
    page_rect: fitz.Rect,
    *,
    multiline: bool,
) -> fitz.Rect:
    gr = graphic.fitz_rect
    if graphic.kind == "box":
        if kind in ("checkbox", "initials"):
            return fitz.Rect(gr)
        inset = 1.5
        return fitz.Rect(gr.x0 + inset, gr.y0 + inset, gr.x1 - inset, gr.y1 - inset)
    # Underline: place the editable rectangle immediately above it.
    height = 42.0 if multiline else (34.0 if kind == "signature" else 20.0)
    return fitz.Rect(gr.x0, max(page_rect.y0, gr.y0 - height), gr.x1, gr.y1 + 2.0)


def _fallback_rect(
    label: _TextLine,
    kind: str,
    page_rect: fitz.Rect,
    *,
    multiline: bool,
) -> fitz.Rect | None:
    widths = {
        "date": 110.0,
        "signature": 190.0,
        "initials": 75.0,
        "checkbox": 18.0,
        "text": 180.0,
    }
    heights = {
        "date": 22.0,
        "signature": 48.0,
        "initials": 34.0,
        "checkbox": 18.0,
        "text": 54.0 if multiline else 22.0,
    }
    width = widths.get(kind, 180.0)
    height = heights.get(kind, 22.0)
    x0 = label.rect.x1 + 8.0
    y0 = label.rect.y0 - 2.0
    if x0 + width > page_rect.x1 - 18.0:
        x0 = label.rect.x0
        y0 = label.rect.y1 + 5.0
    x1 = min(page_rect.x1 - 18.0, x0 + width)
    y1 = min(page_rect.y1 - 12.0, y0 + height)
    if x1 - x0 < 45.0 and kind not in ("checkbox", "initials"):
        return None
    return fitz.Rect(x0, y0, x1, y1)


def _nearby_label_for_box(box: fitz.Rect, lines: Sequence[_TextLine]) -> _TextLine | None:
    candidates: list[tuple[float, _TextLine]] = []
    for line in lines:
        lr = line.rect
        same_row = not (lr.y1 < box.y0 - 8.0 or lr.y0 > box.y1 + 8.0)
        if same_row:
            if lr.x1 <= box.x0:
                distance = box.x0 - lr.x1
            elif lr.x0 >= box.x1:
                distance = lr.x0 - box.x1 + 8.0
            else:
                distance = 0.0
            if distance <= 130.0:
                candidates.append((distance, line))
        elif 0.0 <= box.y0 - lr.y1 <= 24.0:
            horizontal = abs(box.x0 - lr.x0)
            if horizontal <= 55.0:
                candidates.append((35.0 + horizontal, line))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def detect_form_suggestions(
    *,
    page_number: int,
    page_rect: fitz.Rect,
    words: Sequence[OCRWord],
    graphics: Sequence[GraphicPrimitive],
    existing_field_rects: Sequence[Sequence[float]] = (),
    minimum_confidence: float = 0.60,
) -> list[FieldSuggestion]:
    """Return conservative, non-mutating field suggestions."""
    lines = _group_words_into_lines(words)
    graphics = _dedupe_graphics(graphics)
    existing = [fitz.Rect(rect) for rect in existing_field_rects]
    raw: list[FieldSuggestion] = []
    used_graphics: set[int] = set()
    used_graphic_rects: list[fitz.Rect] = []
    counter = 0

    def add_suggestion(
        kind: str,
        rect: fitz.Rect,
        label: str,
        confidence: float,
        rationale: str,
        source: str,
        multiline: bool = False,
    ) -> None:
        nonlocal counter
        rect &= page_rect
        if rect.is_empty or rect.width < 8.0 or rect.height < 8.0:
            return
        if any(_intersection_ratio(rect, current) >= 0.45 for current in existing):
            return
        confidence = max(0.0, min(0.99, confidence))
        if confidence < minimum_confidence:
            return
        counter += 1
        fallback = {
            "text": "text_field",
            "date": "date_field",
            "checkbox": "checkbox",
            "signature": "signature",
            "initials": "initials",
        }.get(kind, "field")
        raw.append(
            FieldSuggestion(
                suggestion_id=f"p{page_number + 1}_{counter}",
                page=page_number,
                kind=kind,
                rect=_rect_tuple(rect),
                label=_clean_label_text(label) or fallback.replace("_", " ").title(),
                name=_slug(label, fallback),
                confidence=confidence,
                rationale=rationale,
                source=source,
                multiline=multiline,
            )
        )

    for line in lines:
        classification = _classify_label(line.text)
        if classification is None:
            continue
        kind, base_confidence, multiline = classification
        graphic = _nearest_graphic_for_label(line, graphics, page_rect)
        if graphic is not None:
            used_graphics.add(id(graphic))
            used_graphic_rects.append(graphic.fitz_rect)
            rect = _field_rect_from_graphic(
                graphic, kind, page_rect, multiline=multiline
            )
            geometry_bonus = 0.08 if graphic.kind == "box" else 0.05
            add_suggestion(
                kind,
                rect,
                line.text,
                min(base_confidence, line.confidence + 0.05) + geometry_bonus,
                f"Recognised label paired with a nearby {graphic.kind}.",
                f"{line.source}+{graphic.source}",
                multiline,
            )
        else:
            rect = _fallback_rect(line, kind, page_rect, multiline=multiline)
            if rect is not None:
                add_suggestion(
                    kind,
                    rect,
                    line.text,
                    min(base_confidence, line.confidence) - 0.12,
                    "Recognised form label; answer area was inferred for review.",
                    line.source,
                    multiline,
                )

    def graphic_was_consumed(graphic: GraphicPrimitive) -> bool:
        if id(graphic) in used_graphics:
            return True
        rect = graphic.fitz_rect
        for used in used_graphic_rects:
            if graphic.kind == "hline":
                if (used.x0 - 4.0 <= rect.x0 <= used.x1 + 4.0
                        and used.x0 - 4.0 <= rect.x1 <= used.x1 + 4.0
                        and used.y0 - 4.0 <= rect.y0 <= used.y1 + 4.0):
                    return True
            elif _intersection_ratio(rect, used) >= 0.55:
                return True
        return False

    # Unassociated outlined boxes are useful, especially checkboxes on scans.
    for graphic in graphics:
        if graphic_was_consumed(graphic) or graphic.kind != "box":
            continue
        rect = graphic.fitz_rect
        ratio = rect.width / max(rect.height, 1e-6)
        nearby = _nearby_label_for_box(rect, lines)
        label = nearby.text if nearby else "Checkbox"
        if 0.70 <= ratio <= 1.35 and 8.0 <= rect.width <= 32.0 and 8.0 <= rect.height <= 32.0:
            add_suggestion(
                "checkbox",
                rect,
                label,
                0.82 if nearby else 0.68,
                "Detected a small outlined square" + (" beside a label." if nearby else "."),
                graphic.source,
            )
        elif ratio >= 2.2 and rect.width >= 65.0 and rect.height <= 45.0:
            add_suggestion(
                "text",
                _field_rect_from_graphic(graphic, "text", page_rect, multiline=False),
                nearby.text if nearby else "Text field",
                0.76 if nearby else 0.63,
                "Detected an empty outlined answer box" + (" beside a label." if nearby else "."),
                graphic.source,
            )

    # Long unassociated underlines with a nearby label are plausible text fields.
    for graphic in graphics:
        if graphic_was_consumed(graphic) or graphic.kind != "hline":
            continue
        rect = graphic.fitz_rect
        if rect.width < 65.0 or rect.width > page_rect.width * 0.75:
            continue
        nearby = _nearby_label_for_box(
            fitz.Rect(rect.x0, rect.y0 - 18.0, rect.x1, rect.y1 + 2.0), lines
        )
        if nearby is None:
            continue
        add_suggestion(
            "text",
            _field_rect_from_graphic(graphic, "text", page_rect, multiline=False),
            nearby.text,
            0.69,
            "Detected a labelled blank line.",
            graphic.source,
        )

    # Deduplicate overlapping suggestions, keeping the most confident one.
    result: list[FieldSuggestion] = []
    for candidate in sorted(raw, key=lambda item: item.confidence, reverse=True):
        candidate_rect = fitz.Rect(candidate.rect)
        duplicate = False
        for existing_suggestion in result:
            existing_rect = fitz.Rect(existing_suggestion.rect)
            same_label = _slug(candidate.label) == _slug(existing_suggestion.label)
            centers_close = (
                abs((candidate_rect.x0 + candidate_rect.x1) / 2.0
                    - (existing_rect.x0 + existing_rect.x1) / 2.0) <= 70.0
                and abs((candidate_rect.y0 + candidate_rect.y1) / 2.0
                        - (existing_rect.y0 + existing_rect.y1) / 2.0) <= 40.0
            )
            if _iou(candidate_rect, existing_rect) >= 0.58 or (same_label and centers_close):
                duplicate = True
                break
        if not duplicate:
            result.append(candidate)

    result.sort(key=lambda item: (item.page, item.rect[1], item.rect[0]))
    # Stable IDs after sorting improve UI refresh behaviour.
    stable: list[FieldSuggestion] = []
    for index, item in enumerate(result, 1):
        stable.append(
            FieldSuggestion(
                suggestion_id=f"p{page_number + 1}_{index}",
                page=item.page,
                kind=item.kind,
                rect=item.rect,
                label=item.label,
                name=item.name,
                confidence=item.confidence,
                rationale=item.rationale,
                source=item.source,
                multiline=item.multiline,
            )
        )
    return stable


def create_fields_from_suggestions(
    document: fitz.Document,
    suggestions: Sequence[FieldSuggestion | dict[str, Any]],
) -> tuple[list[tuple[int, int]], list[str]]:
    """Create approved suggestions as genuine AcroForm widgets.

    This is intentionally separate from detection: callers decide which
    suggestions were reviewed and approved.  Partial failures are returned
    without hiding successfully created fields.
    """
    from form_designer_core import (
        add_checkbox_field,
        add_date_field,
        add_signature_field,
        add_text_field,
        unique_field_name,
    )

    created: list[tuple[int, int]] = []
    failures: list[str] = []
    for suggestion in suggestions:
        record = suggestion.as_record() if isinstance(suggestion, FieldSuggestion) else dict(suggestion)
        label = str(record.get("label") or record.get("name") or "Field").strip()
        try:
            page_number = int(record.get("page", 0))
            if not 0 <= page_number < document.page_count:
                raise ValueError(f"Page {page_number + 1} does not exist.")
            rect = fitz.Rect(record.get("rect", (0, 0, 0, 0)))
            if rect.is_empty:
                raise ValueError("Suggested rectangle is empty.")
            kind = str(record.get("kind", "text"))
            base_name = str(record.get("name") or kind or "field")
            name = unique_field_name(document, base_name)
            if kind == "checkbox":
                widget = add_checkbox_field(document, page_number, rect, name=name)
            elif kind == "date":
                widget = add_date_field(document, page_number, rect, name=name)
            elif kind == "signature":
                widget = add_signature_field(
                    document, page_number, rect, name=name, initials=False
                )
            elif kind == "initials":
                widget = add_signature_field(
                    document, page_number, rect, name=name, initials=True
                )
            else:
                widget = add_text_field(
                    document,
                    page_number,
                    rect,
                    name=name,
                    multiline=bool(record.get("multiline", False)),
                )
            if label:
                # PyMuPDF may return an annotation object whose page binding is
                # invalidated after subsequent widget creation. Set the tooltip
                # directly on the PDF object instead of relying on Widget.update().
                document.xref_set_key(
                    int(widget.xref), "TU", fitz.get_pdf_str(label)
                )
            created.append((page_number, int(widget.xref)))
        except Exception as exc:
            failures.append(f"{label}: {exc}")
    return created, failures
