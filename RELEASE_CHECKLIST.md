# PDF Studio Release Candidate Checklist

This checklist is required before `release_policy.json` may approve a public or
family binary. Record evidence in `release/clean_machine_results.json` using the
provided template.

## Build provenance

- [ ] Python 3.11 clean environment created from the verified offline wheelhouse.
- [ ] `tools/verify_wheelhouse.py` passed.
- [ ] `pip check` passed.
- [ ] Full pytest suite passed in the release environment.
- [ ] `tools/release_audit.py --public-release --require-lock` passed.
- [ ] `release/build_manifest.json` generated before PyInstaller.
- [ ] `release/artifact_manifest.json` records the final executable SHA-256.
- [ ] The exact source archive, locks, wheel manifest, and notices are archived.

## Recovery-integrity validation

- [ ] Fault-inject a late sidecar commit failure and confirm complete rollback reports restored destinations.
- [ ] Fault-inject both a late commit failure and an earlier destination-restoration failure.
- [ ] Confirm PDF Studio shows **Save Rollback Incomplete**, preserves a recovery directory, and records `recovery_manifest.json`.
- [ ] Confirm no success or preservation message is shown while rollback remains incomplete.
- [ ] Confirm failed Office conversion leaves no fresh `pdfstudio_import_*.pdf` cache.

## Clean Windows 10 and Windows 11 tests

Perform every item on clean machines without Python, developer tools, or a
preconfigured Tesseract PATH.

- [ ] Splash appears, remains visible for the minimum interval, fades, and the main window opens.
- [ ] Help > Diagnostics opens, reports the packaged build manifest, and opens the log folder.
- [ ] An unhandled test failure is recorded in the rotating log without exposing document contents.
- [ ] Open, Save, Save As, Save a Copy, and close-with-unsaved-changes work.
- [ ] Existing destination files survive simulated permission and late-validation failures.
- [ ] Merge, split, extract, Office export, and image export cancel cleanly with no partial output.
- [ ] Redactions cannot cross documents and apply transactionally.
- [ ] Signature and stamp placement save exactly once and undo/redo correctly.
- [ ] Insert, remove, move, and reorder preserve all page-bound state.
- [ ] Existing forms fill, save, reopen, and flatten safely.
- [ ] Form Designer and Smart Form Detection create persistent fields.
- [ ] OCR detects a normal Tesseract install without editing PATH.
- [ ] Scanned-text replacement works in reversible and permanent modes.
- [ ] PDF-to-image export works for PNG and JPEG at 300 DPI.
- [ ] Password-protected output contains visible application edits.
- [ ] File associations register and unregister without administrator-only assumptions.
- [ ] Third-party notices and licensing status are visible in Help.
- [ ] Upgrade and uninstall preserve user documents and remove only application-owned files.

## Distribution and legal sign-off

- [x] PyMuPDF/MuPDF path documented: AGPL for official open-source builds.
- [x] PyQt6 path documented: GPLv3 for official open-source builds; Qt terms remain preserved.
- [x] Corresponding-source and notice delivery is defined in `LICENSING_STRATEGY.md`.
- [x] `release/release_policy.json` records the selected strategy and licensing decision.
- [ ] Final binary approver and UTC approval timestamp are recorded after all technical evidence passes.
- [ ] Code signing / publisher identity is documented for the distributed executable or installer.

A checked box is not evidence by itself. Store machine version, test date,
artifact SHA-256, tester, result, and notes in the clean-machine results file.
