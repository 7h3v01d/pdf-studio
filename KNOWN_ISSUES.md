# PDF Studio 3.2.0-alpha12 — Known Issues and Release Gates

This build is an **internal development alpha**. It is not yet approved for
family distribution, public testing, or a GitHub binary release.

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
- A fail-closed policy that blocks public/family binaries while the dependency licensing strategy remains undecided.
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


## Remaining release gates

1. Add packaged-GUI integration tests for real close prompts, worker cancellation,
   file-dialog overwrite flows, and rollback recovery on Windows.
2. Extend atomic output to any optional conversion backend added in future and
   maintain disk-full / permission-denied fault-injection tests.
3. Run the exact-version capture and wheelhouse preparation on the final validated Windows build environment, then archive the resulting manifests.
4. Resolve PyMuPDF/MuPDF and PyQt6 binary-distribution licensing, update `release_policy.json`, and obtain any required legal review.
5. Run clean Windows 10 and Windows 11 virtual-machine installation, upgrade, file association, OCR, diagnostics/logging, and uninstall tests.
6. Raise coverage specifically across the real PyQt controller and packaged startup path; the current suite is much stronger but still core-heavy.
7. Add code signing and installer provenance before a public download is labelled release-ready.

See the adversarial review and the alpha7 through alpha12 changelogs for remediation history.
