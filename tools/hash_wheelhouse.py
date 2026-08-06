#!/usr/bin/env python3
"""Record exact SHA-256 hashes for an offline release wheelhouse."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEELHOUSE = ROOT / "release" / "wheelhouse"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    files = sorted(p for p in WHEELHOUSE.iterdir() if p.is_file()) if WHEELHOUSE.exists() else []
    if not files:
        raise SystemExit("release/wheelhouse is empty")
    payload = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "files": [
            {"name": p.name, "size": p.stat().st_size, "sha256": sha256(p)}
            for p in files
        ],
    }
    out = ROOT / "release" / "wheel_manifest.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
