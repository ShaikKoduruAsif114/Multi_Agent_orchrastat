#!/usr/bin/env python3
"""Probe: what does 74.7% correspond to? Test-case-weighted hidden-test pass rate using raw passed_count."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "results" / "nara_laguna_archstrong_final30_final_20260910"
TASK_IDS = [f"task_{i:03d}" for i in range(1, 31)]

tot = passed = 0
rows = []
for t in TASK_IDS:
    r = json.load(open(ROOT / "raw" / f"{t}_multi_agent.json", encoding="utf-8"))
    reg = r.get("regression") or {}
    if reg.get("hidden_tests_executed"):
        pc = reg.get("hidden_tests_passed_count")
        tc = reg.get("hidden_tests_total")
        rows.append((t, pc, tc, reg.get("hidden_tests_passed")))
        tot += tc or 0
        passed += pc or 0
for row in rows:
    print("  ", row)
print(f"test-weighted: {passed}/{tot} = {passed/tot:.4f} = {100*passed/tot:.1f}%")
print(f"run-weighted: 17/23 = {17/23:.4f} = {100*17/23:.1f}%")
