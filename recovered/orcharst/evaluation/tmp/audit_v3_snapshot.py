#!/usr/bin/env python3
"""Snapshot/verify hashes of the adaptive v3 experiment dir. Read-only except snapshot file."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "evaluation" / "results" / "nara_laguna_adaptive_v3_final_20260910"
SNAP = Path(__file__).resolve().parent / "audit_v3_snapshot.json"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


files = {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in sorted(EXP.rglob("*")) if p.is_file()}
mode = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
if mode == "snapshot":
    SNAP.write_text(json.dumps({"files": files}, indent=1), encoding="utf-8")
    print(f"snapshot saved: {len(files)} files hashed")
else:
    prev = json.loads(SNAP.read_text(encoding="utf-8"))["files"]
    changed = [k for k in files if prev.get(k) != files[k]]
    added = [k for k in files if k not in prev]
    missing = [k for k in prev if k not in files]
    print(f"files now: {len(files)} (was {len(prev)})")
    print("changed pre-existing files:", changed if changed else "(none)")
    print("new files:", added if added else "(none)")
    print("missing files:", missing if missing else "(none)")
