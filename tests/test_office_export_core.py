from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from document_integrity_core import DocumentIntegrityError
from office_export_core import commit_ooxml_atomic, validate_ooxml_file


def _write_ooxml(path: str | Path, members: list[str]):
    with zipfile.ZipFile(path, "w") as archive:
        for member in members:
            archive.writestr(member, "<xml />")


def test_valid_docx_and_xlsx_archives_are_accepted(tmp_path):
    docx = tmp_path / "report.docx"
    xlsx = tmp_path / "report.xlsx"
    _write_ooxml(docx, ["[Content_Types].xml", "word/document.xml"])
    _write_ooxml(xlsx, ["[Content_Types].xml", "xl/workbook.xml"])
    validate_ooxml_file(docx, "docx")
    validate_ooxml_file(xlsx, "xlsx")


def test_invalid_generated_ooxml_preserves_existing_destination(tmp_path):
    destination = tmp_path / "report.docx"
    destination.write_bytes(b"EXISTING USER FILE")

    with pytest.raises(DocumentIntegrityError, match="valid OOXML"):
        commit_ooxml_atomic(
            destination,
            "docx",
            lambda staged: Path(staged).write_bytes(b"not a zip" * 20),
        )

    assert destination.read_bytes() == b"EXISTING USER FILE"


def test_producer_failure_preserves_existing_destination(tmp_path):
    destination = tmp_path / "report.xlsx"
    destination.write_bytes(b"EXISTING")

    def fail(_staged):
        raise RuntimeError("conversion failed")

    with pytest.raises(RuntimeError, match="conversion failed"):
        commit_ooxml_atomic(destination, "xlsx", fail)
    assert destination.read_bytes() == b"EXISTING"
