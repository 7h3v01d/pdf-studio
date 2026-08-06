"""Single-source-of-truth helpers for PDF annotations and sidecar state."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Iterable, Mapping, Sequence

import fitz


def note_identity(x: float, y: float, text: str) -> tuple[int, int, str]:
    """Return a stable-enough migration identity for legacy sticky-note tuples."""
    return (round(float(x)), round(float(y)), str(text or ""))


def native_text_note_identities(document: fitz.Document | None) -> set[tuple[int, int, int, str]]:
    """Collect page-bound identities for native PDF text-note annotations."""
    identities: set[tuple[int, int, int, str]] = set()
    if document is None or document.is_closed:
        return identities
    for page_number in range(document.page_count):
        page = document.load_page(page_number)
        for annotation in page.annots() or []:
            if annotation.type[0] != fitz.PDF_ANNOT_TEXT:
                continue
            position = annotation.rect.top_left
            content = annotation.info.get("content", "")
            x, y, text = note_identity(position.x, position.y, content)
            identities.add((page_number, x, y, text))
    return identities


def filter_legacy_sidecar_notes(
    sidecar_notes: Mapping[int | str, Iterable[Sequence]],
    document: fitz.Document | None,
) -> dict[int, list[tuple[float, float, str]]]:
    """Keep only notes not already represented by a native PDF annotation.

    This migrates old releases without rendering or listing the same annotation
    twice.  Remaining entries are pending sidecar notes and become native on the
    next successful save.
    """
    native = native_text_note_identities(document)
    native_by_page_text: dict[tuple[int, str], list[tuple[int, int]]] = {}
    for page_number, x, y, text in native:
        native_by_page_text.setdefault((page_number, text), []).append((x, y))
    result: dict[int, list[tuple[float, float, str]]] = {}
    for raw_page, items in (sidecar_notes or {}).items():
        try:
            page_number = int(raw_page)
        except (TypeError, ValueError):
            continue
        for item in items or []:
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            try:
                x = float(item[0])
                y = float(item[1])
            except (TypeError, ValueError):
                continue
            text = str(item[2] or "")
            ix, iy, itext = note_identity(x, y, text)
            native_positions = native_by_page_text.get((page_number, itext), [])
            if any(abs(nx - ix) <= 2 and abs(ny - iy) <= 2
                   for nx, ny in native_positions):
                continue
            result.setdefault(page_number, []).append((x, y, text))
    return result


def pending_markup_only(
    markup: Mapping[int | str, Iterable[dict]],
) -> dict[int, list[dict]]:
    """Return only deferred markup that has not already been baked natively."""
    result: dict[int, list[dict]] = {}
    for raw_page, strokes in (markup or {}).items():
        try:
            page_number = int(raw_page)
        except (TypeError, ValueError):
            continue
        pending = []
        for stroke in strokes or []:
            if not isinstance(stroke, dict):
                continue
            if stroke.get("type") in ("signature", "stamp"):
                continue
            if stroke.get("baked"):
                continue
            pending.append(dict(stroke))
        if pending:
            result[page_number] = pending
    return result


def atomic_write_json(path: str | os.PathLike[str], payload) -> None:
    """Atomically replace a JSON sidecar, or delete it when payload is empty."""
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if payload in ({}, [], None):
        destination.unlink(missing_ok=True)
        return
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.pdfstudio-",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def retire_baked_sidecar_state(
    annotations: Mapping[int, Iterable[Sequence]],
    markup_strokes: Mapping[int, Iterable[dict]],
) -> tuple[dict, dict[int, list[dict]]]:
    """Return post-save sidecar state after native-compatible content is baked."""
    # Every sticky note is native-compatible and is inserted during save.
    return {}, pending_markup_only(markup_strokes)
