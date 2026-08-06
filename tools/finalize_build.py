#!/usr/bin/env python3
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "src" / "dist" / "PDF Studio.exe"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    if not EXE.is_file() or EXE.stat().st_size < 1024 * 1024:
        raise SystemExit(f"Built executable is missing or implausibly small: {EXE}")
    payload = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "artifact": {
            "path": EXE.relative_to(ROOT).as_posix(),
            "size": EXE.stat().st_size,
            "sha256": sha256(EXE),
        },
    }
    out = ROOT / "release" / "artifact_manifest.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
