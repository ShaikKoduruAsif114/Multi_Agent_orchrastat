#!/usr/bin/env python3
"""Snapshot/verify hashes: experiment dir + frozen benchmark inputs.

Usage: python audit_file_snapshot.py [snapshot|verify]
Read-only; writes only its own snapshot JSON in evaluation/tmp/.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "evaluation" / "results" / "nara_laguna_archstrong_final30_final_20260910"
MAN = ROOT / "evaluation" / "benchmark_input_manifest_sha256_20260909.txt"
SNAP = Path(__file__).resolve().parent / "audit_file_snapshot.json"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot():
    files = {}
    for p in sorted(EXP.rglob("*")):
        if p.is_file():
            files[str(p.relative_to(ROOT)).replace("\\", "/")] = sha(p)
    files["evaluation/benchmark_input_manifest_sha256_20260909.txt"] = sha(MAN)
    frozen_ok, frozen_bad = 0, []
    for line in MAN.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path, _, expected = line.partition("|")
        p = ROOT / path
        if not p.exists():
            frozen_bad.append((path, "MISSING"))
            continue
        if sha(p) == expected:
            frozen_ok += 1
        else:
            frozen_bad.append((path, "HASH-MISMATCH"))
    return files, frozen_ok, frozen_bad


files, ok, bad = snapshot()
mode = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
print(f"frozen inputs (manifest): {ok}/182 hashes OK, {len(bad)} problems")
for b in bad[:10]:
    print("  FROZEN-PROBLEM:", b)
if mode == "snapshot":
    SNAP.write_text(json.dumps({"files": files}, indent=1), encoding="utf-8")
    print(f"snapshot saved: {len(files)} experiment/manifest files hashed")
else:
    prev = json.loads(SNAP.read_text(encoding="utf-8"))["files"]
    changed = [k for k in files if prev.get(k) != files[k]]
    removed = [k for k in prev if k not in files]
    added = [k for k in files if k not in prev]
    print("changed since snapshot:", changed if changed else "(none)")
    print("removed:", removed if removed else "(none)")
    print("added:", added if added else "(none)")
