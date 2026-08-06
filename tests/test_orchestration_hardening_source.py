from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _class_methods(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise AssertionError(f"Class {class_name} not found in {path.name}")


def _method_node(path: Path, class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    return child
    raise AssertionError(f"{class_name}.{method_name} not found in {path.name}")


def _call_attribute_names(node: ast.AST) -> list[str]:
    names = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            names.append(child.func.attr)
    return names


def test_worker_dialogs_guard_escape_and_window_close():
    assert {"reject", "closeEvent"} <= _class_methods(
        SRC / "merge_split_dialog.py", "MergeSplitDialog"
    )
    assert {"reject", "closeEvent"} <= _class_methods(
        SRC / "extract_pages_dialog.py", "ExtractPagesDialog"
    )
    assert {"reject", "closeEvent"} <= _class_methods(
        SRC / "export_dialog.py", "ExportDialog"
    )


def test_pdf_workers_delegate_to_transactional_cancel_aware_core():
    merge_source = (SRC / "merge_split_dialog.py").read_text(encoding="utf-8")
    extract_source = (SRC / "extract_pages_dialog.py").read_text(encoding="utf-8")
    assert "merge_pdfs_atomic(" in merge_source
    assert "split_pdf_transactional(" in merge_source
    assert "cancelled=self.isInterruptionRequested" in merge_source
    assert "extract_pages_atomic(" in extract_source
    assert "cancelled=self.isInterruptionRequested" in extract_source


def test_office_exports_stage_validate_and_cooperate_with_cancel():
    source = (SRC / "export_dialog.py").read_text(encoding="utf-8")
    assert 'commit_ooxml_atomic(self.out_path, "docx"' in source
    assert 'commit_ooxml_atomic(self.out_path, "xlsx"' in source
    assert source.count("self.isInterruptionRequested()") >= 6
    assert "worker.cancelled.connect(" in source
    assert "worker.finished.connect(self._on_worker_thread_finished)" in source


def test_document_open_is_ast_scoped_transaction_with_real_rollback():
    method = _method_node(
        SRC / "pdf_reader_app.py", "PDFReader", "_open_pdf_path"
    )
    calls = _call_attribute_names(method)
    assert "_capture_open_session" in calls
    assert "_reset_document_session_state" in calls
    assert "_restore_open_session" in calls

    handlers = [node for node in ast.walk(method) if isinstance(node, ast.ExceptHandler)]
    assert any(
        "_restore_open_session" in _call_attribute_names(handler)
        for handler in handlers
    ), "Rollback must occur inside _open_pdf_path's own exception path."

    closes = [
        node for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "close"
    ]
    assert closes, "The previous or failed new document must be explicitly closed."


def test_save_as_requires_explicit_pending_redaction_decision():
    method = _method_node(
        SRC / "pdf_reader_app.py", "PDFReader", "save_pdf_as"
    )
    calls = _call_attribute_names(method)
    assert "_prompt_pending_redactions_for_save_as" in calls
    assert "apply_redactions" in calls
    assert "_do_save" in calls
    assert "_open_pdf_path" in calls


def test_imported_document_ctrl_s_routes_to_save_as_and_tracks_cache():
    save_method = _method_node(
        SRC / "pdf_reader_app.py", "PDFReader", "save_pdf"
    )
    save_source = ast.unparse(save_method)
    assert "self._imported_source_path" in save_source
    assert "self.save_pdf_as()" in save_source

    open_method = _method_node(
        SRC / "pdf_reader_app.py", "PDFReader", "_open_pdf_path"
    )
    open_source = ast.unparse(open_method)
    assert "self._imported_temp_pdf_path = imported_temp_path" in open_source
    assert "cleanup_temporary_import" in open_source


def test_pdf_and_sidecars_use_one_staged_commit_bundle():
    method = _method_node(SRC / "pdf_reader_app.py", "PDFReader", "_do_save")
    calls = _call_attribute_names(method)
    assert "stage_json_payload" in ast.unparse(method)
    assert "commit_staged_operations" in ast.unparse(method)
    assert "_clear_modified" in calls


def test_all_page_moves_route_through_final_index_adapter():
    utils_source = (SRC / "pdf_utils.py").read_text(encoding="utf-8")
    app_source = (SRC / "pdf_reader_app.py").read_text(encoding="utf-8")
    assert ".move_page(" not in utils_source
    assert ".move_page(" not in app_source
    assert utils_source.count("move_page_to_final_index(") >= 3
    assert "move_page_to_final_index(self.pdf_document, frm, to)" in app_source


def test_save_ui_distinguishes_incomplete_rollback_and_surfaces_recovery_path():
    method = _method_node(SRC / "pdf_reader_app.py", "PDFReader", "_do_save")
    source = ast.unparse(method)
    assert "SaveBundleRollbackIncomplete" in source
    assert "recovery_directory" in source
    assert "Save Rollback Incomplete" in source
    assert "Existing destination files were preserved" not in source


def test_startup_invokes_conservative_stale_import_cleanup():
    source = (SRC / "pdf_reader.py").read_text(encoding="utf-8")
    assert "cleanup_stale_temporary_imports" in source
    assert "Stale Office import cleanup failed" in source


def test_successful_save_cleanup_failure_is_a_privacy_warning_not_save_failure():
    save_method = _method_node(SRC / "pdf_reader_app.py", "PDFReader", "_do_save")
    save_source = ast.unparse(save_method)
    assert "SaveBundleRecoveryCleanupIncomplete" in save_source
    assert "cleanup_error.save_committed" in save_source
    assert "_show_recovery_cleanup_warning" in save_source
    assert "privacy action required" in save_source

    warning_method = _method_node(
        SRC / "pdf_reader_app.py", "PDFReader", "_show_recovery_cleanup_warning"
    )
    warning_source = ast.unparse(warning_method)
    assert "Retry Deletion" in warning_source
    assert "Open Recovery Folder" in warning_source
    assert "retry_recovery_cleanup" in warning_source
    assert "Secure completion cannot be claimed" in warning_source
