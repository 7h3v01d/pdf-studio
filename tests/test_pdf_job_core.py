from __future__ import annotations

from pathlib import Path

import fitz
import pytest

import pdf_job_core
from pdf_job_core import (
    JobCancelled,
    commit_staged_file_set,
    extract_pages_atomic,
    merge_pdfs_atomic,
    split_pdf_transactional,
)


def _pdf(path: Path, labels: list[str]) -> None:
    document = fitz.open()
    try:
        for label in labels:
            page = document.new_page(width=250, height=150)
            page.insert_text((40, 70), label, fontsize=16)
        document.save(path)
    finally:
        document.close()


def test_merge_is_atomic_and_validates_page_count(tmp_path):
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    output = tmp_path / "merged.pdf"
    _pdf(first, ["A"])
    _pdf(second, ["B", "C"])

    merge_pdfs_atomic([first, second], output)

    merged = fitz.open(output)
    try:
        assert merged.page_count == 3
        assert "A" in merged[0].get_text()
        assert "C" in merged[2].get_text()
    finally:
        merged.close()


def test_cancelled_merge_preserves_existing_destination(tmp_path):
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    output = tmp_path / "merged.pdf"
    _pdf(first, ["A"])
    _pdf(second, ["B"])
    output.write_bytes(b"EXISTING")

    with pytest.raises(JobCancelled):
        merge_pdfs_atomic(
            [first, second],
            output,
            cancelled=lambda: True,
        )
    assert output.read_bytes() == b"EXISTING"


def test_extract_pages_commits_only_complete_valid_pdf(tmp_path):
    source = tmp_path / "source.pdf"
    output = tmp_path / "extract.pdf"
    _pdf(source, ["ONE", "TWO", "THREE"])

    extract_pages_atomic(source, [2, 0], output)

    extracted = fitz.open(output)
    try:
        assert extracted.page_count == 2
        assert "THREE" in extracted[0].get_text()
        assert "ONE" in extracted[1].get_text()
    finally:
        extracted.close()


def test_split_cancellation_leaves_no_partial_outputs(tmp_path):
    source = tmp_path / "source.pdf"
    _pdf(source, ["ONE", "TWO", "THREE"])
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= 2

    with pytest.raises(JobCancelled):
        split_pdf_transactional(
            source,
            tmp_path,
            [(0, 0), (1, 1), (2, 2)],
            cancelled=cancelled,
        )
    assert not list(tmp_path.glob("source_part*.pdf"))
    assert not list(tmp_path.glob(".source.pdfstudio-split-*"))


def test_split_stages_all_parts_before_commit(tmp_path):
    source = tmp_path / "source.pdf"
    _pdf(source, ["ONE", "TWO", "THREE"])

    outputs = split_pdf_transactional(
        source,
        tmp_path,
        [(0, 0), (1, 2)],
    )

    assert [Path(path).name for path in outputs] == [
        "source_part001.pdf",
        "source_part002.pdf",
    ]
    assert fitz.open(outputs[0]).page_count == 1
    assert fitz.open(outputs[1]).page_count == 2


def test_multifile_commit_rolls_back_replaced_and_new_files(tmp_path, monkeypatch):
    staged_one = tmp_path / "stage-one"
    staged_two = tmp_path / "stage-two"
    destination_one = tmp_path / "one.pdf"
    destination_two = tmp_path / "two.pdf"
    staged_one.write_bytes(b"NEW-ONE")
    staged_two.write_bytes(b"NEW-TWO")
    destination_one.write_bytes(b"OLD-ONE")

    real_replace = pdf_job_core.os.replace
    calls = 0

    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated commit failure")
        return real_replace(source, destination)

    monkeypatch.setattr(pdf_job_core.os, "replace", fail_second)
    with pytest.raises(OSError, match="simulated commit failure"):
        commit_staged_file_set([
            (staged_one, destination_one),
            (staged_two, destination_two),
        ])

    assert destination_one.read_bytes() == b"OLD-ONE"
    assert not destination_two.exists()
