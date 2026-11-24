#!/usr/bin/env python3
"""Post-edit read-only consistency check (v2).

1) Recomputes all metrics from task_ledger.json / raw JSONs.
2) Verifies the updated FINAL_REPORT.md / resume_metrics.md contain the
   correct figures and no stale ones outside the Harness/Audit Notes.
Prints PASS/FAIL per check. Reads only.
"""
import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1] / "results" / "nara_laguna_archstrong_final30_final_20260910"
TASK_IDS = [f"task_{i:03d}" for i in range(1, 31)]

with open(ROOT / "task_ledger.json", encoding="utf-8") as f:
    entries = json.load(f)["entries"]
paired = json.load(open(ROOT / "paired_analysis.json", encoding="utf-8"))
analysis = json.load(open(ROOT / "analysis.json", encoding="utf-8"))

L = {t: {} for t in TASK_IDS}
for e in entries:
    L[e["task_id"]][e["system"]] = e
VALID = ("resolved", "genuine_agent_failure")
mv = [L[t]["multi_agent"] for t in TASK_IDS if L[t]["multi_agent"]["FINAL_CLASSIFICATION"] in VALID]
mv23 = [e for e in mv if e["task_id"] != "task_002"]
bv = [L[t]["baseline_b"] for t in TASK_IDS if L[t]["baseline_b"]["FINAL_CLASSIFICATION"] in VALID]

fr = (ROOT / "FINAL_REPORT.md").read_text(encoding="utf-8")
rm = (ROOT / "resume_metrics.md").read_text(encoding="utf-8")
marker = "## 25. Harness / Audit Notes"
assert marker in fr, "Harness/Audit Notes section missing"
fr_body, fr_notes = fr.split(marker, 1)
norm_notes = " ".join(fr_notes.split())  # whitespace-normalized for cross-line phrase checks

results = []
def check(name, ok):
    results.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

gt = {
    "multi_final": sum(1 for e in mv if e["final_resolved"]),
    "base_final": sum(1 for e in bv if e["final_resolved"]),
    "multi_fp": sum(1 for e in mv if e["first_pass_resolved"]),
    "base_fp": sum(1 for e in bv if e["first_pass_resolved"]),
    "hidden_exec": sum(1 for e in mv if e["hidden_tests_executed"]),
    "hidden_pass": sum(1 for e in mv if e["hidden_tests_executed"] and e["hidden_tests_passed"]),
    "run_weighted_pct": round(100 * 17 / 23, 1),
    "lat_mean": round(statistics.mean(e["latency_seconds"] for e in mv23), 1),
    "tok_mean": round(statistics.mean(e["total_tokens"] for e in mv23)),
    "calls_mean": round(statistics.mean(e["llm_calls"] for e in mv23), 2),
    "cost_mean": round(statistics.mean(e["cost"] for e in mv23), 5),
    "attempts_all_valid_multi": round(sum(e["repair_attempts"] for e in mv) / 30, 2),
    "attempts_all_valid_base": round(sum(e["repair_attempts"] for e in bv) / 30, 2),
    "attempts_among_elig_multi": round(sum(e["repair_attempts"] for e in mv if e["repair_eligible"]) / 9, 2),
    "attempts_among_elig_base": round(sum(e["repair_attempts"] for e in bv if e["repair_eligible"]) / 10, 2),
}
print("ground truth recomputed:", gt)

