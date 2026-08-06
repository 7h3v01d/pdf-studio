#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEELHOUSE = ROOT / "release" / "wheelhouse"
MANIFEST = ROOT / "release" / "wheel_manifest.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    if not MANIFEST.is_file():
        raise SystemExit("Missing release/wheel_manifest.json")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = {item["name"]: item for item in data.get("files", [])}
    actual_names = {p.name for p in WHEELHOUSE.iterdir() if p.is_file()} if WHEELHOUSE.exists() else set()
    if set(expected) != actual_names:
        missing = sorted(set(expected) - actual_names)
        extra = sorted(actual_names - set(expected))
        raise SystemExit(f"Wheelhouse contents differ. missing={missing} extra={extra}")
    for name, record in expected.items():
        path = WHEELHOUSE / name
        if path.stat().st_size != int(record["size"]):
            raise SystemExit(f"Wheel size mismatch: {name}")
        if sha256(path) != record["sha256"]:
            raise SystemExit(f"Wheel hash mismatch: {name}")
    print(f"Wheelhouse verified: {len(expected)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
