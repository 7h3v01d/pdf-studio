# PDF Studio Licensing Strategy

**Decision date:** 2026-08-06

**Decision owner:** Leon Priest

**SPDX expression for PDF Studio source:** `Apache-2.0 OR AGPL-3.0-only`

## Selected model

PDF Studio source code authored by Leon Priest is dual-licensed. A recipient
may use that source under either:

1. the Apache License 2.0; or
2. the GNU Affero General Public License version 3 only.

The complete texts are in `licenses/Apache-2.0.txt` and
`licenses/AGPL-3.0.txt`.

## Official open-source builds

Official prebuilt builds that use the free editions of PyQt6 and
PyMuPDF/MuPDF use the **AGPL-3.0-only option for PDF Studio code**.

The resulting executable is a compatible GPLv3/AGPLv3 combination. Each
third-party component keeps its own licence:

- PDF Studio code: AGPL-3.0-only for the official build;
- PyMuPDF/MuPDF: AGPLv3 or applicable commercial terms from its owner;
- PyQt6: GPLv3 or applicable commercial terms from Riverbank;
- Qt 6 and other components: their respective bundled terms.

This project does not claim to relicense third-party software.

## GitHub binary-release delivery

A public binary release must provide, from the same release page or an equally
prominent location:

- the exact PDF Studio source archive corresponding to the binary;
- build and packaging scripts;
- exact dependency lock files and recorded package hashes;
- the executable SHA-256 and source-archive SHA-256;
- `LICENSE.txt`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, this strategy document,
  and all bundled licence texts;
- the information needed to obtain the corresponding source for bundled
  GPL/AGPL components; and
- clean Windows test evidence for the exact executable.

`release/release_policy.json` records the selected strategy. Selection of this
strategy does **not** by itself approve a public binary. The release audit will
continue to fail closed until build provenance, dependency locks, wheel hashes,
clean-machine evidence, and final approval metadata are present.

## Proprietary or closed-source distribution

This decision does not approve a proprietary or closed-source edition. Before
shipping such an edition, obtain appropriate commercial licences for
PyMuPDF/MuPDF and PyQt6, confirm Qt licensing, and update the release policy.
Charging money does not by itself require a proprietary licence, but restricting
recipients' GPL/AGPL rights would require a different dependency-licensing path.

## Scope and legal review

This document records the project's engineering and distribution decision. It
is not legal advice. The final distributor remains responsible for satisfying
the exact licences of the versions included in each release.

Official references reviewed for this decision:

- PyMuPDF licensing: https://pymupdf.readthedocs.io/en/latest/about.html
- PyQt licensing: https://www.riverbankcomputing.com/commercial/license-faq
- GNU GPL compatibility guidance: https://www.gnu.org/licenses/license-compatibility.html
