from __future__ import annotations

from pathlib import Path

import fitz
import pytest
from PIL import Image

from image_export_core import (
    ImageExportOptions,
    build_output_paths,
    export_pdf_pages,
    parse_page_spec,
    resolve_page_indices,
)


def _sample_pdf(path: Path, pages: int = 3, width: int = 120, height: int = 80):
    doc = fitz.open()
    for number in range(1, pages + 1):
        page = doc.new_page(width=width, height=height)
        page.insert_text((12, 35), f"POSTER PAGE {number}", fontsize=12)
    doc.save(path)
    doc.close()


def test_page_range_parser_preserves_discontiguous_order_and_deduplicates():
    assert parse_page_spec("3, 1-2, 3, 5", 5) == [2, 0, 1, 4]
    assert resolve_page_indices(0, "", 3, 1) == [0, 1, 2]
    assert resolve_page_indices(1, "", 3, 1) == [1]


@pytest.mark.parametrize(
    "spec, message",
    [
        ("", "Enter a page range"),
        ("4-2", "Descending"),
        ("0", "outside"),
        ("6", "outside"),
        ("1,,2", "empty item"),
    ],
)
def test_page_range_parser_rejects_ambiguous_or_invalid_ranges(spec, message):
    with pytest.raises(ValueError, match=message):
        parse_page_spec(spec, 5)


def test_output_names_are_numbered_for_multiple_pages(tmp_path):
    paths = build_output_paths(
        "community-poster.pdf",
        tmp_path,
        [0, 2, 11],
        "PNG",
        total_pages=12,
    )
    assert [path.name for path in paths] == [
        "community-poster_page_001.png",
        "community-poster_page_003.png",
        "community-poster_page_012.png",
    ]


def test_single_page_export_respects_dpi_and_png_text(tmp_path):
    pdf = tmp_path / "poster.pdf"
    output = tmp_path / "poster.png"
    _sample_pdf(pdf, pages=1, width=120, height=80)

    created = export_pdf_pages(
        pdf,
        [0],
        [output],
        ImageExportOptions(image_format="PNG", dpi=144),
    )
    assert created == [output]
    with Image.open(output) as image:
        assert image.format == "PNG"
        assert image.size == (240, 160)


def test_jpeg_and_static_gif_exports_are_readable(tmp_path):
    pdf = tmp_path / "poster.pdf"
    _sample_pdf(pdf, pages=2)
    jpg = tmp_path / "page.jpg"
    gif = tmp_path / "page.gif"

    export_pdf_pages(
        pdf,
        [0],
        [jpg],
        ImageExportOptions(image_format="JPEG", dpi=96, quality=88),
    )
    export_pdf_pages(
        pdf,
        [1],
        [gif],
        ImageExportOptions(image_format="GIF", dpi=96),
    )

    with Image.open(jpg) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
    with Image.open(gif) as image:
        assert image.format == "GIF"
        assert getattr(image, "n_frames", 1) == 1


def test_transparent_png_preserves_blank_page_alpha(tmp_path):
    pdf = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page(width=72, height=72)
    doc.save(pdf)
    doc.close()

    output = tmp_path / "blank.png"
    export_pdf_pages(
        pdf,
        [0],
        [output],
        ImageExportOptions(
            image_format="PNG",
            dpi=72,
            transparent_background=True,
        ),
    )
    with Image.open(output) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((10, 10))[3] == 0


def test_export_cleans_up_created_files_after_later_page_failure(tmp_path):
    pdf = tmp_path / "poster.pdf"
    _sample_pdf(pdf, pages=1)
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"

    with pytest.raises(ValueError, match="outside"):
        export_pdf_pages(
            pdf,
            [0, 99],
            [first, second],
            ImageExportOptions(image_format="PNG", dpi=72),
        )
    assert not first.exists()
    assert not second.exists()


def test_failed_transaction_preserves_preexisting_destination(tmp_path):
    pdf = tmp_path / "poster.pdf"
    _sample_pdf(pdf, pages=1)
    first = tmp_path / "existing.png"
    second = tmp_path / "never.png"
    first.write_bytes(b"ORIGINAL IMAGE BYTES")

    with pytest.raises(ValueError, match="outside"):
        export_pdf_pages(
            pdf,
            [0, 5],
            [first, second],
            ImageExportOptions(image_format="PNG", dpi=72),
        )
    assert first.read_bytes() == b"ORIGINAL IMAGE BYTES"
    assert not second.exists()
