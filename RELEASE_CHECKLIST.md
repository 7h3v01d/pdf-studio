# PDF Studio 3.2.0-alpha12 - Release Candidate Checklist

This checklist separates evidence already established on the validated Windows build
from the remaining clean-machine and publication gates. Public binary approval in
`release/release_policy.json` must remain `false` until the final section is complete.

## Build provenance - complete

- [x] Python 3.11 clean `.buildenv` created from the verified offline wheelhouse.
- [x] `tools/verify_wheelhouse.py` passed (18 wheelhouse files).
- [x] `pip check` passed.
- [x] Full Windows pytest suite passed: **141 passed**.
- [x] Locked internal release audit passed.
- [x] `release/build_manifest.json` generated before PyInstaller.
- [x] PyInstaller completed successfully for Windows x86_64 / Python 3.11.
- [x] `release/artifact_manifest.json` generated for the packaged executable.
- [x] Runtime diagnostics report the expected bundled dependency versions.
- [ ] Archive the exact corresponding-source release package paired to the final public executable.

## Recovery-integrity regression evidence - complete

The automated Windows suite covers staged/atomic save behavior, late commit failure,
complete and incomplete rollback, durable recovery copies, recovery cleanup ownership,
Office-import cache ownership, transactional redaction, and destination preservation.

- [x] Late sidecar/file-set commit failure rolls back earlier destinations.
- [x] Incomplete rollback preserves recovery copies and reports failure rather than success.
- [x] Every restoration is attempted when rollback is incomplete.
- [x] Successful complete rollback removes its temporary recovery directory.
- [x] Failed Office conversion removes only marker-owned temporary output.
- [x] Redaction/save operations preserve existing destinations on prepare/validation failure.

## Clean Windows 10 and Windows 11 tests - still required

Record evidence in `release/clean_machine_results.json` using the provided template.
Test the final executable on clean machines without Python or developer tooling.

- [ ] Windows 10: startup/splash and main window.
- [ ] Windows 11: startup/splash and main window.
- [ ] Diagnostics shows the packaged manifest and expected bundled versions.
- [ ] Open, Save, Save As, Save a Copy, and close-with-unsaved-changes work.
- [ ] Notes, markup, sticky-note popup behavior, and undo/redo work.
- [ ] Drawn and imported signatures place normally and snap into signature fields.
- [ ] Drawn signature colour and thickness survive placement/save/reopen.
- [ ] Responsive **More »** toolbar overflow keeps every command accessible.
- [ ] Existing forms fill/save/reopen; Form Designer and Smart Form Detection work.
- [ ] OCR detects a normal Tesseract install without PATH editing.
- [ ] Scanned-text reversible/permanent replacement works, including exact numeric font size.
- [ ] Redaction removes searchable content and does not cross document sessions.
- [ ] Merge, split, extract, image export, and available Office import/export paths work.
- [ ] File associations register/unregister as documented.
- [ ] Third-party notices/licensing information is visible from Help.
- [ ] User documents are never removed by cleanup/uninstall behavior.

For each machine record edition/build, tested UTC, tester, final executable SHA-256,
status, and notes.

## Distribution and legal sign-off

- [x] PyMuPDF/MuPDF path documented: AGPL for official open-source builds.
- [x] PyQt6 path documented: GPLv3 for official open-source builds; Qt terms preserved.
- [x] Corresponding-source and notice delivery requirements defined in `LICENSING_STRATEGY.md`.
- [x] `release/release_policy.json` records the selected licensing strategy/decision.
- [x] Exact dependency locks and wheel hashes are captured.
- [x] Packaged Windows build/test evidence exists.
- [ ] Matching corresponding-source release package is archived with the final binary.
- [ ] Windows 10 clean-machine result is `passed`.
- [ ] Windows 11 clean-machine result is `passed`.
- [ ] Final binary approver and UTC approval timestamp are recorded.
- [ ] `tools/release_audit.py --public-release --require-lock` passes.
- [ ] `build_release.bat` completes against the approved release policy.

### Recommended, not currently enforced

- [ ] Code-signing / publisher identity decision documented.
- [ ] GitHub release notes link the binary to its exact source archive and SHA-256.

A checked box is not evidence by itself; retain the corresponding manifests and
clean-machine result records with the release.