print("\nFINAL_REPORT.md figures:")
check("17/30 (56.7%) multi final", "17/30 (56.7%)" in fr)
check("24/30 (80.0%) baseline final", "24/30 (80.0%)" in fr)
check("first-pass 15/24 valid", "15/24 valid (50.0% of 30)" in fr)
check("first-pass 20/30 baseline", "20/30 (66.7%)" in fr)
check("paired 17/24 (70.8%) & 19/24 (79.2%)", "17/24 (70.8%)" in fr and "19/24 (79.2%)" in fr)
check("paired first-pass 15/24 & 16/24", "15/24 (62.5%)" in fr and "16/24 (66.7%)" in fr)
check("outcome counts 16/1/3/4", "both solved 16" in fr and "multi only 1" in fr and "baseline only 3" in fr and "neither 4" in fr)
check("McNemar p=0.625", "p = 0.625" in fr and "p=0.625" in fr)
check("73.9% of EXECUTED runs (17/23)", "73.9% of EXECUTED runs (17/23" in fr)
check("stale 74.7% gone from whole file", "74.7" not in fr)
check("§5 stored smoke: 19+/3− and 4 calls", "(19+/3−" in fr_body and "(4 calls)" in fr_body)
check("§1–24 stale smoke numbers removed", "15+/3−" not in fr_body and "(6 calls)" not in fr_body)
check("stale figures only in Notes, marked superseded", "15+/3−" in fr_notes and "(6 LLM calls," in fr_notes and "no longer exists" in norm_notes)
check("§6 breakdown sums to 182", "30 task-spec JSONs + 31 hidden-test files" in fr and "+ 120 fixture files + 1 config = 182" in fr)
check("§15 no '3×' claim", "3×\nsyntax-invalid" not in fr and "3× syntax-invalid" not in fr)
check("§15 single syntax-gate rejection described", "rejected once by the syntax gate" in fr and "['syntax_valid']" in fr)
check("§15 observed stage execution (3 calls, no test-gen)", "3 calls total, with no" in fr and "test-generation call" in fr)
check("§16 localization 23/23 & 30/30, 0 hallucinated", "23/23 evaluable (100%)" in fr and "30/30 (100%)" in fr and "Hallucinated target files: 0 in both" in fr)
check("§14 repair 2/9 (22.2%) & 4/10 (40.0%)", "2/9 (22.2%)" in fr and "4/10 (40.0%)" in fr)
check("§14 both attempt conventions stated", "over ALL valid runs (÷30) multi_agent 0.23 and baseline_b 0.57" in fr
      and "multi_agent 0.33 (3 attempts / 9 eligible) and baseline_b 1.70 (17 / 10) on" in fr and "1.62 on the paired 24" in fr)
check("attempt figures match ledger", gt["attempts_all_valid_multi"] == 0.23 and gt["attempts_all_valid_base"] == 0.57
      and gt["attempts_among_elig_multi"] == 0.33 and gt["attempts_among_elig_base"] == 1.70)
check("efficiency stats match 23-run denominator",
      gt["lat_mean"] == 70.8 and gt["tok_mean"] == 5633 and gt["calls_mean"] == 4.61 and gt["cost_mean"] == 0.00379)
check("Harness/Audit Notes present", marker in fr)
check("notes: task_002 passed-count inconsistency documented", "164/171" in fr_notes and "17/23 runs all-pass" in fr_notes and "not altered" in fr_notes)
check("notes: task_009 overwrite documented", "overwrote the first" in norm_notes and "authoritative first-pass record" in norm_notes)
check("notes: HTTP-200 upstream_error classification documented", "upstream_error" in fr_notes and "request IDs" in fr_notes)

print("\nresume_metrics.md figures:")
check("Metric 1 claim intact (17/24 vs 19/24, p=0.625)", "17/24 (70.8%) vs 19/24 (79.2%)" in rm and "p=0.625" in rm)
check("Metric 2 claim intact (23/23)", "23/23 evaluable tasks" in rm)
check("Metric 3 claim intact (4/10, 2/9)", "4/10 (40%)" in rm and "2/9 (22.2%)" in rm)
check("Metric 4 values intact (5.3×, 3.7×, $0.00379/$0.00071, 70.8/19.3)",
      "5.3×" in rm and "3.7×" in rm and "$0.00379 vs $0.00071" in rm and "70.8s vs 19.3s" in rm)
check("Metric 4 denominator caveat updated", "23 of 24 valid multi-agent runs that produced output" in rm)
check("old '23 valid runs' wording gone", "23 valid multi_agent runs, 30 baseline_b runs" not in rm)
check("Metric 5 claim intact (6/60)", "6/60" in rm)

print("\ncross-artifact agreement:")
check("paired_analysis agrees with ledger", paired["task_count"] == 24 and paired["outcome_counts"] == {"both_solved": 16, "multi_only": 1, "baseline_only": 3, "neither_solved": 4}
      and paired["multi_agent"]["final_resolved"] == 17 and paired["baseline_b"]["final_resolved"] == 19
      and paired["mcnemar_exact_p_two_sided"] == 0.625)
check("analysis.json full-30 blocks agree with ledger", analysis["raw_full_30"]["multi_agent"]["final_resolved"] == 17
      and analysis["raw_full_30"]["baseline_b"]["final_resolved"] == 24
      and analysis["raw_full_30"]["multi_agent"]["repair_attempts_mean"] == 0.2
      and analysis["raw_full_30"]["baseline_b"]["repair_attempts_mean"] == 1.7)

fails = [n for n, ok in results if not ok]
print(f"\nRESULT: {len(results) - len(fails)}/{len(results)} checks passed" + (f"; FAILURES: {fails}" if fails else " — all consistent"))
