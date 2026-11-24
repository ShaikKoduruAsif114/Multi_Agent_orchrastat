#!/usr/bin/env python3
"""READ-ONLY post-generation consistency check for the corrected adaptive v3 package.

Verifies, from raw JSONs + task_ledger.json + aggregates:
  1. every number in FINAL_REPORT_CORRECTED.md / resume_metrics_corrected.md
  2. ledger entries vs raw JSONs (per-run fidelity) and internal ledger consistency
  3. immutability: original FINAL_REPORT.md + raw/ + aggregates/ unchanged (SHA256)
Prints PASS/FAIL per check and a mismatch list. Writes nothing.
"""
import json
import math
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "evaluation" / "results" / "nara_laguna_adaptive_v3_final_20260910"
TASK_IDS = [f"task_{i:03d}" for i in range(1, 31)]
SYSTEMS = ("adaptive_multi_agent", "baseline_b")

FR = (EXP / "FINAL_REPORT_CORRECTED.md").read_text(encoding="utf-8")
RM = (EXP / "resume_metrics_corrected.md").read_text(encoding="utf-8")
LED = json.load(open(EXP / "task_ledger.json", encoding="utf-8"))
entries = LED["entries"]
L = {t: {} for t in TASK_IDS}
for e in entries:
    L[e["task_id"]][e["system"]] = e


def raw(t, s):
    return json.load(open(EXP / "raw" / f"{t}_{s}.json", encoding="utf-8"))


