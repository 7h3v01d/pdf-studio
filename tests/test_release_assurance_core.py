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


def test_frozen_diagnostics_use_build_manifest_for_bundled_runtime_versions(monkeypatch):
    def missing_version(name):
        raise runtime_support.metadata.PackageNotFoundError(name)

    manifest = {
        "dependencies": {
            "PyMuPDF": "1.28.0",
            "PyQt6": "6.11.0",
            "PyInstaller": "6.21.0",
        }
    }
    monkeypatch.setattr(runtime_support.metadata, "version", missing_version)
    monkeypatch.setattr(runtime_support.sys, "frozen", True, raising=False)

    assert runtime_support.dependency_versions(
        ("PyMuPDF", "PyQt6", "missing"),
        build_manifest=manifest,
    ) == {
        "PyMuPDF": "1.28.0 (bundled)",
        "PyQt6": "6.11.0 (bundled)",
        "missing": "not installed",
    }


def test_default_diagnostics_dependencies_exclude_build_only_tools():
    assert runtime_support._DEPENDENCIES == (
        "PyMuPDF",
        "PyQt6",
        "PyQt6-Qt6",
        "PyQt6-sip",
        "Pillow",
        "pytesseract",
    )
    assert "PyInstaller" not in runtime_support._DEPENDENCIES
    assert "pytest" not in runtime_support._DEPENDENCIES


def test_diagnostics_summarise_build_manifest_without_full_file_inventory(monkeypatch):
    manifest = {
        "application_version": APP_VERSION,
        "manifest_kind": "internal-build",
        "dependencies": {"PyMuPDF": "1.28.0"},
        "source_file_count": 123,
        "source_tree_sha256": "abc123",
        "files": [{"path": ".old/private.zip", "sha256": "secret"}],
    }
    monkeypatch.setattr(runtime_support, "_safe_build_manifest", lambda: manifest)
    info = runtime_support.collect_diagnostics(APP_NAME, APP_VERSION)

    assert info["build_manifest"]["source_file_count"] == 123
    assert "files" not in info["build_manifest"]
    assert ".old/private.zip" not in runtime_support.format_diagnostics_report(info)


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


def test_release_policy_records_selected_open_source_strategy_but_stays_fail_closed():
    policy = json.loads((ROOT / "release" / "release_policy.json").read_text(encoding="utf-8"))
    assert policy["distribution_status"] == "release-candidate-source"
    assert policy["binary_distribution_approved"] is False
    assert policy["license_strategy"] == "agpl-gpl-compliant-source-distribution"
    assert policy["license_decision_by"] == "Leon Priest"
    assert policy["license_decision_utc"]
    assert "public release evidence pending" in DISTRIBUTION_STATUS.lower()


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
        "../LICENSING_STRATEGY.md",
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




def test_release_manifest_generator_excludes_local_archives_samples_and_scratch(monkeypatch, tmp_path):
    generator = load_tool("generate_release_manifest")
    monkeypatch.setattr(generator, "ROOT", tmp_path)

    keep = tmp_path / "src" / "app.py"
    keep.parent.mkdir(parents=True)
    keep.write_text("print('ok')\n", encoding="utf-8")

    for relative in (
        ".old/previous.zip",
        ".samples/private-test.pdf",
        ".venv/Lib/site-packages/demo.py",
        ".buildenv/Lib/site-packages/demo.py",
        ".releaseenv/Lib/site-packages/demo.py",
        "src/build/generated.bin",
        "src/dist/PDF Studio.exe",
        "release/wheelhouse/demo.whl",
        "New Text Document.bat",
        "release/artifact_manifest.json",
        "PACKAGE_MANIFEST.json",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"generated or local")

    included = {path.relative_to(tmp_path).as_posix() for path in generator.included_files()}
    assert included == {"src/app.py"}


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


def test_selected_licensing_strategy_is_consistent_across_release_surfaces():
    license_text = (ROOT / "LICENSE.txt").read_text(encoding="utf-8")
    strategy = (ROOT / "LICENSING_STRATEGY.md").read_text(encoding="utf-8")
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    metadata = (ROOT / "src" / "app_metadata.py").read_text(encoding="utf-8")
    spec = (ROOT / "src" / "PDF Studio.spec").read_text(encoding="utf-8")
    expression = "Apache-2.0 OR AGPL-3.0-only"
    for text in (license_text, strategy, notices, metadata):
        assert expression in text
    assert "official" in strategy.lower() and "agpl" in strategy.lower()
    assert "../LICENSING_STRATEGY.md" in spec
    assert not (ROOT / "LICENSING_DECISION_REQUIRED.md").exists()


def test_release_audit_recognises_selected_strategy_without_public_approval():
    audit = load_tool("release_audit")
    policy = json.loads((ROOT / "release" / "release_policy.json").read_text(encoding="utf-8"))
    assert policy["license_strategy"] in audit.ALLOWED_PUBLIC_STRATEGIES
    assert policy["binary_distribution_approved"] is False


def test_generated_tree_cleaner_removes_project_caches_but_preserves_environments(tmp_path):
    cleaner = load_tool("clean_release_tree")

    generated = (
        tmp_path / "src" / "__pycache__" / "module.cpython-311.pyc",
        tmp_path / "tests" / ".pytest_cache" / "v" / "cache" / "nodeids",
        tmp_path / ".coverage",
        tmp_path / "coverage.xml",
    )
    for path in generated:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"generated")

    preserved = (
        tmp_path / ".venv" / "Lib" / "site-packages" / "demo" / "__pycache__" / "x.pyc",
        tmp_path / ".buildenv" / "Lib" / "site-packages" / "demo" / "__pycache__" / "x.pyc",
        tmp_path / ".releaseenv" / "Lib" / "site-packages" / "demo" / "__pycache__" / "x.pyc",
    )
    for path in preserved:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"environment cache")

    removed = {path.as_posix() for path in cleaner.clean_generated_tree(tmp_path)}

    assert "src/__pycache__" in removed
    assert "tests/.pytest_cache" in removed
    assert ".coverage" in removed
    assert "coverage.xml" in removed
    assert all(not path.exists() for path in generated)
    assert all(path.exists() for path in preserved)


def test_test_and_build_workflows_use_shared_generated_tree_cleaner_before_audit():
    cleaner_token = "tools\\clean_release_tree.py"
    for script_name in (
        "setup.bat",
        "run_tests.bat",
        "capture_release_environment.bat",
        "build_clean.bat",
        "buildit.bat",
        "build_release.bat",
    ):
        source = (ROOT / script_name).read_text(encoding="utf-8", errors="replace")
        assert cleaner_token in source, f"{script_name} does not use the shared cache cleaner"

    for script_name in (
        "capture_release_environment.bat",
        "build_clean.bat",
        "buildit.bat",
        "build_release.bat",
    ):
        source = (ROOT / script_name).read_text(encoding="utf-8", errors="replace")
        assert source.rfind(cleaner_token) < source.rfind("release_audit.py")

    audit_source = (ROOT / "tools" / "release_audit.py").read_text(encoding="utf-8")
    assert '".releaseenv"' in audit_source
