#!/usr/bin/env python3
"""Capture exact versions from a Windows environment that passed the suite."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_REQUIRED = (
    "PyMuPDF",
    "PyQt6",
    "PyQt6-Qt6",
    "PyQt6-sip",
    "Pillow",
    "pytesseract",
)
OPTIONAL_RUNTIME = (
    "pdf2docx",
    "tabula-py",
    "openpyxl",
    "pandas",
    "pywin32",
)
BUILD_REQUIRED = (
    "pytest",
    "PyInstaller",
    "pyinstaller-hooks-contrib",
)


def version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def normalise_requirement_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def write_lock(path: Path, names: tuple[str, ...], *, optional=False) -> dict[str, str]:
    found: dict[str, str] = {}
    missing: list[str] = []
    lines = [
        "# Generated from a test-validated environment.",
        "# Do not edit manually; regenerate with capture_release_environment.bat.",
    ]
    for name in names:
        value = version(name)
        if value is None:
            if not optional:
                missing.append(name)
            continue
        found[name] = value
        lines.append(f"{name}=={value}")
    if missing:
        raise SystemExit("Missing required distributions: " + ", ".join(missing))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return found


def main() -> int:
    if sys.version_info[:2] != (3, 11):
        raise SystemExit(
            f"Release capture requires Python 3.11; found {platform.python_version()}"
        )

    runtime = write_lock(ROOT / "requirements-validated.lock", RUNTIME_REQUIRED)
    optional: dict[str, str] = {}
    for name in OPTIONAL_RUNTIME:
        val = version(name)
        if val is not None:
            optional[name] = val

    build_found: dict[str, str] = {}
    build_missing: list[str] = []
    for name in BUILD_REQUIRED:
        val = version(name)
        if val is None:
            build_missing.append(name)
        else:
            build_found[name] = val
    if build_missing:
        print(
            "WARNING: build lock was not written because these packages are missing: "
            + ", ".join(build_missing),
            file=sys.stderr,
        )
    else:
        write_lock(ROOT / "requirements-build.lock", BUILD_REQUIRED)

    out_dir = ROOT / "release"
    out_dir.mkdir(exist_ok=True)
    payload = {
        "schema_version": 1,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "runtime": runtime,
        "optional_runtime": optional,
        "build": build_found,
        "pytest_command": ".venv\\Scripts\\python.exe -m pytest ./tests -v",
        "validation_required": True,
    }
    path = out_dir / "validated_environment.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {ROOT / 'requirements-validated.lock'}")
    if build_found:
        print(f"Wrote {ROOT / 'requirements-build.lock'}")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