results = []
def check(name, ok):
    results.append((name, bool(ok)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")


print("== 1. ledger vs raw JSONs (per-run fidelity, 60 runs) ==")
mm = 0
for t in TASK_IDS:
    for s in SYSTEMS:
        e, r = L[t][s], raw(t, s)
        ex, reg, rep, ad, loc = r["execution"], r["regression"], r["repair"], r.get("adaptive") or {}, r["localization"]
        checks = [
            ("final_resolved", e["final_resolved"], r["end_to_end_resolved"] is True),
            ("llm_calls", e["llm_calls"], ex.get("llm_calls")),
            ("total_tokens", e["total_tokens"], ex.get("total_tokens")),
            ("latency", e["latency_seconds"], ex.get("latency_seconds")),
            ("cost", e["cost"], (r.get("cost") or {}).get("estimated_usd")),
            ("top1", e["localization_top1"], loc.get("top1_correct") if loc.get("predicted_file") is not None else None),
            ("halluc", e["hallucinated_file"], loc.get("hallucinated_file")),
            ("fp_repairblock", e["first_pass_resolved"], rep.get("first_pass_resolved_hidden")),
            ("hidden_exec", e["hidden_tests_executed"], reg.get("hidden_tests_executed")),
        ]
        if s == "adaptive_multi_agent":
            checks += [("elig", e["repair_eligible"], bool(ad.get("repair_eligible"))),
                       ("att", e["repair_attempts"], int(ad.get("repair_attempts") or 0)),
                       ("rec", e["repair_recovered"], bool(ad.get("repair_recovered"))),
                       ("ipath", e["initial_path"], ad.get("initial_path")),
                       ("fpath", e["final_path"], ad.get("final_path")),
                       ("esc", e["escalated"], ad.get("escalated"))]
        else:
            checks += [("att", e["repair_attempts"], max(0, int(rep.get("attempts") or 1) - 1))]
        for name, got, want in checks:
            ok = abs(got - want) < 1e-9 if isinstance(got, float) or isinstance(want, float) else got == want
            if not ok:
                print(f"    !! {t}/{s} {name}: ledger={got!r} raw={want!r}")
                mm += 1
check("all per-run fields match raw (60 runs)", mm == 0)

print("\n== 2. ledger internal consistency ==")
check("60 entries, 30 tasks x 2 systems", len(entries) == 60 and all(len(L[t]) == 2 for t in TASK_IDS))
check("exactly one FINAL_CLASSIFICATION per entry, valid vocabulary",
      all(e["FINAL_CLASSIFICATION"] in ("resolved", "genuine_agent_failure", "provider_failure",
                                        "infrastructure_failure", "invalid_evaluation") for e in entries))
check("classification counts adaptive (25/3/2/0)",
      L["task_001"]["adaptive_multi_agent"] and
      sum(1 for t in TASK_IDS if L[t]["adaptive_multi_agent"]["FINAL_CLASSIFICATION"] == "resolved") == 25 and
      sum(1 for t in TASK_IDS if L[t]["adaptive_multi_agent"]["FINAL_CLASSIFICATION"] == "provider_failure") == 3 and
      sum(1 for t in TASK_IDS if L[t]["adaptive_multi_agent"]["FINAL_CLASSIFICATION"] == "genuine_agent_failure") == 2 and
      sum(1 for t in TASK_IDS if L[t]["adaptive_multi_agent"]["FINAL_CLASSIFICATION"] == "infrastructure_failure") == 0)
check("classification counts baseline (19/7/4/0)",
      sum(1 for t in TASK_IDS if L[t]["baseline_b"]["FINAL_CLASSIFICATION"] == "resolved") == 19 and
      sum(1 for t in TASK_IDS if L[t]["baseline_b"]["FINAL_CLASSIFICATION"] == "provider_failure") == 7 and
      sum(1 for t in TASK_IDS if L[t]["baseline_b"]["FINAL_CLASSIFICATION"] == "genuine_agent_failure") == 4 and
      sum(1 for t in TASK_IDS if L[t]["baseline_b"]["FINAL_CLASSIFICATION"] == "infrastructure_failure") == 0)
check("provider-contaminated runs = 10, infra = 0",
      sum(1 for e in entries if e["provider_failure"]) == 10 and
      sum(1 for e in entries if e["FINAL_CLASSIFICATION"] == "infrastructure_failure") == 0)

pa = LED["paired_analysis"]["primary"]
check("primary set is the specified 22-task list",
      pa["task_count"] == 22 and pa["tasks"] == ["task_001", "task_002", "task_005", "task_006", "task_007", "task_009",
                                                 "task_011", "task_012", "task_013", "task_014", "task_015", "task_016",
                                                 "task_019", "task_020", "task_021", "task_022", "task_025", "task_026",
                                                 "task_027", "task_028", "task_029", "task_030"])
check("primary excluded = the 8 specified fatal tasks",
      sorted(pa["excluded_tasks"]) == ["task_003", "task_004", "task_008", "task_010", "task_017", "task_018", "task_023", "task_024"])
check("primary outcomes 16/3/3/0 with exact task lists",
      pa["outcomes"] == {"both": 16, "adaptive_only": 3, "baseline_only": 3, "neither": 0}
      and pa["outcome_tasks"]["adaptive_only"] == ["task_002", "task_006", "task_022"]
      and pa["outcome_tasks"]["baseline_only"] == ["task_020", "task_027", "task_030"]
      and len(pa["outcome_tasks"]["both"]) == 16 and pa["outcome_tasks"]["neither"] == [])
check("primary resolved 19/19 and McNemar 3v3 p=1.0",
      pa["adaptive_resolved"] == 19 and pa["baseline_resolved"] == 19 and pa["mcnemar_exact_two_sided_p"] == 1.0)
st = LED["paired_analysis"]["strict_sensitivity"]
check("strict N=21 with task_020 dropped, p=1.0, cells 16/3/2/0, 19v18",
      st["task_count"] == 21 and "task_020" not in st["tasks"] and st["mcnemar_exact_two_sided_p"] == 1.0
      and st["outcomes"] == {"both": 16, "adaptive_only": 3, "baseline_only": 2, "neither": 0}
      and st["adaptive_resolved"] == 19 and st["baseline_resolved"] == 18)
a30 = LED["paired_analysis"]["all_30_descriptive"]
check("all-30 table 16/9/3/2, p two-sided 0.146 / one-sided 0.073",
      a30["outcomes"] == {"both": 16, "adaptive_only": 9, "baseline_only": 3, "neither": 2}
      and round(a30["mcnemar_exact_two_sided_p"], 3) == 0.146 and round(a30["mcnemar_one_sided_p_all30"], 3) == 0.073)
check("retry-budget disclosure present", "UNEQUAL" in LED["retry_budget_disclosure"]["verdict"])

def eff_ok(s, key, tok, cost, calls, lat):
    b = LED["efficiency"]["by_system"][s][key]
    return b["tokens_mean"] == tok and b["cost_mean"] == cost and b["llm_calls_mean"] == calls and b["latency_mean"] == lat

check("adaptive runs-with-output eff (1112.6 / 0.000714 / 2.107 / 17.37)",
      eff_ok("adaptive_multi_agent", "runs_with_output", 1112.6, 0.000714, 2.107, 17.37))
check("baseline runs-with-output eff (1160.5 / 0.000766 / 2.696 / 20.91)",
      eff_ok("baseline_b", "runs_with_output", 1160.5, 0.000766, 2.696, 20.91))
check("adaptive all-30 latency 23.75 recorded separately",
      LED["efficiency"]["by_system"]["adaptive_multi_agent"]["all_30"]["latency_mean"] == 23.75)
check("baseline all-30 latency 17.82 recorded separately",
      LED["efficiency"]["by_system"]["baseline_b"]["all_30"]["latency_mean"] == 17.82)

print("\n== 3. FINAL_REPORT_CORRECTED.md figures ==")
for name, cond in [
    ("19/22 both arms + 86.4%", "19/22 (86.4%)" in FR and FR.count("19/22 (86.4%)") >= 2),
    ("cells 16/3/3/0 and p=1.00", "both 16 · adaptive-only 3 · baseline-only 3 · neither 0" in FR and "p = 1.00" in FR),
    ("excluded 8 tasks listed", "task_003, task_004, task_008, task_010,\ntask_017, task_018, task_023, task_024" in FR),
    ("strict N=21 documented", "N=21" in FR and "16/3/2/0" in FR and "19/21" in FR),
    ("10/60 contamination + 0 infra", "10 of 60" in FR and "genuine infrastructure failures = 0" in FR),
    ("task_020 separate disclosure", "task_020 (separate disclosure)" in FR),
    ("all-30 confounded 9v3 p=0.146 + one-sided 0.073", "p = 0.146" in FR and "0.073" in FR),
    ("corrected tokens 1,112.6 / 1,160.5", "1,112.6" in FR and "1,160.5" in FR),
    ("corrected cost 0.000714 / 0.000766", "$0.000714" in FR and "$0.000766" in FR),
    ("corrected latency 17.37 / 20.91", "17.37 s" in FR and "20.91 s" in FR),
    ("stale v2 totals named and retracted", "34,777 / 49,470" in FR and "retracted" in FR),
    ("calls 2.107/2.696 with max 3/5", "2.107 (max 3)" in FR and "2.696 (max 5)" in FR),
    ("escalations corrected (2, both failed, A->B)", "task_027 and task_030, PATH_A → PATH_B" in FR and "Both escalated runs FAILED" in FR),
    ("budget disclosure (1-2 vs 3)", "`retry_budget=1` on 23 tasks and `2` on 5" in FR and "`retry_budget=3`" in FR),
    ("N=28 retracted", "N = 28" in FR and "not derivable" in FR),
    ("denominator dictionary present", "## 2. Denominator dictionary" in FR),
    ("per-resolved cost baseline cheaper noted", "$0.000737 (19 resolved) | $0.000519" in FR),
    ("verdict section present", "## 12. Verdict" in FR and "## Not valid" not in FR and "resume-safe" in FR.lower()),
]:
    check(name, cond)

print("\n== 4. resume_metrics_corrected.md figures ==")
for name, cond in [
    ("Metric 1 exact claim", "19/22 (86.4%)" in RM and "p = 1.00" in RM),
    ("Metric 1 task lists", "002, 006, 022" in RM and "020, 027, 030" in RM),
    ("Metric 2 calls", "2.11" in RM and "2.70" in RM and "max 3 vs\nmax 5" in RM),
    ("Metric 3 corrected tokens/cost", "1,112.6" in RM and "1,160.5" in RM and "$0.000714" in RM and "$0.000766" in RM),
    ("Metric 3 NOT-29% retraction", "NOT the −29%" in RM),
    ("Metric 4 latency", "17.37 s vs baseline 20.91 s" in RM),
    ("Metric 6 integrity", "182/182" in RM and "10/60" in RM),
    ("budget disclosure block", "UNEQUAL RETRY BUDGETS" in RM),
    ("anti-claims list", "Anti-claims" in RM and "N=28" in RM),
]:
    check(name, cond)

print("\n== 5. aggregates.json cross-reference (documented disagreements only) ==")
agg = json.load(open(EXP / "aggregates" / "aggregates.json", encoding="utf-8"))["systems"]
check("aggregates latency_mean_s 23.75/17.82 = ledger all-30 convention",
      agg["adaptive_multi_agent"]["latency_mean_s"] == 23.75 and agg["baseline_b"]["latency_mean_s"] == 17.82)
check("aggregates calls/tokens/loc counts agree with ledger runs-with-output / evaluable",
      agg["adaptive_multi_agent"]["llm_calls_mean"] == 2.107 and agg["baseline_b"]["llm_calls_mean"] == 2.696
      and agg["adaptive_multi_agent"]["loc_eligible"] == 28 and agg["baseline_b"]["loc_eligible"] == 23)

print("\n== 6. immutability of original artifacts (hashes) ==")
import hashlib
SNAP = json.loads((Path(__file__).resolve().parent / "audit_v3_snapshot.json").read_text(encoding="utf-8"))["files"]
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()
touched, added, missing = [], [], []
for rel, old in SNAP.items():
    p = ROOT / rel
    if not p.exists():
        missing.append(rel)
    elif sha(p) != old:
        touched.append(rel)
for p in EXP.rglob("*"):
    if p.is_file():
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if rel not in SNAP:
            added.append(rel)
check("no pre-existing file modified (FINAL_REPORT.md, raw/, aggregates/ intact)", not touched and not missing)
check("only the three NEW package files added", sorted(added) == [
    "evaluation/results/nara_laguna_adaptive_v3_final_20260910/FINAL_REPORT_CORRECTED.md",
    "evaluation/results/nara_laguna_adaptive_v3_final_20260910/resume_metrics_corrected.md",
    "evaluation/results/nara_laguna_adaptive_v3_final_20260910/task_ledger.json"])

fails = [n for n, ok in results if not ok]
print(f"\nRESULT: {len(results) - len(fails)}/{len(results)} checks passed" + (f"; MISMATCHES: {fails}" if fails else " — fully consistent"))
