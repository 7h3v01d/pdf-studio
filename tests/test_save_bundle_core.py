from __future__ import annotations

from pathlib import Path

import pytest

from save_bundle_core import (
    StagedOperation,
    cleanup_staged_operations,
    commit_staged_operations,
    stage_json_payload,
)


def test_save_bundle_commits_replacement_creation_and_deletion(tmp_path):
    pdf = tmp_path / "document.pdf"
    annotations = tmp_path / "document.pdf.annotations.json"
    bookmarks = tmp_path / "document.pdf.bookmarks.json"
    pdf.write_bytes(b"OLD-PDF")
    annotations.write_text("old", encoding="utf-8")
    bookmarks.write_text("obsolete", encoding="utf-8")

    staged_pdf = tmp_path / ".staged.pdf"
    staged_pdf.write_bytes(b"NEW-PDF")
    operations = [
        StagedOperation(pdf, staged_pdf),
        stage_json_payload(annotations, {"0": [[10, 20, "note"]]}),
        stage_json_payload(bookmarks, []),
    ]
    try:
        commit_staged_operations(operations)
    finally:
        cleanup_staged_operations(operations)

    assert pdf.read_bytes() == b"NEW-PDF"
    assert "note" in annotations.read_text(encoding="utf-8")
    assert not bookmarks.exists()


def test_save_bundle_rolls_back_every_destination_after_late_failure(tmp_path):
    pdf = tmp_path / "document.pdf"
    sidecar = tmp_path / "document.pdf.annotations.json"
    pdf.write_bytes(b"ORIGINAL-PDF")
    sidecar.write_text("ORIGINAL-SIDECAR", encoding="utf-8")

    staged_pdf = tmp_path / ".staged.pdf"
    staged_pdf.write_bytes(b"NEW-PDF")
    missing = tmp_path / ".missing.json"
    operations = [
        StagedOperation(pdf, staged_pdf),
        StagedOperation(sidecar, missing),
    ]

    with pytest.raises(FileNotFoundError):
        commit_staged_operations(operations)

    assert pdf.read_bytes() == b"ORIGINAL-PDF"
    assert sidecar.read_text(encoding="utf-8") == "ORIGINAL-SIDECAR"


def test_invalid_json_payload_does_not_touch_existing_sidecar(tmp_path):
    destination = tmp_path / "document.pdf.markup.json"
    destination.write_text("ORIGINAL", encoding="utf-8")

    with pytest.raises(TypeError):
        stage_json_payload(destination, {"bad": object()})

    assert destination.read_text(encoding="utf-8") == "ORIGINAL"


def test_save_bundle_rolls_back_a_deleted_sidecar_after_late_failure(tmp_path):
    obsolete = tmp_path / "document.pdf.bookmarks.json"
    later = tmp_path / "document.pdf.markup.json"
    obsolete.write_text("OLD-BOOKMARKS", encoding="utf-8")
    later.write_text("OLD-MARKUP", encoding="utf-8")
    missing = tmp_path / ".missing-stage"

    operations = [
        StagedOperation(obsolete, None),
        StagedOperation(later, missing),
    ]
    with pytest.raises(FileNotFoundError):
        commit_staged_operations(operations)

    assert obsolete.read_text(encoding="utf-8") == "OLD-BOOKMARKS"
    assert later.read_text(encoding="utf-8") == "OLD-MARKUP"


