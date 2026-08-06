"""Transactional PDF job primitives used by background workers.

The functions in this module contain no Qt code.  They stage output, validate it,
cooperate with cancellation, and only replace user destinations after a complete
successful operation.
"""
from __future__ import annotations

from contextlib import ExitStack
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable, Iterable, Sequence

import fitz

from document_integrity_core import (
    DocumentIntegrityError,
    sibling_staged_path,
    validate_pdf_file,
)

ProgressCallback = Callable[[int, str], None]
CancelledCallback = Callable[[], bool]


class JobCancelled(InterruptedError):
    """Raised when a cooperative background operation is cancelled."""


def _emit(progress: ProgressCallback | None, percentage: int, message: str) -> None:
    if progress is not None:
        progress(max(0, min(100, int(percentage))), message)


def _check_cancelled(cancelled: CancelledCallback | None) -> None:
    if cancelled is not None and cancelled():
        raise JobCancelled("Operation cancelled.")


def _open_pdf(path: str | os.PathLike[str]) -> fitz.Document:
    try:
        document = fitz.open(str(path))
    except Exception as exc:
        raise DocumentIntegrityError(f"Could not open PDF '{path}': {exc}") from exc
    if document.needs_pass:
        document.close()
        raise DocumentIntegrityError(
            f"Password-protected input is not supported by this operation: {path}"
        )
    if document.page_count < 1:
        document.close()
        raise DocumentIntegrityError(f"Input PDF has no pages: {path}")
    return document


def merge_pdfs_atomic(
    input_paths: Sequence[str | os.PathLike[str]],
    output_path: str | os.PathLike[str],
    *,
    progress: ProgressCallback | None = None,
    cancelled: CancelledCallback | None = None,
) -> str:
    """Merge PDFs into one validated staged file, then atomically commit it."""
    paths = [Path(path).expanduser().resolve() for path in input_paths]
    if len(paths) < 2:
        raise ValueError("At least two input PDFs are required.")
    destination = Path(output_path).expanduser().resolve()
    expected_pages = 0

    with sibling_staged_path(destination) as staged:
        merged = fitz.open()
        try:
            for index, path in enumerate(paths):
                _check_cancelled(cancelled)
                _emit(
                    progress,
                    int(index / len(paths) * 85),
                    f"Adding: {path.name}",
                )
                source = _open_pdf(path)
                try:
                    expected_pages += source.page_count
                    merged.insert_pdf(source)
                finally:
                    source.close()
            _check_cancelled(cancelled)
            _emit(progress, 90, "Writing staged PDF...")
            merged.save(str(staged), garbage=3, deflate=True)
        finally:
            merged.close()

        _check_cancelled(cancelled)
        validate_pdf_file(staged, expected_pages=expected_pages)
        _check_cancelled(cancelled)
        os.replace(staged, destination)

    _emit(progress, 100, "Done")
    return str(destination)


def extract_pages_atomic(
    input_path: str | os.PathLike[str],
    page_indices: Sequence[int],
    output_path: str | os.PathLike[str],
    *,
    progress: ProgressCallback | None = None,
    cancelled: CancelledCallback | None = None,
) -> str:
    """Extract selected pages into one validated PDF and atomically commit it."""
    indices = [int(index) for index in page_indices]
    if not indices:
        raise ValueError("At least one page must be selected.")
    destination = Path(output_path).expanduser().resolve()
    source = _open_pdf(input_path)
    try:
        for index in indices:
            if index < 0 or index >= source.page_count:
                raise ValueError(f"Page {index + 1} is outside the source PDF.")
        with sibling_staged_path(destination) as staged:
            output = fitz.open()
            try:
                for position, page_number in enumerate(indices):
                    _check_cancelled(cancelled)
                    _emit(
                        progress,
                        int(position / len(indices) * 85),
                        f"Extracting page {page_number + 1}...",
                    )
                    output.insert_pdf(
                        source,
                        from_page=page_number,
                        to_page=page_number,
                    )
                _check_cancelled(cancelled)
                _emit(progress, 90, "Writing staged PDF...")
                output.save(str(staged), garbage=3, deflate=True)
            finally:
                output.close()

            _check_cancelled(cancelled)
            validate_pdf_file(staged, expected_pages=len(indices))
            _check_cancelled(cancelled)
            os.replace(staged, destination)
    finally:
        source.close()

    _emit(progress, 100, "Done")
    return str(destination)


