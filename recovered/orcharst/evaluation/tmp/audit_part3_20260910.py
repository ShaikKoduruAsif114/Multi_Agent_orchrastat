#!/usr/bin/env python3
"""Part 3: manifest inspection, p95 method, 74.7% probe, repair-attempt conventions."""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "results" / "nara_laguna_archstrong_final30_final_20260910"
MAN = Path(__file__).resolve().parents[1] / "benchmark_input_manifest_sha256_20260909.txt"
TASK_IDS = [f"task_{i:03d}" for i in range(1, 31)]

print("== manifest head/tail and line classification ==")
lines = MAN.read_text(encoding="utf-8-sig").splitlines()
nonempty = [l for l in lines if l.strip()]
print(f"total lines={len(lines)} nonempty={len(nonempty)}")
for l in nonempty[:3]:
    print("  HEAD:", l[:100].encode("ascii", "replace").decode())
for l in nonempty[-2:]:
    print("  TAIL:", l[:100])
kinds = {"sha256 <two spaces> path": 0, "other": 0}
paths = []
for l in nonempty:
    if len(l) >= 66 and l[64:66] == "  ":
        kinds["sha256 <two spaces> path"] += 1
        paths.append(l[66:])
    else:
        kinds["other"] += 1
print(kinds)
print("unique paths:", len(set(paths)))
exts = {}
for p in paths:
    ext = Path(p).suffix or "(none)"
    exts[ext] = exts.get(ext, 0) + 1
print("by extension:", dict(sorted(exts.items(), key=lambda kv: -kv[1])))
print("hidden_tests files:", sum(1 for p in paths if "hidden_tests" in p))
print("fixture_repos files:", sum(1 for p in paths if "fixture_repos" in p))
print("config-ish files:", sum(1 for p in paths if p.endswith(".json") and "fixture" not in p and "hidden" not in p))

with open(ROOT / "task_ledger.json", encoding="utf-8") as f:
    entries = json.load(f)["entries"]
L = {t: {} for t in TASK_IDS}
for e in entries:
    L[e["task_id"]][e["system"]] = e

VALID = ("resolved", "genuine_agent_failure")
multi_valid = [L[t]["multi_agent"] for t in TASK_IDS if L[t]["multi_agent"]["FINAL_CLASSIFICATION"] in VALID]
mv23 = [e for e in multi_valid if e["task_id"] != "task_002"]
base_all = [L[t]["baseline_b"] for t in TASK_IDS]

def p95_methods(vals, label):
    s = sorted(vals)
    n = len(s)
    import math
    nearest = s[math.ceil(0.95 * n) - 1]
    lower = s[max(0, math.ceil(0.95 * n) - 2)]
    q = statistics.quantiles(s, n=100, method="inclusive")[94]
    qe = statistics.quantiles(s, n=100, method="exclusive")[94]
    idx = int(0.95 * (n - 1))
    print(f"{label:<28} n={n:2d} nearest={nearest:7.1f} lower={lower:7.1f} incl={q:7.1f} excl={qe:7.1f} numpy-idx={s[idx]:7.1f}")

print("\n== p95 candidates (report: multi 101.3, baseline 36.8) ==")
p95_methods([e["latency_seconds"] for e in mv23], "multi 23 (valid minus 002)")
p95_methods([e["latency_seconds"] for e in multi_valid], "multi 24 valid")
p95_methods([e["latency_seconds"] for e in base_all], "baseline 30")
paired = json.load(open(ROOT / "paired_analysis.json", encoding="utf-8"))["tasks"]
p95_methods([L[t]["baseline_b"]["latency_seconds"] for t in paired], "baseline paired 24")
p95_methods([L[t]["multi_agent"]["latency_seconds"] for t in paired], "multi paired 24")
res_only = [e for e in base_all if e["FINAL_CLASSIFICATION"] == "resolved"]
p95_methods([e["latency_seconds"] for e in res_only], "baseline resolved-only 24")
res_only_m = [e for e in mv23 if e["FINAL_CLASSIFICATION"] == "resolved"]
p95_methods([e["latency_seconds"] for e in res_only_m], "multi 23 resolved-only 17")

print("\n== 74.7% probe: test-case-weighted hidden-test pass rate (multi) ==")
ex = [e for e in multi_valid if e["hidden_tests_executed"]]
tot_all = sum(e["hidden_tests_total"] or 0 for e in ex)
tot_pass = sum(e["hidden_tests_total"] or 0 for e in ex if e["hidden_tests_passed"])
print(f"run-weighted: 17/{len(ex)} = {17/len(ex):.4f}")
print(f"test-weighted: {tot_pass}/{tot_all} = {tot_pass/tot_all:.4f}")
per = [(e["task_id"], e["hidden_tests_total"]) for e in ex]
print(per)

print("\n== repair_attempts conventions ==")
mv = multi_valid
bv = base_all
m_el = [e for e in mv if e["repair_eligible"]]
b_el = [e for e in bv if e["repair_eligible"]]
print(f"multi : sum_valid={sum(e['repair_attempts'] for e in mv)}  /30={sum(e['repair_attempts'] for e in mv)/30:.4f}  among_elig={sum(e['repair_attempts'] for e in m_el)/len(m_el):.4f}")
print(f"base  : sum_valid={sum(e['repair_attempts'] for e in bv)}  /30={sum(e['repair_attempts'] for e in bv)/30:.4f}  among_elig={sum(e['repair_attempts'] for e in b_el)/len(b_el):.4f}")
m_el_p = [L[t]['multi_agent'] for t in paired if L[t]['multi_agent']['repair_eligible']]
b_el_p = [L[t]['baseline_b'] for t in paired if L[t]['baseline_b']['repair_eligible']]
print(f"multi paired among_elig={sum(e['repair_attempts'] for e in m_el_p)/len(m_el_p):.4f} (paired_analysis says 0.33)")
print(f"base  paired among_elig={sum(e['repair_attempts'] for e in b_el_p)/len(b_el_p):.4f} (paired_analysis says 1.62)")
print("base paired eligible tasks:", [(e['task_id'], e['repair_attempts']) for e in b_el_p])

print("\n== multi contaminated runs: attempts & fields ==")
for t in TASK_IDS:
    e = L[t]["multi_agent"]
    if e["FINAL_CLASSIFICATION"] == "provider_failure":
        print(f"  {t}: repair_attempts={e['repair_attempts']} latency={e['latency_seconds']} tokens={e['total_tokens']} cost={e['cost']}")
