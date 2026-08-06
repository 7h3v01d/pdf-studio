"""Atomic helpers for generated DOCX and XLSX files."""
from __future__ import annotations

import os
from pathlib import Path
import zipfile

from document_integrity_core import DocumentIntegrityError, sibling_staged_path


_REQUIRED_MEMBERS = {
    "docx": {"[Content_Types].xml", "word/document.xml"},
    "xlsx": {"[Content_Types].xml", "xl/workbook.xml"},
}


def validate_ooxml_file(path: str | os.PathLike[str], kind: str) -> None:
    kind = kind.lower().lstrip(".")
    required = _REQUIRED_MEMBERS.get(kind)
    if required is None:
        raise ValueError(f"Unsupported OOXML kind: {kind}")
    source = Path(path)
    if not source.is_file() or source.stat().st_size < 64:
        raise DocumentIntegrityError(f"Generated {kind.upper()} is missing or empty.")
    try:
        with zipfile.ZipFile(source, "r") as archive:
            bad_member = archive.testzip()
            if bad_member is not None:
                raise DocumentIntegrityError(
                    f"Generated {kind.upper()} contains a corrupt member: {bad_member}"
                )
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise DocumentIntegrityError(
            f"Generated {kind.upper()} is not a valid OOXML archive."
        ) from exc
    missing = sorted(required - names)
    if missing:
        raise DocumentIntegrityError(
            f"Generated {kind.upper()} is missing: {', '.join(missing)}"
        )


def commit_ooxml_atomic(
    destination: str | os.PathLike[str],
    kind: str,
    producer,
) -> str:
    """Run ``producer(staged_path)``, validate, then atomically replace output."""
    destination_path = Path(destination).expanduser().resolve()
    suffix = destination_path.suffix or f".{kind.lower().lstrip('.')}"
    with sibling_staged_path(destination_path, suffix=suffix) as staged:
        producer(str(staged))
        validate_ooxml_file(staged, kind)
        os.replace(staged, destination_path)
    return str(destination_path)
