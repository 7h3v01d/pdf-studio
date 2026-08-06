#!/usr/bin/env python3
"""Generate a source/build manifest consumed by Diagnostics and PyInstaller."""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git", ".venv", ".buildenv", ".pytest_cache", "__pycache__",
    "build", "dist", "wheelhouse",
}
EXCLUDED_NAMES = {"build_manifest.json", "wheel_manifest.json", "PACKAGE_MANIFEST.json"}


def app_version() -> str:
    scope: dict[str, object] = {}
    exec((ROOT / "src" / "app_metadata.py").read_text(encoding="utf-8"), scope)
    return str(scope["APP_VERSION"])


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True, timeout=5, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def included_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if path.name in EXCLUDED_NAMES or path.suffix in {".pyc", ".pyo"}:
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(ROOT).as_posix())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def distribution_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for name in (
        "PyMuPDF", "PyQt6", "PyQt6-Qt6", "PyQt6-sip", "Pillow",
        "pytesseract", "PyInstaller", "pyinstaller-hooks-contrib", "pytest",
    ):
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = "not installed"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--context",
        choices=("source-package", "internal-build", "public-release"),
        default="source-package",
    )
    args = parser.parse_args()
    files = included_files()
    records = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in files
    ]
    aggregate = hashlib.sha256()
    for record in records:
        aggregate.update(record["path"].encode("utf-8"))
        aggregate.update(record["sha256"].encode("ascii"))

    policy_path = ROOT / "release" / "release_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    payload = {
        "schema_version": 1,
        "manifest_kind": args.context,
        "application_version": app_version(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "frozen_build_target": (
            "Windows x86_64 / Python 3.11"
            if args.context != "source-package" else "not built"
        ),
        "git_commit": git_commit(),
        "release_policy": policy,
        "dependencies": distribution_versions(),
        "source_file_count": len(records),
        "source_tree_sha256": aggregate.hexdigest(),
        "files": records,
    }
    out = ROOT / "release" / "build_manifest.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(records)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
