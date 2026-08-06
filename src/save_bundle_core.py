"""Atomic commit primitives for a PDF and its JSON sidecar files."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable


@dataclass(frozen=True)
class StagedOperation:
    """Replace ``destination`` from ``staged`` or delete it when staged is None."""

    destination: Path
    staged: Path | None


def stage_json_payload(destination: str | os.PathLike[str], payload: Any) -> StagedOperation:
    """Serialise a JSON payload beside its destination without committing it."""
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if payload in ({}, [], None):
        return StagedOperation(target, None)
    fd, raw = tempfile.mkstemp(
        prefix=f".{target.name}.pdfstudio-stage-",
        suffix=".tmp",
        dir=str(target.parent),
    )
    staged = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        staged.unlink(missing_ok=True)
        raise
    return StagedOperation(target, staged)


def cleanup_staged_operations(operations: Iterable[StagedOperation]) -> None:
    for operation in operations:
        if operation.staged is not None:
            operation.staged.unlink(missing_ok=True)


def commit_staged_operations(operations: Iterable[StagedOperation]) -> list[str]:
    """Commit a file set with rollback of replaced, deleted, and new files."""
    ops = list(operations)
    destinations = [op.destination.expanduser().resolve() for op in ops]
    if len(set(destinations)) != len(destinations):
        raise ValueError("A save bundle contains duplicate destinations.")
    if not ops:
        return []

    backup_parent = destinations[0].parent
    backup_parent.mkdir(parents=True, exist_ok=True)
    backups: dict[Path, Path] = {}
    committed: list[Path] = []
    with tempfile.TemporaryDirectory(
        prefix=".pdfstudio-save-backup-", dir=str(backup_parent)
    ) as backup_raw:
        backup_dir = Path(backup_raw)
        try:
            for index, op in enumerate(ops):
                destination = op.destination.expanduser().resolve()
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    backup = backup_dir / f"{index:04d}-{destination.name}"
                    shutil.copy2(destination, backup)
                    backups[destination] = backup

                if op.staged is None:
                    destination.unlink(missing_ok=True)
                else:
                    staged = op.staged.expanduser().resolve()
                    if not staged.is_file():
                        raise FileNotFoundError(f"Staged file is missing: {staged}")
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
                    pass
            raise
    return [str(path) for path in committed]
