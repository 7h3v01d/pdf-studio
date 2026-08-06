# Binary Distribution Licensing Decision Required

PDF Studio is currently an **internal development alpha**. The repository's
application source is marked Apache-2.0, while the normal runtime stack uses:

- PyMuPDF / MuPDF under AGPL or commercial terms; and
- PyQt6 under GPLv3 or Riverbank commercial terms.

A bundled executable must not be described as release-approved until the
project owner deliberately chooses one of these paths:

## Path A — open-source combined distribution

Adopt a distribution model that satisfies the applicable GPLv3 and AGPL
requirements for the complete combined work. This normally requires careful
corresponding-source delivery, complete notices and licence texts, and a clear
written offer/process appropriate to the chosen distribution method.

## Path B — commercial dependency licences

Acquire and document appropriate commercial licences for PyMuPDF/MuPDF and
PyQt6 (and confirm the Qt licence used by the binary).

## Path C — dependency replacement

Replace the GPL/AGPL components with dependencies whose licences are compatible
with the intended binary distribution model, then repeat technical and legal
review.

This file is not legal advice. It is a fail-closed engineering gate. Obtain
qualified legal advice before public distribution when necessary.
