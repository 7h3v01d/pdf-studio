"""Atomic commit primitives for a PDF and its JSON sidecar files.

The bundle commit is deliberately fail-closed. Existing destinations are copied
into a durable, application-owned recovery directory before any mutation. If
commit fails, every completed mutation is rolled back. Recovery data is removed
only after cleanup is verified; any residual recovery copy is reported rather
than silently ignored.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Any, Iterable
import uuid

from runtime_support import application_data_dir


_RECOVERY_OWNER = "PDF Studio save transaction"
_RECOVERY_SCHEMA = 2
_RECOVERY_DIR_RE = re.compile(r"^transaction-[0-9a-f]{32}$")


@dataclass(frozen=True)
class StagedOperation:
    """Replace ``destination`` from ``staged`` or delete it when staged is None."""

    destination: Path
    staged: Path | None


@dataclass(frozen=True)
class RollbackFailure:
    """One destination that could not be restored after a failed commit."""

    destination: Path
    action: str
    error: str
    recovery_backup: Path | None = None


class SaveBundleRollbackIncomplete(RuntimeError):
    """Raised when save commit fails and one or more rollback actions fail."""

    def __init__(
        self,
        *,
        original_error: BaseException,
        failures: Iterable[RollbackFailure],
        recovery_directory: Path,
    ) -> None:
        self.original_error = original_error
        self.failures = tuple(failures)
        self.recovery_directory = Path(recovery_directory).resolve()
        summary = "; ".join(
            f"{failure.destination} ({failure.action}: {failure.error})"
            for failure in self.failures
        )
        super().__init__(
            "Save commit failed and rollback was incomplete. "
            f"Recovery copies were preserved at {self.recovery_directory}. "
            f"Rollback failures: {summary or 'unknown'}. "
            f"Original error: {type(original_error).__name__}: {original_error}"
        )


class SaveBundleRecoveryCleanupIncomplete(RuntimeError):
    """Raised when a transaction outcome is known but recovery copies remain.

    ``save_committed`` distinguishes a successful save with residual original
    copies from a failed save whose rollback succeeded but whose redundant
    recovery directory could not be removed.
    """

    def __init__(
        self,
        *,
        recovery_directory: Path,
        residual_paths: Iterable[Path],
        save_committed: bool,
        committed_paths: Iterable[Path] = (),
        original_error: BaseException | None = None,
    ) -> None:
        self.recovery_directory = Path(recovery_directory).resolve()
        self.residual_paths = tuple(Path(path).resolve() for path in residual_paths)
        self.save_committed = bool(save_committed)
        self.committed_paths = tuple(Path(path).resolve() for path in committed_paths)
        self.original_error = original_error
        outcome = "The save committed" if self.save_committed else "The save failed and rollback completed"
        super().__init__(
            f"{outcome}, but recovery copies could not be removed from "
            f"{self.recovery_directory}."
        )


def recovery_root_directory() -> Path:
    """Return PDF Studio's controlled local recovery directory."""
    return application_data_dir() / "recovery"


