#!/usr/bin/env python3
"""Fail-closed release engineering checks for PDF Studio."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "LICENSE.txt",
    "NOTICE",
    "THIRD_PARTY_NOTICES.md",
    "LICENSING_DECISION_REQUIRED.md",
    "release/release_policy.json",
    "RELEASE_CHECKLIST.md",
    "release/clean_machine_results.template.json",
    "licenses/Apache-2.0.txt",
    "licenses/GPL-3.0.txt",
    "licenses/LGPL-3.0.txt",
    "licenses/AGPL-3.0.txt",
    "licenses/Pillow-License.txt",
    "licenses/pytesseract-License.txt",
    "assets/splashscreen.png",
    "src/app_metadata.py",
    "src/runtime_support.py",
    "src/diagnostics_dialog.py",
)
REQUIRED_RUNTIME_LOCK_NAMES = {
    "pymupdf", "pyqt6", "pyqt6-qt6", "pyqt6-sip", "pillow", "pytesseract"
}
ALLOWED_PUBLIC_STRATEGIES = {
    "agpl-gpl-compliant-source-distribution",
    "commercial-licenses",
    "dependency-replacement",
}


def metadata_version() -> str:
    tree = ast.parse((ROOT / "src" / "app_metadata.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "APP_VERSION":
                    return ast.literal_eval(node.value)
    raise RuntimeError("APP_VERSION not found")


def exact_pins(path: Path) -> set[str]:
    names: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line or any(op in line for op in (">=", "<=", "~=", "!=", "<", ">")):
            raise ValueError(f"Not an exact pin: {line}")
        name, version = line.split("==", 1)
        if not name.strip() or not version.strip():
            raise ValueError(f"Invalid exact pin: {line}")
        names.add(re.sub(r"[-_.]+", "-", name.strip()).lower())
    return names


def run(public_release: bool, require_lock: bool) -> list[str]:
    failures: list[str] = []
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            failures.append(f"Missing required release file: {relative}")

    try:
        version = metadata_version()
    except Exception as exc:
        failures.append(f"Could not read APP_VERSION: {exc}")
        version = ""

    for relative in ("README.md", "KNOWN_ISSUES.md"):
        path = ROOT / relative
        if path.exists() and version and version not in path.read_text(encoding="utf-8"):
            failures.append(f"{relative} does not mention current version {version}")

    about_text = (ROOT / "src" / "about_dialog.py").read_text(encoding="utf-8")
    if re.search(r"^APP_VERSION\s*=", about_text, re.MULTILINE):
        failures.append("about_dialog.py duplicates APP_VERSION instead of importing app_metadata")
    if "production-ready" in about_text.lower():
        failures.append("About dialog still claims production readiness")

    spec = (ROOT / "src" / "PDF Studio.spec").read_text(encoding="utf-8")
    for token in (
        "../assets/splashscreen.png",
        "../THIRD_PARTY_NOTICES.md",
        "../LICENSING_DECISION_REQUIRED.md",
        "../release/build_manifest.json",
        "../licenses",
    ):
        if token not in spec:
            failures.append(f"PyInstaller spec does not bundle {token}")

    for script in ("build_clean.bat", "buildit.bat"):
        text = (ROOT / script).read_text(encoding="utf-8", errors="replace").lower()
        if "pip check" not in text:
            failures.append(f"{script} does not run pip check")
        if "pytest" not in text:
            failures.append(f"{script} does not run the test suite")
        if "release_audit.py" not in text:
            failures.append(f"{script} does not run the release audit")
        if "goto :fail" not in text and "exit /b 1" not in text:
            failures.append(f"{script} does not visibly fail closed")

    policy_path = ROOT / "release" / "release_policy.json"
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception as exc:
        failures.append(f"Invalid release policy: {exc}")
        policy = {}

    if public_release:
        if policy.get("binary_distribution_approved") is not True:
            failures.append("Public binary release is not approved by release_policy.json")
        if policy.get("license_strategy") not in ALLOWED_PUBLIC_STRATEGIES:
            failures.append("A recognised binary licensing strategy has not been selected")
        if not str(policy.get("approved_by", "")).strip():
            failures.append("Release policy has no approving person")
        if not str(policy.get("approved_utc", "")).strip():
            failures.append("Release policy has no approval timestamp")

    lock = ROOT / "requirements-validated.lock"
    if require_lock or public_release:
        if not lock.is_file():
            failures.append("requirements-validated.lock is required")
        else:
            try:
                names = exact_pins(lock)
                missing = sorted(REQUIRED_RUNTIME_LOCK_NAMES - names)
                if missing:
                    failures.append("Runtime lock is missing: " + ", ".join(missing))
            except ValueError as exc:
                failures.append(str(exc))
        if not (ROOT / "requirements-build.lock").is_file():
            failures.append("requirements-build.lock is required")
        if not (ROOT / "release" / "validated_environment.json").is_file():
            failures.append("release/validated_environment.json is required")
        if public_release and not (ROOT / "release" / "wheel_manifest.json").is_file():
            failures.append("release/wheel_manifest.json is required for public release")

    if public_release:
        results_path = ROOT / "release" / "clean_machine_results.json"
        if not results_path.is_file():
            failures.append("release/clean_machine_results.json is required")
        else:
            try:
                results = json.loads(results_path.read_text(encoding="utf-8"))
                for key in ("windows_10", "windows_11"):
                    item = results.get(key, {})
                    if item.get("status") != "passed":
                        failures.append(f"{key} clean-machine status is not passed")
                    for field in ("edition_and_build", "tested_utc", "tester"):
                        if not str(item.get(field, "")).strip():
                            failures.append(f"{key} is missing {field}")
                if not str(results.get("artifact_sha256", "")).strip():
                    failures.append("clean-machine results are missing artifact_sha256")
            except Exception as exc:
                failures.append(f"Invalid clean-machine results: {exc}")

    forbidden_dirs = {".pytest_cache", "__pycache__"}
    for path in ROOT.rglob("*"):
        if path.is_dir() and path.name in forbidden_dirs:
            failures.append(f"Release tree contains generated directory: {path.relative_to(ROOT)}")
            break
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-release", action="store_true")
    parser.add_argument("--require-lock", action="store_true")
    args = parser.parse_args()
    failures = run(args.public_release, args.require_lock)
    if failures:
        print("RELEASE AUDIT FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("Release audit passed.")
    if not args.public_release:
        print("Distribution status remains internal-development-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
