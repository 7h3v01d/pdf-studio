"""Pure geometry helpers for visual signature placement.

PDF Studio's signatures are visual ink/image stamps, not cryptographic PDF
signatures. These helpers let a visual signature snap into an unsigned PDF
signature field while preserving the real form field itself.
"""
from __future__ import annotations

from dataclasses import dataclass

import fitz


@dataclass(frozen=True)
class SignatureFieldTarget:
    xref: int
    rect: fitz.Rect


def unsigned_signature_field_at(
    document: fitz.Document,
    page_number: int,
    point: fitz.Point,
) -> SignatureFieldTarget | None:
    """Return the unsigned signature field containing *point*, if any."""
    if document is None or document.is_closed:
        return None
    if page_number < 0 or page_number >= document.page_count:
        return None
    page = document.load_page(page_number)
    for field in page.widgets() or []:
        if field.field_type != fitz.PDF_WIDGET_TYPE_SIGNATURE:
            continue
        if bool(getattr(field, "is_signed", False)):
            continue
        rect = fitz.Rect(field.rect)
        rect.normalize()
        if rect.contains(point):
            return SignatureFieldTarget(int(field.xref), rect)
    return None


def fit_signature_inside(
    field_rect: fitz.Rect,
    image_width: int,
    image_height: int,
    *,
    padding_fraction: float = 0.08,
) -> fitz.Rect:
    """Aspect-fit an image inside a signature field with modest padding."""
    rect = fitz.Rect(field_rect)
    rect.normalize()
    if rect.is_empty or rect.is_infinite:
        raise ValueError("Signature field rectangle is invalid.")
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Signature image dimensions must be positive.")

    padding_fraction = max(0.0, min(float(padding_fraction), 0.2))
    pad = min(rect.width, rect.height) * padding_fraction
    inner = fitz.Rect(
        rect.x0 + pad,
        rect.y0 + pad,
        rect.x1 - pad,
        rect.y1 - pad,
    )
    if inner.is_empty:
        inner = rect

    image_aspect = float(image_width) / float(image_height)
    target_w = inner.width
    target_h = target_w / image_aspect
    if target_h > inner.height:
        target_h = inner.height
        target_w = target_h * image_aspect

    cx = (inner.x0 + inner.x1) / 2.0
    cy = (inner.y0 + inner.y1) / 2.0
    return fitz.Rect(
        cx - target_w / 2.0,
        cy - target_h / 2.0,
        cx + target_w / 2.0,
        cy + target_h / 2.0,
    )