def _create_recovery_directory() -> Path:
    root = recovery_root_directory()
    root.mkdir(parents=True, exist_ok=True)
    transaction_id = uuid.uuid4().hex
    directory = (root / f"transaction-{transaction_id}").resolve()
    directory.mkdir(mode=0o700)
    marker = directory / "transaction_owner.json"
    marker.write_text(
        json.dumps(
            {
                "schema_version": _RECOVERY_SCHEMA,
                "owner": _RECOVERY_OWNER,
                "transaction_id": transaction_id,
                "created_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return directory


def _ensure_owner_marker(directory: Path) -> None:
    """Recreate the ownership marker if a partial cleanup removed it."""
    transaction_id = directory.name.removeprefix("transaction-")
    if not _RECOVERY_DIR_RE.fullmatch(directory.name):
        return
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / "transaction_owner.json"
    marker.write_text(
        json.dumps(
            {
                "schema_version": _RECOVERY_SCHEMA,
                "owner": _RECOVERY_OWNER,
                "transaction_id": transaction_id,
                "created_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _is_owned_recovery_directory(path: Path) -> bool:
    try:
        candidate = path.expanduser().resolve()
        root = recovery_root_directory().expanduser().resolve()
    except OSError:
        return False
    if candidate.parent != root or not _RECOVERY_DIR_RE.fullmatch(candidate.name):
        return False
    marker = candidate / "transaction_owner.json"
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("owner") == _RECOVERY_OWNER
        and payload.get("transaction_id") == candidate.name.removeprefix("transaction-")
    )


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


def _copy_file_durable(source: Path, destination: Path) -> None:
    """Copy file content and flush it through a writable descriptor."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as source_handle, destination.open("wb") as target_handle:
        shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
        target_handle.flush()
        os.fsync(target_handle.fileno())


def _backup_name(index: int, destination: Path) -> str:
    safe_name = destination.name.replace(os.sep, "_")
    return f"{index:04d}-{safe_name}.original"


def _restore_backup_atomic(backup: Path, destination: Path) -> None:
    """Restore ``backup`` without consuming the durable recovery copy."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(
        prefix=f".{destination.name}.pdfstudio-restore-",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    restore_stage = Path(raw)
    os.close(fd)
    try:
        _copy_file_durable(backup, restore_stage)
        os.replace(restore_stage, destination)
    finally:
        restore_stage.unlink(missing_ok=True)


def _residual_paths(directory: Path) -> tuple[Path, ...]:
    if not directory.exists():
        return ()
    try:
        items = tuple(sorted(directory.rglob("*"), key=lambda item: str(item).lower()))
    except OSError:
        items = ()
    return items or (directory,)


def retry_recovery_cleanup(
    recovery_directory: str | os.PathLike[str],
    *,
    attempts: int = 3,
    delay_seconds: float = 0.05,
) -> tuple[Path, ...]:
    """Retry verified removal of one PDF Studio-owned recovery transaction."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds cannot be negative")
    directory = Path(recovery_directory)
    if not _is_owned_recovery_directory(directory):
        raise ValueError("Refusing to remove an unowned recovery directory.")
    for attempt in range(attempts):
        try:
            shutil.rmtree(directory)
        except OSError:
            pass
        if not directory.exists():
            return ()
        if attempt + 1 < attempts and delay_seconds:
            time.sleep(delay_seconds)
    return _residual_paths(directory)


def _write_recovery_manifest(
    recovery_directory: Path,
    *,
    status: str,
    operations: list[StagedOperation],
    backups: dict[Path, Path],
    original_error: BaseException | None = None,
    failures: list[RollbackFailure] | None = None,
    residual_paths: Iterable[Path] = (),
) -> None:
    """Best-effort human and machine-readable recovery instructions."""
    failures = failures or []
    try:
        _ensure_owner_marker(recovery_directory)
    except OSError:
        pass
    payload = {
        "schema_version": _RECOVERY_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "original_error": (
            {
                "type": type(original_error).__name__,
                "message": str(original_error),
            }
            if original_error is not None
            else None
        ),
        "operations": [
            {
                "destination": str(operation.destination.expanduser().resolve()),
                "intent": "delete" if operation.staged is None else "replace",
                "backup": (
                    str(backups[operation.destination.expanduser().resolve()])
                    if operation.destination.expanduser().resolve() in backups
                    else None
                ),
            }
            for operation in operations
        ],
        "rollback_failures": [
            {
                "destination": str(failure.destination),
                "action": failure.action,
                "error": failure.error,
                "recovery_backup": (
                    str(failure.recovery_backup)
                    if failure.recovery_backup is not None
                    else None
                ),
            }
            for failure in failures
        ],
        "residual_paths": [str(path) for path in residual_paths],
    }
    try:
        manifest = recovery_directory / "recovery_manifest.json"
        manifest.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        readme = recovery_directory / "RECOVERY_README.txt"
        if status == "commit_succeeded_cleanup_incomplete":
            instructions = (
                "PDF Studio saved the new files successfully, but original recovery "
                "copies could not be removed. These copies may contain sensitive "
                "pre-redaction content. Use PDF Studio's retry action or remove this "
                "directory after verifying the saved files.\n"
            )
        else:
            instructions = (
                "PDF Studio could not fully restore or clean a save transaction. "
                "Do not delete this directory until the affected PDF and sidecar "
                "files have been inspected. Original destination copies use the "
                "suffix '.original'.\n"
            )
        readme.write_text(
            instructions + "See recovery_manifest.json for destination mappings.\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _cleanup_or_raise(
    recovery_directory: Path,
    *,
    operations: list[StagedOperation],
    backups: dict[Path, Path],
    save_committed: bool,
    committed_paths: Iterable[Path],
    original_error: BaseException | None = None,
) -> None:
    residual = retry_recovery_cleanup(recovery_directory)
    if not residual:
        return
    status = (
        "commit_succeeded_cleanup_incomplete"
        if save_committed
        else "rollback_succeeded_cleanup_incomplete"
    )
    _write_recovery_manifest(
        recovery_directory,
        status=status,
        operations=operations,
        backups=backups,
        original_error=original_error,
        residual_paths=residual,
    )
    raise SaveBundleRecoveryCleanupIncomplete(
        recovery_directory=recovery_directory,
        residual_paths=_residual_paths(recovery_directory),
        save_committed=save_committed,
        committed_paths=committed_paths,
        original_error=original_error,
    ) from original_error


def commit_staged_operations(operations: Iterable[StagedOperation]) -> list[str]:
    """Commit a file set atomically as far as the host filesystem permits."""
    ops = [
        StagedOperation(
            operation.destination.expanduser().resolve(),
            operation.staged.expanduser().resolve()
            if operation.staged is not None
            else None,
        )
        for operation in operations
    ]
    destinations = [operation.destination for operation in ops]
    if len(set(destinations)) != len(destinations):
        raise ValueError("A save bundle contains duplicate destinations.")
    if not ops:
        return []
    for operation in ops:
        if operation.staged is not None and not operation.staged.is_file():
            raise FileNotFoundError(f"Staged file is missing: {operation.staged}")

    recovery_directory = _create_recovery_directory()
    backups: dict[Path, Path] = {}
    committed: list[Path] = []

    # Complete the full backup set before the first destination mutation.
    try:
        for index, destination in enumerate(destinations):
            if destination.exists():
                backup = recovery_directory / _backup_name(index, destination)
                _copy_file_durable(destination, backup)
                backups[destination] = backup
    except Exception as backup_error:
        _cleanup_or_raise(
            recovery_directory,
            operations=ops,
            backups=backups,
            save_committed=False,
            committed_paths=(),
            original_error=backup_error,
        )
        raise

    try:
        for operation in ops:
            destination = operation.destination
            destination.parent.mkdir(parents=True, exist_ok=True)
            if operation.staged is None:
                destination.unlink(missing_ok=True)
            else:
                os.replace(operation.staged, destination)
            committed.append(destination)
    except Exception as commit_error:
        rollback_failures: list[RollbackFailure] = []
        for destination in reversed(committed):
            backup = backups.get(destination)
            try:
                if backup is not None and backup.exists():
                    _restore_backup_atomic(backup, destination)
                else:
                    destination.unlink(missing_ok=True)
            except Exception as rollback_error:
                rollback_failures.append(RollbackFailure(
                    destination=destination,
                    action=(
                        "restore original"
                        if backup is not None
                        else "remove newly-created destination"
                    ),
                    error=f"{type(rollback_error).__name__}: {rollback_error}",
                    recovery_backup=backup,
                ))

        if rollback_failures:
            _write_recovery_manifest(
                recovery_directory,
                status="rollback_incomplete",
                original_error=commit_error,
                operations=ops,
                backups=backups,
                failures=rollback_failures,
            )
            raise SaveBundleRollbackIncomplete(
                original_error=commit_error,
                failures=rollback_failures,
                recovery_directory=recovery_directory,
            ) from commit_error

        _cleanup_or_raise(
            recovery_directory,
            operations=ops,
            backups=backups,
            save_committed=False,
            committed_paths=(),
            original_error=commit_error,
        )
        raise

    _cleanup_or_raise(
        recovery_directory,
        operations=ops,
        backups=backups,
        save_committed=True,
        committed_paths=committed,
    )
    return [str(path) for path in committed]
