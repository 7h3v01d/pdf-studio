#!/usr/bin/env python3
"""Remove generated Python/test caches from the project release tree.

Virtual environments and repository metadata are intentionally left untouched.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_TOP_LEVEL = {".git", ".venv", ".buildenv", ".releaseenv"}
GENERATED_DIR_NAMES = {".pytest_cache", "__pycache__"}
GENERATED_FILE_NAMES = {".coverage", "coverage.xml"}
GENERATED_FILE_SUFFIXES = {".pyc", ".pyo"}


def _make_writable_and_retry(function, path: str, _exc_info) -> None:
    """Allow cleanup of read-only generated files on Windows."""
    os.chmod(path, stat.S_IWRITE)
    function(path)


def clean_generated_tree(root: Path = ROOT) -> list[Path]:
    """Delete generated caches outside managed environment directories.

    Returns paths relative to *root* that were removed. Any cleanup failure is
    raised so build scripts continue to fail closed.
    """
    root = Path(root).resolve()
    removed: list[Path] = []

    for current_text, directory_names, file_names in os.walk(root, topdown=True):
        current = Path(current_text)
        relative_current = current.relative_to(root)

        if relative_current == Path("."):
            directory_names[:] = [
                name for name in directory_names if name not in EXCLUDED_TOP_LEVEL
            ]

        generated_directories = [
            name for name in directory_names if name in GENERATED_DIR_NAMES
        ]
        for name in generated_directories:
            target = current / name
            relative = target.relative_to(root)
            shutil.rmtree(target, onerror=_make_writable_and_retry)
            removed.append(relative)
            directory_names.remove(name)

        for name in file_names:
            target = current / name
            if name not in GENERATED_FILE_NAMES and target.suffix.lower() not in GENERATED_FILE_SUFFIXES:
                continue
            relative = target.relative_to(root)
            try:
                target.unlink()
            except PermissionError:
                target.chmod(stat.S_IWRITE)
                target.unlink()
            removed.append(relative)

    return sorted(removed, key=lambda path: path.as_posix())


def main() -> int:
    try:
        removed = clean_generated_tree()
    except Exception as exc:
        print(f"[ERROR] Generated-tree cleanup failed: {exc}", file=sys.stderr)
        return 1

    if removed:
        print(f"Cleaned generated release-tree entries: {len(removed)}")
        for relative in removed:
            print(f"  - {relative}")
    else:
        print("Generated release tree already clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
