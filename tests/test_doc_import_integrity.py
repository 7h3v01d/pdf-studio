from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

import doc_import


def _write_valid_pdf(path: str, text: str = "converted") -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def _fake_run_factory(*, returncode: int, produce: str):
    def _run(cmd, **_kwargs):
        out_dir = cmd[cmd.index("--outdir") + 1]
        src = cmd[-1]
        produced = os.path.join(
            out_dir, os.path.splitext(os.path.basename(src))[0] + ".pdf"
        )
        if produce == "valid":
            _write_valid_pdf(produced)
        elif produce == "invalid":
            Path(produced).write_bytes(b"not a pdf")
        return SimpleNamespace(returncode=returncode, stdout="stdout", stderr="failure")
    return _run


def test_libreoffice_rejects_stale_target_when_process_fails(tmp_path, monkeypatch):
    src = tmp_path / "report.docx"
    src.write_text("source")
    target = tmp_path / "result.pdf"
    target.write_bytes(b"PREVIOUS TARGET")
    monkeypatch.setattr(doc_import, "_find_soffice", lambda: "soffice")
    monkeypatch.setattr(
        doc_import.subprocess,
        "run",
        _fake_run_factory(returncode=1, produce="valid"),
    )

    with pytest.raises(doc_import.ConversionError, match="reported a conversion failure"):
        doc_import._convert_libreoffice(str(src), str(target))
    assert target.read_bytes() == b"PREVIOUS TARGET"


def test_libreoffice_rejects_invalid_pdf_even_after_zero_returncode(tmp_path, monkeypatch):
    src = tmp_path / "report.docx"
    src.write_text("source")
    target = tmp_path / "result.pdf"
    monkeypatch.setattr(doc_import, "_find_soffice", lambda: "soffice")
    monkeypatch.setattr(
        doc_import.subprocess,
        "run",
        _fake_run_factory(returncode=0, produce="invalid"),
    )

    with pytest.raises(doc_import.ConversionError, match="not a valid PDF"):
        doc_import._convert_libreoffice(str(src), str(target))
    assert not target.exists()


def test_libreoffice_commits_only_valid_isolated_output(tmp_path, monkeypatch):
    src = tmp_path / "report.docx"
    src.write_text("source")
    target = tmp_path / "result.pdf"
    monkeypatch.setattr(doc_import, "_find_soffice", lambda: "soffice")
    monkeypatch.setattr(
        doc_import.subprocess,
        "run",
        _fake_run_factory(returncode=0, produce="valid"),
    )

    result = doc_import._convert_libreoffice(str(src), str(target))
    assert result == str(target)
    check = fitz.open(target)
    try:
        assert "converted" in check[0].get_text()
    finally:
        check.close()


def test_imported_pdf_default_path_uses_original_source_directory(tmp_path):
    from doc_import import imported_pdf_default_path

    source = tmp_path / "Quarterly Report.docx"
    assert imported_pdf_default_path(str(source)) == str(
        (tmp_path / "Quarterly Report.pdf").resolve()
    )


def test_cleanup_temporary_import_refuses_unowned_files(tmp_path):
    from doc_import import cleanup_temporary_import

    user_file = tmp_path / "pdfstudio_import_keep.pdf"
    user_file.write_bytes(b"user")
    assert cleanup_temporary_import(str(user_file)) is False
    assert user_file.exists()


def test_cleanup_temporary_import_removes_marker_owned_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(doc_import.tempfile, "gettempdir", lambda: str(tmp_path))
    workspace, candidate = doc_import._create_import_workspace()
    candidate.write_bytes(b"temporary")

    assert doc_import.cleanup_temporary_import(str(candidate)) is True
    assert not workspace.exists()


def test_filename_pattern_alone_does_not_establish_import_ownership(tmp_path, monkeypatch):
    monkeypatch.setattr(doc_import.tempfile, "gettempdir", lambda: str(tmp_path))
    lookalike = tmp_path / "pdfstudio_import_deadbeef.pdf"
    lookalike.write_bytes(b"unrelated")

    assert doc_import.cleanup_temporary_import(str(lookalike)) is False
    assert lookalike.exists()


def test_convert_failure_removes_partial_owned_cache(tmp_path, monkeypatch):
    source = tmp_path / "broken.docx"
    source.write_text("source", encoding="utf-8")
    monkeypatch.setattr(doc_import.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(doc_import, "_office_com_available", lambda _kind: False)
    monkeypatch.setattr(doc_import, "_find_soffice", lambda: "soffice")

    def partial_then_fail(_source, out_pdf):
        Path(out_pdf).write_bytes(b"PARTIAL")
        raise doc_import.ConversionError("validation failed")

    monkeypatch.setattr(doc_import, "_convert_libreoffice", partial_then_fail)

    with pytest.raises(doc_import.ConversionError, match="validation failed"):
        doc_import.convert_to_pdf(str(source))

    root = doc_import.import_cache_root(temp_root=tmp_path)
    assert not root.exists() or list(root.iterdir()) == []


def test_stale_import_cleanup_requires_marker_and_age(tmp_path, monkeypatch):
    now = 2_000_000.0
    monkeypatch.setattr(doc_import.tempfile, "gettempdir", lambda: str(tmp_path))

    old_workspace, old_output = doc_import._create_import_workspace()
    old_output.write_bytes(b"old-owned")
    fresh_workspace, fresh_output = doc_import._create_import_workspace()
    fresh_output.write_bytes(b"fresh-owned")

    old_marker = old_workspace / doc_import._IMPORT_MARKER
    fresh_marker = fresh_workspace / doc_import._IMPORT_MARKER
    os.utime(old_marker, (now - 10_000, now - 10_000))
    os.utime(fresh_marker, (now - 10, now - 10))

    fake_workspace = doc_import.import_cache_root() / ("f" * 32)
    fake_workspace.mkdir(parents=True)
    (fake_workspace / doc_import._IMPORT_OUTPUT).write_bytes(b"no-marker")
    os.utime(fake_workspace, (now - 10_000, now - 10_000))

    lookalike = tmp_path / "pdfstudio_import_deadbeef.pdf"
    lookalike.write_bytes(b"unrelated")
    os.utime(lookalike, (now - 10_000, now - 10_000))

    removed = doc_import.cleanup_stale_temporary_imports(
        max_age_seconds=1000,
        now=now,
    )

    assert removed == [str(old_workspace.resolve())]
    assert not old_workspace.exists()
    assert fresh_workspace.exists()
    assert fake_workspace.exists()
    assert lookalike.exists()


def test_stale_import_cleanup_rejects_negative_age():
    with pytest.raises(ValueError, match="cannot be negative"):
        doc_import.cleanup_stale_temporary_imports(max_age_seconds=-1)
