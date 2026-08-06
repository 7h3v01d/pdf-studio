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


def test_cleanup_temporary_import_removes_owned_cache_file():
    import tempfile
    from pathlib import Path
    from uuid import uuid4
    from doc_import import cleanup_temporary_import

    candidate = Path(tempfile.gettempdir()) / f"pdfstudio_import_{uuid4().hex[:8]}.pdf"
    candidate.write_bytes(b"temporary")
    try:
        assert cleanup_temporary_import(str(candidate)) is True
        assert not candidate.exists()
    finally:
        candidate.unlink(missing_ok=True)
