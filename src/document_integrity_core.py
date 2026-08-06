"""Document-integrity primitives for destructive PDF operations.

This module intentionally contains no Qt code so transaction boundaries can be
exercised directly by pytest.  Callers stage and validate destructive work here,
then update the GUI only after a complete operation succeeds.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import math
import os
from pathlib import Path
import tempfile
from typing import Callable, Iterable, Mapping, Sequence
import uuid

import fitz


class DocumentIntegrityError(RuntimeError):
    """Raised when an operation would violate a document-integrity boundary."""


@dataclass(frozen=True)
class RedactionTarget:
    page_number: int
    rect: tuple[float, float, float, float]


def new_document_session_id() -> str:
    """Return an opaque identifier for one loaded-document session."""
    return uuid.uuid4().hex


def clone_pdf_document(document: fitz.Document) -> fitz.Document:
    """Create an independent in-memory clone preserving document-level data."""
    if document is None or document.is_closed:
        raise DocumentIntegrityError("The source PDF is not open.")
    payload = document.tobytes(
        garbage=3,
        deflate=True,
        encryption=fitz.PDF_ENCRYPT_KEEP,
    )
    clone = fitz.open(stream=payload, filetype="pdf")
    if clone.page_count != document.page_count:
        clone.close()
        raise DocumentIntegrityError("The staged PDF page count changed while cloning.")
    return clone


def _finite_rect(rect: fitz.Rect) -> bool:
    values = (rect.x0, rect.y0, rect.x1, rect.y1)
    return all(math.isfinite(float(value)) for value in values)


def validate_redaction_plan(
    document: fitz.Document,
    pending_redactions: Mapping[int, Iterable[fitz.Rect | Sequence[float]]],
    *,
    redaction_session_id: str,
    active_session_id: str,
) -> list[RedactionTarget]:
    """Validate and normalise every pending redaction before any mutation."""
    if document is None or document.is_closed:
        raise DocumentIntegrityError("No open PDF is available for redaction.")
    if not active_session_id or redaction_session_id != active_session_id:
        raise DocumentIntegrityError(
            "The pending redactions belong to a different document session."
        )

    plan: list[RedactionTarget] = []
    for raw_page, raw_rects in pending_redactions.items():
        try:
            page_number = int(raw_page)
        except (TypeError, ValueError) as exc:
            raise DocumentIntegrityError(
                f"Invalid redaction page reference: {raw_page!r}."
            ) from exc
        if page_number < 0 or page_number >= document.page_count:
            raise DocumentIntegrityError(
                f"Redaction page {page_number + 1} is outside this document."
            )

        page_rect = document.load_page(page_number).rect
        for raw_rect in raw_rects:
            try:
                rect = fitz.Rect(raw_rect)
            except Exception as exc:
                raise DocumentIntegrityError(
                    f"Invalid redaction rectangle on page {page_number + 1}."
                ) from exc
            rect.normalize()
            if rect.is_empty or rect.is_infinite or not _finite_rect(rect):
                raise DocumentIntegrityError(
                    f"Empty or non-finite redaction rectangle on page {page_number + 1}."
                )
            clipped = rect & page_rect
            if clipped.is_empty:
                raise DocumentIntegrityError(
                    f"Redaction rectangle does not intersect page {page_number + 1}."
                )
            plan.append(
                RedactionTarget(page_number, tuple(float(v) for v in clipped))
            )

    if not plan:
        raise DocumentIntegrityError("No valid redaction rectangles were supplied.")
    return plan


def apply_redactions_transactionally(
    document: fitz.Document,
    pending_redactions: Mapping[int, Iterable[fitz.Rect | Sequence[float]]],
    *,
    redaction_session_id: str,
    active_session_id: str,
) -> fitz.Document:
    """Apply a fully validated plan to a clone and return it on total success.

    The active document is never mutated.  The caller owns the returned document
    and must close it if it is not committed.
    """
    plan = validate_redaction_plan(
        document,
        pending_redactions,
        redaction_session_id=redaction_session_id,
        active_session_id=active_session_id,
    )
    staged = clone_pdf_document(document)
    try:
        by_page: dict[int, list[fitz.Rect]] = {}
        for target in plan:
            by_page.setdefault(target.page_number, []).append(fitz.Rect(target.rect))
        for page_number in sorted(by_page):
            page = staged.load_page(page_number)
            for rect in by_page[page_number]:
                annot = page.add_redact_annot(rect, fill=(0, 0, 0))
                annot.update()
            page.apply_redactions()
        if staged.page_count != document.page_count:
            raise DocumentIntegrityError(
                "The staged redaction result changed the document page count."
            )
        # Serialising and reopening catches malformed staged object graphs before
        # the live application commits them.
        verified = clone_pdf_document(staged)
        staged.close()
        return verified
    except Exception:
        staged.close()
        raise


@contextmanager
def sibling_staged_path(destination: str | os.PathLike[str], suffix: str = ".pdf"):
    """Yield a unique non-existent sibling path and clean it on failure."""
    destination_path = Path(destination).expanduser().resolve()
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_path = tempfile.mkstemp(
        prefix=f".{destination_path.stem}.pdfstudio-",
        suffix=suffix,
        dir=str(destination_path.parent),
    )
    os.close(fd)
    os.unlink(raw_path)  # PyMuPDF should create, not append to, the staged file.
    staged = Path(raw_path)
    try:
        yield staged
    finally:
        try:
            staged.unlink()
        except FileNotFoundError:
            pass


def validate_pdf_file(
    path: str | os.PathLike[str],
    *,
    expected_pages: int | None = None,
    password: str | None = None,
) -> None:
    """Open a generated PDF and reject malformed or implausible output."""
    pdf_path = Path(path)
    if not pdf_path.is_file() or pdf_path.stat().st_size < 5:
        raise DocumentIntegrityError("The generated PDF is missing or empty.")
    try:
        check = fitz.open(str(pdf_path))
    except Exception as exc:
        raise DocumentIntegrityError(f"The generated output is not a valid PDF: {exc}") from exc
    try:
        if check.needs_pass:
            if password is None or not check.authenticate(password):
                raise DocumentIntegrityError(
                    "The generated PDF is encrypted but could not be authenticated."
                )
        if check.page_count < 1:
            raise DocumentIntegrityError("The generated PDF has no pages.")
        if expected_pages is not None and check.page_count != expected_pages:
            raise DocumentIntegrityError(
                f"Expected {expected_pages} page(s), but generated {check.page_count}."
            )
        # Force page object parsing, not merely trailer parsing.
        for page_number in range(check.page_count):
            _ = check.load_page(page_number).rect
    finally:
        check.close()


def save_pdf_atomic(
    document: fitz.Document,
    destination: str | os.PathLike[str],
    *,
    save_kwargs: dict | None = None,
    validator: Callable[[str], None] | None = None,
) -> None:
    """Save, validate, and atomically replace a destination PDF."""
    destination_path = Path(destination).expanduser().resolve()
    kwargs = dict(save_kwargs or {})
    with sibling_staged_path(destination_path) as staged:
        document.save(str(staged), **kwargs)
        if validator is None:
            validate_pdf_file(staged, expected_pages=document.page_count)
        else:
            validator(str(staged))
        os.replace(staged, destination_path)


def flatten_form_atomic(
    document: fitz.Document,
    destination: str | os.PathLike[str],
    *,
    prepare_clone: Callable[[fitz.Document], None] | None = None,
) -> int:
    """Flatten widgets in an independent clone and atomically commit the copy."""
    staged_doc = clone_pdf_document(document)
    try:
        if prepare_clone is not None:
            prepare_clone(staged_doc)
        field_count = sum(
            len(list(staged_doc.load_page(page_no).widgets() or []))
            for page_no in range(staged_doc.page_count)
        )
        staged_doc.bake(annots=False, widgets=True)

        def _validate_flattened(path: str) -> None:
            validate_pdf_file(path, expected_pages=staged_doc.page_count)
            check = fitz.open(path)
            try:
                remaining = sum(
                    len(list(check.load_page(page_no).widgets() or []))
                    for page_no in range(check.page_count)
                )
            finally:
                check.close()
            if remaining:
                raise DocumentIntegrityError(
                    f"Flatten verification failed: {remaining} interactive field(s) remain."
                )

        save_pdf_atomic(
            staged_doc,
            destination,
            save_kwargs={"garbage": 4, "deflate": True},
            validator=_validate_flattened,
        )
        return field_count
    finally:
        staged_doc.close()


def insert_signature_image_once(
    document: fitz.Document,
    *,
    page_number: int,
    rect: fitz.Rect | Sequence[float],
    image_bytes: bytes | bytearray | memoryview,
) -> int:
    """Insert one signature image using the immediate-persistence model."""
    if not isinstance(image_bytes, (bytes, bytearray, memoryview)):
        raise TypeError("Signature image data must be bytes-like.")
    payload = bytes(image_bytes)
    if not payload:
        raise ValueError("Signature image data is empty.")
    if page_number < 0 or page_number >= document.page_count:
        raise IndexError("Signature page is outside the document.")
    target = fitz.Rect(rect)
    target.normalize()
    if target.is_empty or target.is_infinite or not _finite_rect(target):
        raise ValueError("Signature rectangle is invalid.")
    page = document.load_page(page_number)
    clipped = target & page.rect
    if clipped.is_empty:
        raise ValueError("Signature rectangle is outside the page.")
    return int(page.insert_image(clipped, stream=payload))


def snapshot_pdf_bytes(document: fitz.Document) -> bytes:
    """Serialise a validated in-memory snapshot for undoable native mutations."""
    if document is None or document.is_closed:
        raise DocumentIntegrityError("The PDF is not open.")
    payload = document.tobytes(
        garbage=3,
        deflate=True,
        encryption=fitz.PDF_ENCRYPT_KEEP,
    )
    check = fitz.open(stream=payload, filetype="pdf")
    try:
        if check.page_count != document.page_count:
            raise DocumentIntegrityError(
                "The PDF snapshot changed the document page count."
            )
        for page_number in range(check.page_count):
            _ = check.load_page(page_number).rect
    finally:
        check.close()
    return payload


def open_pdf_snapshot(payload: bytes | bytearray | memoryview) -> fitz.Document:
    """Open and validate a previously captured PDF snapshot."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("PDF snapshot data must be bytes-like.")
    document = fitz.open(stream=bytes(payload), filetype="pdf")
    try:
        if document.page_count < 1:
            raise DocumentIntegrityError("The PDF snapshot has no pages.")
        for page_number in range(document.page_count):
            _ = document.load_page(page_number).rect
    except Exception:
        document.close()
        raise
    return document