def _validate_chunks(chunks: Iterable[tuple[int, int]], page_count: int) -> list[tuple[int, int]]:
    validated: list[tuple[int, int]] = []
    for start, end in chunks:
        start = int(start)
        end = int(end)
        if start < 0 or end < start or end >= page_count:
            raise ValueError(
                f"Invalid split range {start + 1}-{end + 1} for {page_count} pages."
            )
        validated.append((start, end))
    if not validated:
        raise ValueError("The split operation produced no page ranges.")
    return validated


def commit_staged_file_set(
    staged_to_destination: Sequence[tuple[Path, Path]],
) -> list[str]:
    """Commit several staged files with rollback of replaced destinations.

    The files are individually replaced atomically.  If a later replacement
    fails, earlier replacements are rolled back from sibling backups and newly
    created destinations are removed.
    """
    pairs = [(Path(staged), Path(destination)) for staged, destination in staged_to_destination]
    backups: dict[Path, Path] = {}
    committed: list[Path] = []
    with ExitStack() as stack:
        backup_dir = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="pdfstudio-backup-")))
        try:
            for sequence, (staged, destination) in enumerate(pairs):
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    backup = backup_dir / f"{sequence:04d}-{destination.name}"
                    shutil.copy2(destination, backup)
                    backups[destination] = backup
                os.replace(staged, destination)
                committed.append(destination)
        except Exception:
            for destination in reversed(committed):
                backup = backups.get(destination)
                try:
                    if backup is not None and backup.exists():
                        os.replace(backup, destination)
                    else:
                        destination.unlink(missing_ok=True)
                except OSError:
                    # Preserve the original exception. A best-effort rollback
                    # failure is still safer than masking the commit failure.
                    pass
            raise
    return [str(path) for path in committed]


def split_pdf_transactional(
    input_path: str | os.PathLike[str],
    output_dir: str | os.PathLike[str],
    chunks: Iterable[tuple[int, int]],
    *,
    progress: ProgressCallback | None = None,
    cancelled: CancelledCallback | None = None,
) -> list[str]:
    """Stage and validate every split part before committing the page set."""
    source_path = Path(input_path).expanduser().resolve()
    destination_dir = Path(output_dir).expanduser().resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    source = _open_pdf(source_path)
    try:
        ranges = _validate_chunks(chunks, source.page_count)
        base = source_path.stem
        with tempfile.TemporaryDirectory(
            prefix=f".{base}.pdfstudio-split-",
            dir=str(destination_dir),
        ) as temporary:
            temporary_dir = Path(temporary)
            staged_pairs: list[tuple[Path, Path]] = []
            for index, (start, end) in enumerate(ranges):
                _check_cancelled(cancelled)
                _emit(
                    progress,
                    int(index / len(ranges) * 80),
                    f"Writing part {index + 1}/{len(ranges)}...",
                )
                staged = temporary_dir / f"part-{index + 1:04d}.pdf"
                destination = destination_dir / f"{base}_part{index + 1:03d}.pdf"
                part = fitz.open()
                try:
                    part.insert_pdf(source, from_page=start, to_page=end)
                    part.save(str(staged), garbage=3, deflate=True)
                finally:
                    part.close()
                validate_pdf_file(staged, expected_pages=end - start + 1)
                staged_pairs.append((staged, destination))

            _check_cancelled(cancelled)
            _emit(progress, 90, "Committing completed parts...")
            outputs = commit_staged_file_set(staged_pairs)
    finally:
        source.close()

    _emit(progress, 100, "Done")
    return outputs
