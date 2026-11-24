#!/usr/bin/env python3
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MAN = Path(__file__).resolve().parents[1] / "benchmark_input_manifest_sha256_20260909.txt"
lines = MAN.read_text(encoding="utf-8-sig").splitlines()
nonempty = [l for l in lines if l.strip()]
comments = [l for l in nonempty if l.lstrip().startswith("#")]
entries = [l for l in nonempty if not l.lstrip().startswith("#")]
print(f"total={len(lines)} nonempty={len(nonempty)} comments={len(comments)} entries={len(entries)}")
print("comment lines:", comments)
fmt_pipe = sum(1 for l in entries if "|" in l)
fmt_space = sum(1 for l in entries if "|" not in l and len(l) >= 66 and l[64:66] == "  ")
print(f"pipe-format={fmt_pipe} sha256-two-space-format={fmt_space} other={len(entries)-fmt_pipe-fmt_space}")
paths = [l.split("|")[0] for l in entries if "|" in l]
print("unique paths:", len(set(paths)))
ht = [p for p in paths if "hidden_tests" in p]
fx = [p for p in paths if "fixture_repos" in p]
print(f"hidden_tests={len(ht)} fixture_repos={len(fx)} other={len(paths)-len(ht)-len(fx)}")
for p in paths:
    if "fixture_repos" not in p and "hidden_tests" not in p:
        print("  other-entry:", p)
