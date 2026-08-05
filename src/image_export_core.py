"""Core PDF-page-to-image export helpers.

The functions in this module deliberately avoid Qt so page parsing, output naming,
and rendering can be regression-tested independently of the GUI.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import uuid
from typing import Callable, Iterable

import fitz
from PIL import Image


FORMAT_EXTENSIONS = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "WEBP": ".webp",
    "TIFF": ".tiff",
    "BMP": ".bmp",
    "GIF": ".gif",
}

TRANSPARENCY_FORMATS = {"PNG", "WEBP", "TIFF"}
QUALITY_FORMATS = {"JPEG", "WEBP"}


@dataclass(frozen=True)
class ImageExportOptions:
    image_format: str = "PNG"
    dpi: int = 300
    quality: int = 92
    transparent_background: bool = False
    background_rgb: tuple[int, int, int] = (255, 255, 255)

    def normalised(self) -> "ImageExportOptions":
        fmt = self.image_format.upper().strip()
        if fmt == "JPG":
            fmt = "JPEG"
        if fmt not in FORMAT_EXTENSIONS:
            raise ValueError(f"Unsupported image format: {self.image_format}")
        if not 36 <= int(self.dpi) <= 1200:
            raise ValueError("DPI must be between 36 and 1200.")
        if not 1 <= int(self.quality) <= 100:
            raise ValueError("Quality must be between 1 and 100.")
        rgb = tuple(int(c) for c in self.background_rgb)
        if len(rgb) != 3 or any(c < 0 or c > 255 for c in rgb):
            raise ValueError("Background colour must contain three values from 0 to 255.")
        return ImageExportOptions(
            image_format=fmt,
            dpi=int(self.dpi),
            quality=int(self.quality),
            transparent_background=(
                bool(self.transparent_background) and fmt in TRANSPARENCY_FORMATS
            ),
            background_rgb=rgb,
        )


def parse_page_spec(raw: str, total_pages: int) -> list[int]:
    """Parse a one-based page specification into unique zero-based indices.

    Examples: ``1-3, 6, 9-10``. Invalid, descending, and out-of-range
    references are rejected instead of being silently ignored.
    """
    if total_pages < 1:
        raise ValueError("The PDF does not contain any pages.")
    value = raw.strip()
    if not value:
        raise ValueError("Enter a page range.")

    result: list[int] = []
    seen: set[int] = set()
    for chunk in value.split(","):
        token = chunk.strip()
        if not token:
            raise ValueError("The page range contains an empty item.")
        if "-" in token:
            if token.count("-") != 1:
                raise ValueError(f"Invalid page range: {token}")
            left, right = (part.strip() for part in token.split("-", 1))
            if not left.isdigit() or not right.isdigit():
                raise ValueError(f"Invalid page range: {token}")
            start, end = int(left), int(right)
            if start > end:
                raise ValueError(f"Descending page range is not supported: {token}")
            pages: Iterable[int] = range(start, end + 1)
        else:
            if not token.isdigit():
                raise ValueError(f"Invalid page number: {token}")
            pages = (int(token),)

        for page_number in pages:
            if not 1 <= page_number <= total_pages:
                raise ValueError(
                    f"Page {page_number} is outside this PDF (1-{total_pages})."
                )
            index = page_number - 1
            if index not in seen:
                seen.add(index)
                result.append(index)

    if not result:
        raise ValueError("No pages were selected.")
    return result


def resolve_page_indices(
    scope_id: int,
    raw_range: str,
    total_pages: int,
    current_page: int,
) -> list[int]:
    if total_pages < 1:
        raise ValueError("The PDF does not contain any pages.")
    if scope_id == 0:
        return list(range(total_pages))
    if scope_id == 1:
        if not 0 <= current_page < total_pages:
            raise ValueError("The current page is outside the document.")
        return [current_page]
    if scope_id == 2:
        return parse_page_spec(raw_range, total_pages)
    raise ValueError("Unknown page-selection mode.")


def build_output_paths(
    pdf_path: str | Path,
    destination: str | Path,
    page_indices: list[int],
    image_format: str,
    total_pages: int,
) -> list[Path]:
    """Build output paths for a single chosen filename or a page folder."""
    if not page_indices:
        raise ValueError("No pages were selected.")
    fmt = image_format.upper().strip()
    if fmt == "JPG":
        fmt = "JPEG"
    try:
        extension = FORMAT_EXTENSIONS[fmt]
    except KeyError as exc:
        raise ValueError(f"Unsupported image format: {image_format}") from exc

    pdf = Path(pdf_path)
    target = Path(destination)
    if len(page_indices) == 1:
        if target.suffix.lower() != extension:
            target = target.with_suffix(extension)
        return [target]

    width = max(3, len(str(total_pages)))
    return [
        target / f"{pdf.stem}_page_{index + 1:0{width}d}{extension}"
        for index in page_indices
    ]


def _pil_image_from_page(page: fitz.Page, options: ImageExportOptions) -> Image.Image:
    scale = options.dpi / 72.0
    pix = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale),
        alpha=options.transparent_background,
        annots=True,
    )
    mode = "RGBA" if pix.alpha else "RGB"
    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    if image.mode == "RGBA" and not options.transparent_background:
        background = Image.new("RGB", image.size, options.background_rgb)
        background.paste(image, mask=image.getchannel("A"))
        image = background
    return image


def _save_image(image: Image.Image, path: Path, options: ImageExportOptions) -> None:
    fmt = options.image_format
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "JPEG":
        if image.mode != "RGB":
            background = Image.new("RGB", image.size, options.background_rgb)
            if image.mode == "RGBA":
                background.paste(image, mask=image.getchannel("A"))
            else:
                background.paste(image.convert("RGB"))
            image = background
        image.save(
            path,
            format="JPEG",
            quality=options.quality,
            optimize=True,
            progressive=True,
            subsampling=0,
            dpi=(options.dpi, options.dpi),
        )
    elif fmt == "WEBP":
        image.save(
            path,
            format="WEBP",
            quality=options.quality,
            method=6,
            lossless=options.quality == 100,
        )
    elif fmt == "TIFF":
        image.save(
            path,
            format="TIFF",
            compression="tiff_deflate",
            dpi=(options.dpi, options.dpi),
        )
    elif fmt == "GIF":
        # GIF is intentionally a static page image. Multi-page PDFs produce
        # one GIF per selected page rather than an animation.
        if image.mode == "RGBA":
            background = Image.new("RGB", image.size, options.background_rgb)
            background.paste(image, mask=image.getchannel("A"))
            image = background
        image.convert("P", palette=Image.Palette.ADAPTIVE, colors=256).save(
            path,
            format="GIF",
            optimize=True,
        )
    elif fmt == "BMP":
        if image.mode == "RGBA":
            background = Image.new("RGB", image.size, options.background_rgb)
            background.paste(image, mask=image.getchannel("A"))
            image = background
        image.save(path, format="BMP", dpi=(options.dpi, options.dpi))
    else:  # PNG
        image.save(
            path,
            format="PNG",
            optimize=True,
            dpi=(options.dpi, options.dpi),
        )


def export_pdf_pages(
    pdf_path: str | Path,
    page_indices: list[int],
    output_paths: list[str | Path],
    options: ImageExportOptions,
    progress: Callable[[int, str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> list[Path]:
    """Render selected pages transactionally to independent image files.

    Every page is first written to a temporary sibling. Destination files are
    replaced only after all pages render successfully. Existing images are
    backed up during commit and restored if the commit itself fails.
    """
    options = options.normalised()
    if len(page_indices) != len(output_paths):
        raise ValueError("Each selected page requires one output path.")
    if not page_indices:
        raise ValueError("No pages were selected.")

    outputs = [Path(path) for path in output_paths]
    token = uuid.uuid4().hex
    staged = [
        path.with_name(f".{path.name}.pdfstudio-{token}.tmp") for path in outputs
    ]
    backups: dict[Path, Path] = {}
    committed: list[Path] = []

    document = fitz.open(str(pdf_path))
    try:
        for position, (page_index, staged_path) in enumerate(
            zip(page_indices, staged), start=1
        ):
            if cancelled and cancelled():
                raise InterruptedError("Image export was cancelled.")
            if not 0 <= page_index < document.page_count:
                raise ValueError(f"Page index {page_index} is outside the PDF.")
            if progress:
                progress(
                    int(((position - 1) / len(page_indices)) * 100),
                    f"Rendering page {page_index + 1} of {document.page_count}…",
                )
            image = _pil_image_from_page(document[page_index], options)
            _save_image(image, staged_path, options)
            if progress:
                progress(
                    int((position / len(page_indices)) * 95),
                    f"Rendered page {page_index + 1}",
                )
    except Exception:
        for path in staged:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        document.close()

    try:
        if cancelled and cancelled():
            raise InterruptedError("Image export was cancelled.")
        if progress:
            progress(96, "Finalising exported images…")
        for output, staged_path in zip(outputs, staged):
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                backup = output.with_name(
                    f".{output.name}.pdfstudio-backup-{token}.tmp"
                )
                os.replace(output, backup)
                backups[output] = backup
            os.replace(staged_path, output)
            committed.append(output)
    except Exception:
        for output in committed:
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass
        for output, backup in backups.items():
            try:
                if backup.exists():
                    os.replace(backup, output)
            except OSError:
                pass
        for path in staged:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    else:
        for backup in backups.values():
            try:
                backup.unlink(missing_ok=True)
            except OSError:
                pass
        if progress:
            progress(100, "Export complete")
        return outputs
