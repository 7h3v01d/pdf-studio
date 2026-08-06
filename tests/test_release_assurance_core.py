from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
import sys

import pytest

import runtime_support
from app_metadata import APP_NAME, APP_VERSION, DISTRIBUTION_STATUS

ROOT = Path(__file__).resolve().parents[1]


def load_tool(name: str):
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"pdfstudio_tool_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_application_data_dir_prefers_windows_local_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_support.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert runtime_support.application_data_dir() == tmp_path / "PDFStudio"


def test_logging_is_bounded_and_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_support, "log_directory", lambda: tmp_path)
    root = logging.getLogger()
    old = list(root.handlers)
    for handler in old:
        root.removeHandler(handler)
    try:
        first = runtime_support.configure_logging(APP_VERSION)
        second = runtime_support.configure_logging(APP_VERSION)
        tagged = [h for h in root.handlers if getattr(h, "_pdf_studio_handler", False)]
        assert first == second == tmp_path / "pdf_studio.log"
        assert len(tagged) == 1
        assert getattr(tagged[0], "maxBytes") == 2 * 1024 * 1024
        assert getattr(tagged[0], "backupCount") == 4
    finally:
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)
        for handler in old:
            root.addHandler(handler)


def test_diagnostics_report_contains_no_document_content_and_redacts_home(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_support.Path, "home", classmethod(lambda cls: tmp_path))
    info = runtime_support.collect_diagnostics(
        APP_NAME,
        APP_VERSION,
        extra={"tesseract_status": "ready"},
    )
    report = runtime_support.format_diagnostics_report(info)
    assert APP_VERSION in report
    assert "tesseract_status: ready" in report
    assert "no document contents" in report.lower()
    assert str(tmp_path) not in report


def test_dependency_versions_tolerates_missing_distribution(monkeypatch):
    def fake_version(name):
        if name == "present":
            return "1.2.3"
        raise runtime_support.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(runtime_support.metadata, "version", fake_version)
    assert runtime_support.dependency_versions(("present", "missing")) == {
        "present": "1.2.3",
        "missing": "not installed",
    }


def test_exact_pin_parser_rejects_ranges_and_accepts_complete_lock(tmp_path):
    audit = load_tool("release_audit")
    good = tmp_path / "good.lock"
    good.write_text("PyMuPDF==1.26.7\nPyQt6==6.9.1\n", encoding="utf-8")
    assert audit.exact_pins(good) == {"pymupdf", "pyqt6"}

    bad = tmp_path / "bad.lock"
    bad.write_text("PyMuPDF>=1.23\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Not an exact pin"):
        audit.exact_pins(bad)


def test_wheelhouse_manifest_detects_tampering(monkeypatch, tmp_path):
    verifier = load_tool("verify_wheelhouse")
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    wheel = wheelhouse / "demo-1.0-py3-none-any.whl"
    wheel.write_bytes(b"known bytes")
    manifest = tmp_path / "wheel_manifest.json"
    manifest.write_text(json.dumps({
        "files": [{
            "name": wheel.name,
            "size": wheel.stat().st_size,
            "sha256": verifier.sha256(wheel),
        }]
    }), encoding="utf-8")
    monkeypatch.setattr(verifier, "WHEELHOUSE", wheelhouse)
    monkeypatch.setattr(verifier, "MANIFEST", manifest)
    assert verifier.main() == 0
    wheel.write_bytes(b"changed")
    with pytest.raises(SystemExit, match="mismatch"):
        verifier.main()


def test_release_policy_is_fail_closed_by_default():
    policy = json.loads((ROOT / "release" / "release_policy.json").read_text(encoding="utf-8"))
    assert policy["distribution_status"] == "internal-development-only"
    assert policy["binary_distribution_approved"] is False
    assert policy["license_strategy"] == "undecided"
    assert "not yet approved" in DISTRIBUTION_STATUS.lower()


def test_release_assurance_is_wired_into_ui_spec_and_build_scripts():
    ui = (ROOT / "src" / "pdf_reader_ui.py").read_text(encoding="utf-8")
    entry = (ROOT / "src" / "pdf_reader.py").read_text(encoding="utf-8")
    spec = (ROOT / "src" / "PDF Studio.spec").read_text(encoding="utf-8")
    assert "Diagnostics…" in ui
    assert "Third-Party &Licences and Notices…" in ui
    assert "configure_logging(APP_VERSION)" in entry
    assert "install_exception_hook()" in entry
    for token in (
        "../THIRD_PARTY_NOTICES.md",
        "../LICENSING_DECISION_REQUIRED.md",
        "../release/build_manifest.json",
        "../licenses",
    ):
        assert token in spec
    for script_name in ("build_clean.bat", "buildit.bat"):
        script = (ROOT / script_name).read_text(encoding="utf-8")
        assert "pip check" in script
        assert "pytest" in script
        assert "release_audit.py" in script


def test_runtime_assets_are_separate_from_documentation_images():
    assets = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "assets").rglob("*")
        if path.is_file()
    }
    assert assets == {"assets/splashscreen.png"}

    docs_images = {
        path.name
        for path in (ROOT / "docs" / "images").glob("*.png")
        if path.is_file()
    }
    assert {"Badge_big.png", "Badge_small.png", "banner.png", "screenshot.png"} <= docs_images

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "![PDF Studio](docs/images/banner.png)" in readme
    assert "![PDF Studio application window](docs/images/screenshot.png)" in readme
    assert "assets/                              Runtime startup assets only" in readme


def test_release_manifest_generator_excludes_package_manifest_to_avoid_hash_cycle():
    generator = load_tool("generate_release_manifest")
    assert "PACKAGE_MANIFEST.json" in generator.EXCLUDED_NAMES



def test_windows_batch_scripts_do_not_require_py_launcher():
    import re

    forbidden = re.compile(r"(?im)^\s*(?:where\s+py\b|py(?:\.exe)?\s+-3\.11\b)")
    for path in ROOT.glob("*.bat"):
        source = path.read_text(encoding="utf-8", errors="replace")
        assert not forbidden.search(source), f"{path.name} still requires the py launcher"


def test_python311_resolver_is_shared_by_setup_build_and_registration_scripts():
    resolver = ROOT / "tools" / "resolve_python311.bat"
    source = resolver.read_text(encoding="utf-8", errors="replace")
    for token in (
        "PDF_STUDIO_PYTHON",
        ".venv\\Scripts\\python.exe",
        "where python.exe",
        "Python311\\python.exe",
        "sys.version_info[:2] == (3, 11)",
    ):
        assert token in source

    for script_name in (
        "setup.bat",
        "build_clean.bat",
        "build_release.bat",
        "register_pdf.bat",
        "unregister_pdf.bat",
    ):
        script = (ROOT / script_name).read_text(encoding="utf-8", errors="replace")
        assert "tools\\resolve_python311.bat" in script
        assert "PDF_STUDIO_PYTHON_EXE" in script


def test_readme_states_that_windows_py_launcher_is_optional():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "optional Windows `py` launcher is **not** required" in readme
    assert "PDF_STUDIO_PYTHON" in readme
