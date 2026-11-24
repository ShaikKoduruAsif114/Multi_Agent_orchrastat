#!/usr/bin/env python3
"""Part 2: efficiency denominators, percentile methods, repair means, spot checks.

Read-only. Verifies FINAL_REPORT.md and resume_metrics.md efficiency and
repair-attempt numbers against task_ledger.json with explicit denominator
tests, plus manifest line count and contaminated-run timestamps.
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "results" / "nara_laguna_archstrong_final30_final_20260910"
TASK_IDS = [f"task_{i:03d}" for i in range(1, 31)]
SYSTEMS = ("multi_agent", "baseline_b")

with open(ROOT / "task_ledger.json", encoding="utf-8") as f:
    entries = json.load(f)["entries"]

L = {t: {} for t in TASK_IDS}
for e in entries:
    L[e["task_id"]][e["system"]] = e

VALID = ("resolved", "genuine_agent_failure")
multi_valid = [L[t]["multi_agent"] for t in TASK_IDS if L[t]["multi_agent"]["FINAL_CLASSIFICATION"] in VALID]
base_valid = [L[t]["baseline_b"] for t in TASK_IDS if L[t]["baseline_b"]["FINAL_CLASSIFICATION"] in VALID]

# candidate multi denominators
def show(name, es):
    lat = sorted(e["latency_seconds"] for e in es)
    tok = sorted(e["total_tokens"] for e in es)
    calls = [e["llm_calls"] for e in es]
    costs = [e["cost"] for e in es]
    q = statistics.quantiles(lat, n=100, method="inclusive")[94] if len(lat) > 1 else lat[0]
    print(f"{name:<38} n={len(es):2d}  lat mean={statistics.mean(lat):6.1f} med={statistics.median(lat):6.1f} p95lin={q:6.1f}  "
          f"tok mean={statistics.mean(tok):6.0f} med={statistics.median(tok):6.0f}  calls={statistics.mean(calls):.2f}  "
          f"cost tot={sum(costs):.4f} mean={statistics.mean(costs):.5f}")

print("== multi_agent denominator candidates (report: 70.8 / 63.4 / 101.3, tok 5633/5802, calls 4.61, $0.0873/$0.00379) ==")
show("all 30", [L[t]["multi_agent"] for t in TASK_IDS])
show("24 valid", multi_valid)
mv23 = [e for e in multi_valid if e["task_id"] != "task_002"]
show("23 valid minus task_002 (no output)", mv23)
excl = [t for t in TASK_IDS if L[t]["multi_agent"]["FINAL_CLASSIFICATION"] == "provider_failure"]
show("30 minus 4 pure-502 runs (task_021/029 in)", [L[t]["multi_agent"] for t in TASK_IDS if t not in ("task_007", "task_010", "task_011", "task_027")])

print("\n== baseline_b denominator candidates (report: 19.3 / 14.2 / 36.8, tok 1070/729, calls 2.57, $0.0212/$0.00071) ==")
show("all 30 (== valid)", base_valid)

print("\n== which tasks are in the multi 23-run set? ==")
print(sorted(e["task_id"] for e in mv23))
print("task_002 latency/tok/cost:", L["task_002"]["multi_agent"]["latency_seconds"],
      L["task_002"]["multi_agent"]["total_tokens"], L["task_002"]["multi_agent"]["cost"])

print("\n== repair attempts among eligible ==")
for sysname, valid in (("multi_agent", multi_valid), ("baseline_b", base_valid)):
    elig = [e for e in valid if e["repair_eligible"]]
    s = sum(e["repair_attempts"] for e in elig)
    print(f"{sysname}: eligible={len(elig)} attempts_sum={s} mean={s/len(elig):.3f} tasks={[(e['task_id'], e['repair_attempts'], e['repair_recovered']) for e in elig]}")

print("\n== hidden-test pass rate of executed (multi_agent) ==")
ex = [e for e in multi_valid if e["hidden_tests_executed"]]
ps = sum(1 for e in ex if e["hidden_tests_passed"])
print(f"executed={len(ex)} passed={ps} rate={ps/len(ex):.4f}  (report says 74.7% -- recheck)")

print("\n== multi localization non-evaluable tasks (report: 6 provider + 1 gate) ==")
noneval = [t for t in TASK_IDS if not L[t]["multi_agent"]["localization_evaluable"]]
print(noneval, "classifications:", [L[t]["multi_agent"]["FINAL_CLASSIFICATION"] for t in noneval])

print("\n== paired outcome detail (which tasks in each cell) ==")
paired = json.load(open(ROOT / "paired_analysis.json", encoding="utf-8"))["tasks"]
for t in paired:
    m, b = L[t]["multi_agent"], L[t]["baseline_b"]
    cell = ("both" if m["final_resolved"] and b["final_resolved"] else
            "multi_only" if m["final_resolved"] else
            "baseline_only" if b["final_resolved"] else "neither")
    print(f"  {t}: {cell:<13} multi={m['FINAL_CLASSIFICATION']:<22} baseline={b['FINAL_CLASSIFICATION']}")

print("\n== contaminated run timestamps (502 burst window claim 22:00-22:50Z) ==")
for t in TASK_IDS:
    e = L[t]["multi_agent"]
    if e["FINAL_CLASSIFICATION"] == "provider_failure":
        r = json.load(open(ROOT / "raw" / f"{t}_multi_agent.json", encoding="utf-8"))
        print(f"  {t}: ts={r.get('timestamp')} status={r['execution']['status']}")

print("\n== manifest line count (report: 182 files) ==")
mp = Path(__file__).resolve().parents[1] / "benchmark_input_manifest_sha256_20260909.txt"
lines = [l for l in mp.read_text(encoding="utf-8").splitlines() if l.strip()]
print(f"manifest lines: {len(lines)}")

print("\n== served models distinct ==")
served = set()
for t in TASK_IDS:
    for s in SYSTEMS:
        served.update(L[t][s].get("served_model") or [])
        served.update(json.load(open(ROOT / "raw" / f"{t}_{s}.json", encoding="utf-8"))["provider"]["served_models"])
print(sorted(served))

print("\n== resume Metric 4 ratios ==")
print(f"  cost ratio 0.00379/0.00071 = {0.00379/0.00071:.2f}  (claim 5.3x)")
print(f"  token ratio 5633/1070 = {5633/1070:.2f}  (claim 5.3x)")
print(f"  latency ratio 70.8/19.3 = {70.8/19.3:.2f}  (claim 3.7x)")