def test_incomplete_rollback_preserves_recovery_backup_and_reports_failure(
    tmp_path, monkeypatch
):
    import json
    import os
    import shutil
    import save_bundle_core
    from save_bundle_core import SaveBundleRollbackIncomplete

    pdf = tmp_path / "document.pdf"
    sidecar = tmp_path / "document.pdf.annotations.json"
    pdf.write_bytes(b"ORIGINAL-PDF")
    sidecar.write_text("ORIGINAL-SIDECAR", encoding="utf-8")
    staged_pdf = tmp_path / ".staged.pdf"
    staged_sidecar = tmp_path / ".staged.json"
    staged_pdf.write_bytes(b"NEW-PDF")
    staged_sidecar.write_text("NEW-SIDECAR", encoding="utf-8")
    operations = [
        StagedOperation(pdf, staged_pdf),
        StagedOperation(sidecar, staged_sidecar),
    ]

    real_replace = os.replace
    call_count = 0

    def fault_injected_replace(source, destination):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("injected second commit failure")
        if call_count == 3:
            raise OSError("injected PDF restoration failure")
        return real_replace(source, destination)

    monkeypatch.setattr(save_bundle_core.os, "replace", fault_injected_replace)

    with pytest.raises(SaveBundleRollbackIncomplete) as caught:
        commit_staged_operations(operations)

    error = caught.value
    try:
        assert isinstance(error.original_error, OSError)
        assert len(error.failures) == 1
        assert error.failures[0].destination == pdf.resolve()
        assert error.recovery_directory.is_dir()
        assert error.failures[0].recovery_backup is not None
        assert error.failures[0].recovery_backup.read_bytes() == b"ORIGINAL-PDF"
        assert pdf.read_bytes() == b"NEW-PDF"
        assert sidecar.read_text(encoding="utf-8") == "ORIGINAL-SIDECAR"

        manifest = json.loads(
            (error.recovery_directory / "recovery_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        assert manifest["original_error"]["message"] == "injected second commit failure"
        assert manifest["rollback_failures"][0]["destination"] == str(pdf.resolve())
        assert (error.recovery_directory / "RECOVERY_README.txt").is_file()
    finally:
        shutil.rmtree(error.recovery_directory, ignore_errors=True)
        cleanup_staged_operations(operations)


def test_incomplete_rollback_attempts_every_restoration(tmp_path, monkeypatch):
    import os
    import shutil
    import save_bundle_core
    from save_bundle_core import SaveBundleRollbackIncomplete

    first = tmp_path / "first.pdf"
    second = tmp_path / "second.json"
    third = tmp_path / "third.json"
    first.write_bytes(b"FIRST-OLD")
    second.write_bytes(b"SECOND-OLD")
    third.write_bytes(b"THIRD-OLD")
    stages = []
    operations = []
    for destination, payload in (
        (first, b"FIRST-NEW"),
        (second, b"SECOND-NEW"),
        (third, b"THIRD-NEW"),
    ):
        staged = tmp_path / f".{destination.name}.stage"
        staged.write_bytes(payload)
        stages.append(staged)
        operations.append(StagedOperation(destination, staged))

    real_replace = os.replace
    call_count = 0

    def fault_injected_replace(source, destination):
        nonlocal call_count
        call_count += 1
        if call_count == 3:  # third commit
            raise OSError("third commit failed")
        if call_count == 4:  # rollback of second destination
            raise OSError("second restore failed")
        return real_replace(source, destination)

    monkeypatch.setattr(save_bundle_core.os, "replace", fault_injected_replace)

    with pytest.raises(SaveBundleRollbackIncomplete) as caught:
        commit_staged_operations(operations)

    error = caught.value
    try:
        # Rollback continued after the second destination failed, restoring first.
        assert first.read_bytes() == b"FIRST-OLD"
        assert second.read_bytes() == b"SECOND-NEW"
        assert third.read_bytes() == b"THIRD-OLD"
        assert [failure.destination for failure in error.failures] == [second.resolve()]
        originals = sorted(error.recovery_directory.glob("*.original"))
        assert len(originals) == 3
    finally:
        shutil.rmtree(error.recovery_directory, ignore_errors=True)
        cleanup_staged_operations(operations)


def test_complete_rollback_removes_temporary_recovery_directory(tmp_path):
    before = set(tmp_path.glob(".pdfstudio-recovery-*"))
    original = tmp_path / "document.pdf"
    later = tmp_path / "sidecar.json"
    original.write_bytes(b"ORIGINAL")
    staged = tmp_path / ".new.pdf"
    staged.write_bytes(b"NEW")
    operations = [
        StagedOperation(original, staged),
        StagedOperation(later, tmp_path / ".missing"),
    ]

    with pytest.raises(FileNotFoundError):
        commit_staged_operations(operations)

    assert original.read_bytes() == b"ORIGINAL"
    assert set(tmp_path.glob(".pdfstudio-recovery-*")) == before


def test_durable_copy_fsyncs_a_writable_destination_handle(tmp_path, monkeypatch):
    import os
    import save_bundle_core

    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"durable-copy")

    real_fsync = os.fsync
    access_modes = []

    def recording_fsync(fd):
        # A zero-length write is harmless but proves the descriptor is writable.
        os.write(fd, b"")
        access_modes.append("writable")
        return real_fsync(fd)

    monkeypatch.setattr(save_bundle_core.os, "fsync", recording_fsync)
    save_bundle_core._copy_file_durable(source, destination)

    assert destination.read_bytes() == b"durable-copy"
    assert access_modes == ["writable"]


def test_successful_commit_reports_residual_recovery_copies(tmp_path, monkeypatch):
    import save_bundle_core
    from save_bundle_core import SaveBundleRecoveryCleanupIncomplete

    recovery_root = tmp_path / "appdata" / "recovery"
    monkeypatch.setattr(
        save_bundle_core,
        "recovery_root_directory",
        lambda: recovery_root,
    )

    destination = tmp_path / "redacted.pdf"
    destination.write_bytes(b"ORIGINAL-SENSITIVE")
    staged = tmp_path / ".redacted.stage"
    staged.write_bytes(b"NEW-REDACTED")

    real_rmtree = save_bundle_core.shutil.rmtree

    def locked_cleanup(path, *args, **kwargs):
        if Path(path).resolve().parent == recovery_root.resolve():
            raise PermissionError("injected antivirus lock")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(save_bundle_core.shutil, "rmtree", locked_cleanup)

    with pytest.raises(SaveBundleRecoveryCleanupIncomplete) as caught:
        commit_staged_operations([StagedOperation(destination, staged)])

    error = caught.value
    assert error.save_committed is True
    assert destination.read_bytes() == b"NEW-REDACTED"
    assert error.recovery_directory.parent == recovery_root.resolve()
    originals = list(error.recovery_directory.glob("*.original"))
    assert len(originals) == 1
    assert originals[0].read_bytes() == b"ORIGINAL-SENSITIVE"
    assert (error.recovery_directory / "RECOVERY_README.txt").is_file()
    assert "commit_succeeded_cleanup_incomplete" in (
        error.recovery_directory / "recovery_manifest.json"
    ).read_text(encoding="utf-8")

    monkeypatch.setattr(save_bundle_core.shutil, "rmtree", real_rmtree)
    assert save_bundle_core.retry_recovery_cleanup(
        error.recovery_directory, attempts=1, delay_seconds=0
    ) == ()
    assert not error.recovery_directory.exists()


def test_recovery_cleanup_refuses_unowned_directory(tmp_path):
    from save_bundle_core import retry_recovery_cleanup

    unrelated = tmp_path / ("transaction-" + "0" * 32)
    unrelated.mkdir()
    (unrelated / "user.pdf").write_bytes(b"not-owned")
    with pytest.raises(ValueError, match="unowned"):
        retry_recovery_cleanup(unrelated, attempts=1, delay_seconds=0)
    assert unrelated.exists()


def test_recovery_directory_uses_controlled_application_data_root(tmp_path, monkeypatch):
    import save_bundle_core

    appdata = tmp_path / "LocalAppData"
    monkeypatch.setattr(
        save_bundle_core,
        "application_data_dir",
        lambda: appdata / "PDFStudio",
    )
    directory = save_bundle_core._create_recovery_directory()
    try:
        assert directory.parent == (appdata / "PDFStudio" / "recovery").resolve()
        assert directory.name.startswith("transaction-")
        assert len(directory.name.removeprefix("transaction-")) == 32
        assert save_bundle_core._is_owned_recovery_directory(directory)
    finally:
        import shutil
        shutil.rmtree(directory, ignore_errors=True)
