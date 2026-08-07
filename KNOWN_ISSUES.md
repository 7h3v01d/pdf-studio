# PDF Studio 3.2.0-alpha12 — Known Issues and Release Gates

This build is a **Windows release candidate**. Reproducible dependency locks,
the verified wheelhouse, the packaged Windows build, diagnostics, release manifests,
and the 141-test Windows suite have passed. Public binary publication remains
fail-closed until clean Windows 10/11 evidence, matching corresponding-source release
packaging, and final approval are recorded.

## Corrected in alpha7

- Cross-document and partially applied redaction failures.
- Duplicate / invalid signature persistence.
- Unsafe flattening, Save As, Save a Copy, protected-copy, and LibreOffice output.
- Incomplete page-indexed state remapping and page-operation undo snapshots.

## Corrected in alpha8

- Merge, split, and extract now stage and validate output before commit.
- Split output commits as one file set and rolls back earlier replacements if a
  later destination cannot be committed.
- Merge, split, extract, Word, Excel, and image workers cooperate with cancellation.
- Their dialogs defer Escape / Close / window destruction until the active worker stops.
- DOCX and XLSX exports are structurally validated OOXML archives before replacement.
- Saved notes and markup now have one authority: native PDF annotations. Legacy
  sidecars are migrated without duplicate rendering or duplicate sidebar rows.
- Annotation, bookmark, and markup sidecars use atomic JSON replacement.
- Image signatures, stamps, and native annotation deletion use bounded PDF-snapshot undo.
- Failed same-file save preparation restores the pre-save in-memory PDF.
- A new PDF does not replace or close the current document until its caches and UI
  have initialised successfully; failures roll back to the previous session.

## Added in alpha9 - release assurance I

- Rotating application logs and unhandled-exception capture.
- In-app Diagnostics and bundled third-party notice viewers.
- Central application metadata and packaged build-manifest reporting.
- Python 3.11-only clean build validation with `pip check`, tests, and release audit.
- Exact environment capture and offline wheelhouse SHA-256 manifests.
- Separate internal and public-release build paths.
- A fail-closed policy that blocks public/family binaries until licensing, reproducible-build, clean-machine, and final approval evidence are complete.
- A clean Windows 10/11 checklist and machine-result evidence gate for public release.


## Corrected in alpha10 - controller integrity III

- Downward, thumbnail, undo, and redo page moves now translate desired final
  positions into PyMuPDF's native insertion-index semantics.
- Save As cannot silently drop pending redaction boxes; apply, discard, or cancel
  is required explicitly.
- Document opening now closes failed new documents, restores the previous session
  on initialisation failure, and closes the previous document only after success.
- Imported Word/Excel conversions are tracked as temporary caches. Normal Save is
  redirected to Save As, a durable `<original-name>.pdf` path is suggested, and
  owned cache files are cleaned when the session ends.
- The PDF, deferred notes, markup, and bookmarks now stage and commit as one
  rollback-capable save bundle. Sidecar failures preserve prior destinations and
  keep the document dirty instead of being overwritten by a false `Saved` state.

## Corrected in alpha11 - recovery integrity IV

- Save-bundle rollback failures are no longer suppressed. A compounded commit
  and restoration failure raises a dedicated `SaveBundleRollbackIncomplete`.
- Original destination backups remain in a durable recovery directory until the
  transaction commits or every rollback action succeeds.
- Incomplete rollback records the original commit failure, each failed restore,
  destination paths, recovery-copy paths, and human-readable instructions.
- The GUI never claims that existing destinations were preserved when rollback
  is incomplete; it shows the recovery path and keeps the document dirty.
- Failed Office conversions remove partial owned temporary PDFs. Startup removes
  only conservatively named PDF Studio import caches older than seven days.


## Corrected in alpha12 - confidential recovery V

- Successful saves no longer suppress failure to remove original transaction backups.
- Residual recovery copies raise a dedicated committed-but-cleanup-incomplete result, are shown prominently to the user, and can be retried or opened directly.
- Recovery transactions are stored under PDF Studio's local application-data recovery directory rather than beside potentially synchronised documents.
- Office-import caches now live in full-UUID, marker-owned workspaces under a dedicated temp root; filename resemblance alone is never treated as ownership.
- Stale-cache cleanup requires a valid ownership marker and removes the complete workspace only after the configured age threshold.


## Known limitations

- PDF signature fields can receive PDF Studio's visual drawn/imported signatures, but
  PDF Studio does **not** perform certificate-backed cryptographic PDF signing.
- PDF push-button actions and embedded PDF JavaScript are not executed.
- Multi-select list boxes are detected, but this release saves one selected item.
- Microsoft Office/LibreOffice, Tesseract, and optional export backends remain
  external dependencies where documented.

## Remaining public-release gates

1. Run and record the clean Windows 10 and Windows 11 machine checklist against the
   final executable SHA-256.
2. Package the exact corresponding source for that executable together with build
   scripts, dependency locks, wheel manifest/hashes, notices, licence texts, and the
   corresponding-source information required by `LICENSING_STRATEGY.md`.
3. Record the final approver and UTC approval timestamp in
   `release/release_policy.json`, then run the public-release audit/build path.

Code signing is recommended release polish, but it is not currently an enforced
`release_audit.py` gate.

See the README changelog for the alpha7-through-alpha12 remediation history.
