#!/usr/bin/env python3
"""Read-only audit of experiment nara_laguna_archstrong_final30_final_20260910.

Recomputes every reported metric from task_ledger.json and the 60 raw JSONs,
cross-checks FINAL_REPORT.md / resume_metrics.md / analysis.json /
paired_analysis.json, and prints exact task-ID sets + exclusion reasons.

Reads only. Never writes, reruns, or modifies anything.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "results" / "nara_laguna_archstrong_final30_final_20260910"
TASK_IDS = [f"task_{i:03d}" for i in range(1, 31)]
SYSTEMS = ("multi_agent", "baseline_b")


def load(name):
    with open(ROOT / name, encoding="utf-8") as f:
        return json.load(f)


def raw(task, system):
    p = ROOT / "raw" / f"{task}_{system}.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


ledger = load("task_ledger.json")["entries"]
analysis = load("analysis.json")
paired_analysis = load("paired_analysis.json")

L = {t: {} for t in TASK_IDS}
for e in ledger:
    L[e["task_id"]][e["system"]] = e

print(f"ledger entries: {len(ledger)} (expected 60); unique tasks: {len({e['task_id'] for e in ledger})} (expected 30)")

# ---------------------------------------------------------------- A. task sets
print()
print("=" * 78)
print("A. EXACT TASK-ID SETS (from ledger FINAL_CLASSIFICATION)")
print("=" * 78)


def reason(e):
    fc = e["FINAL_CLASSIFICATION"]
    if fc == "provider_failure":
        return (f"provider_failure: http={e.get('provider_http_status')}, "
                f"type={e.get('provider_error_type')}, msg={e.get('provider_error_message')}")
    if fc == "genuine_agent_failure":
        return f"genuine_agent_failure: first_pass_failure_category={e.get('first_pass_failure_category')}"
    return fc


sets = {}
for sysname in SYSTEMS:
    ok = [t for t in TASK_IDS if t in L and sysname in L[t] and L[t][sysname]["FINAL_CLASSIFICATION"] == "resolved"]
    fail = [t for t in TASK_IDS if t in L and sysname in L[t] and L[t][sysname]["FINAL_CLASSIFICATION"] != "resolved"]
    sets[sysname] = (ok, fail)
    entries = [L[t][sysname] for t in TASK_IDS]
    print(f"\n{sysname}: {len(ok)} resolved / {len(fail)} not-resolved (ledger entries={len(entries)}/30)")
    print(f"  resolved ({len(ok)}):")
    for t in ok:
        print(f"    {t}")
    print(f"  excluded from 'all-resolved' ({len(fail)}):")
    for t in fail:
        print(f"    {t}: {reason(L[t][sysname])}")

paired_clean = [t for t in TASK_IDS
                if all(t in L and s in L[t] for s in SYSTEMS)
                and all(L[t][s]["FINAL_CLASSIFICATION"] not in ("provider_failure", "infrastructure_failure", "invalid_evaluation") for s in SYSTEMS)]
excluded_paired = [t for t in TASK_IDS if t not in paired_clean]

print(f"\nPAIRED-CLEAN (both systems valid & uncontaminated), n={len(paired_clean)}:")
for t in paired_clean:
    print(f"    {t}")
print(f"EXCLUDED from paired-clean ({len(excluded_paired)}):")
for t in excluded_paired:
    rs = {s: L[t][s]["FINAL_CLASSIFICATION"] for s in SYSTEMS}
    detail = "; ".join(f"{s}={reason(L[t][s])}" for s in SYSTEMS if rs[s] != "resolved")
    print(f"    {t}: {detail}")

print("\nraw/ file presence:")
for sysname in SYSTEMS:
    missing = [t for t in TASK_IDS if raw(t, sysname) is None]
    print(f"  {sysname}: {30 - len(missing)}/30 raw JSONs" + (f"  MISSING: {missing}" if missing else ""))

# ------------------------------------------------- B. recompute per-system metrics
print()
print("=" * 78)
print("B. RECOMPUTED METRICS FROM LEDGER (full-30)")
print("=" * 78)


def stats(entries, valid_only):
    sel = [e for e in entries if (e["FINAL_CLASSIFICATION"] not in ("provider_failure", "infrastructure_failure", "invalid_evaluation")) or not valid_only]
    valid = [e for e in entries if e["FINAL_CLASSIFICATION"] not in ("provider_failure", "infrastructure_failure", "invalid_evaluation")]
    n_all, n_valid = len(entries), len(valid)
    out = {
        "n_all": n_all,
        "n_valid": n_valid,
        "final_resolved": sum(1 for e in valid if e["final_resolved"]),
        "first_pass_resolved": sum(1 for e in valid if e["first_pass_resolved"]),
        "repair_eligible": sum(1 for e in valid if e["repair_eligible"]),
        "repair_recovered": sum(1 for e in valid if e["repair_eligible"] and e["repair_recovered"]),
        "repair_attempts_sum": sum(e["repair_attempts"] for e in valid),
        "top1_evaluable": sum(1 for e in valid if e["localization_evaluable"]),
        "top1_correct": sum(1 for e in valid if e["localization_evaluable"] and e["localization_top1"]),
        "hallucinated": sum(1 for e in valid if e["hallucinated_file"]),
        "hidden_tests_executed": sum(1 for e in valid if e["hidden_tests_executed"]),
        "hidden_tests_passed": sum(1 for e in valid if e["hidden_tests_executed"] and e["hidden_tests_passed"]),
        "gen_tests_created": sum(1 for e in valid if e["generated_tests_created"]),
        "gen_tests_passed": sum(1 for e in valid if e["generated_tests_created"] and e["generated_tests_passed"]),
        "placeholder": sum(1 for e in valid if e["patch_placeholder"]),
        "syntax_fail": sum(1 for e in valid if e["patch_generated"] and e["patch_syntax_valid"] is False),
        "provider_contaminated": sum(1 for e in entries if e["provider_failure"]),
        "infrastructure": sum(1 for e in entries if e["FINAL_CLASSIFICATION"] == "infrastructure_failure"),
        "latencies": [e["latency_seconds"] for e in valid],
        "tokens": [e["total_tokens"] for e in valid],
        "calls": [e["llm_calls"] for e in valid],
        "costs": [e["cost"] for e in valid],
    }
    lat = sorted(out["latencies"])
    out["latency_mean"] = sum(lat) / len(lat)
    out["latency_median"] = lat[len(lat) // 2] if len(lat) % 2 else (lat[len(lat) // 2 - 1] + lat[len(lat) // 2]) / 2
    out["latency_p95"] = lat[min(len(lat) - 1, math.ceil(0.95 * len(lat)) - 1)]
    out["tokens_mean"] = sum(out["tokens"]) / len(out["tokens"])
    out["tokens_median"] = sorted(out["tokens"])[len(out["tokens"]) // 2]
    out["calls_mean"] = sum(out["calls"]) / len(out["calls"])
    out["cost_total"] = sum(out["costs"])
    out["cost_mean"] = out["cost_total"] / len(out["costs"])
    return out


import math

for sysname in SYSTEMS:
    entries = [L[t][sysname] for t in TASK_IDS]
    s = stats(entries, valid_only=False)
    print(f"\n--- {sysname} (full 30) ---")
    print(f"  FINAL_CLASSIFICATION counts: ", end="")
    from collections import Counter
    print(dict(Counter(e["FINAL_CLASSIFICATION"] for e in entries)))
    for k in ("n_valid", "final_resolved", "first_pass_resolved", "repair_eligible", "repair_recovered",
              "top1_evaluable", "top1_correct", "hallucinated", "hidden_tests_executed", "hidden_tests_passed",
              "gen_tests_created", "gen_tests_passed", "placeholder", "syntax_fail",
              "provider_contaminated", "infrastructure"):
        print(f"  {k}: {s[k]}")
    print(f"  repair_attempts_sum (valid): {s['repair_attempts_sum']}  -> mean over all valid: {s['repair_attempts_sum']/s['n_valid']:.2f}")
    print(f"  latency mean/median/p95: {s['latency_mean']:.1f} / {s['latency_median']:.1f} / {s['latency_p95']:.1f}")
    print(f"  tokens mean/median: {s['tokens_mean']:.0f} / {s['tokens_median']}")
    print(f"  llm_calls mean: {s['calls_mean']:.2f}")
    print(f"  cost total/mean: ${s['cost_total']:.4f} / ${s['cost_mean']:.5f}")
    # consistency checks
    n_class = Counter(e["FINAL_CLASSIFICATION"] for e in entries)
    assert sum(n_class.values()) == 30
    assert s["final_resolved"] == n_class.get("resolved", 0), "final_resolved must equal count of resolved classifications"
    assert s["provider_contaminated"] == n_class.get("provider_failure", 0)

# ------------------------------------------------- C. paired subset recompute
print()
print("=" * 78)
print("C. PAIRED-CLEAN SUBSET RECOMPUTED FROM LEDGER")
print("=" * 78)


def pstats(t):
    out = {}
    for sysname in SYSTEMS:
        e = L[t][sysname]
        out[sysname] = e
    return out


counts = {"both_solved": 0, "multi_only": 0, "baseline_only": 0, "neither_solved": 0}
multi_res = base_res = multi_fp = base_fp = 0
multi_elig = base_elig = multi_rec = base_rec = 0
for t in paired_clean:
    m, b = L[t]["multi_agent"], L[t]["baseline_b"]
    mr, br = m["final_resolved"], b["final_resolved"]
    multi_res += mr
    base_res += br
    multi_fp += m["first_pass_resolved"]
    base_fp += b["first_pass_resolved"]
    multi_elig += m["repair_eligible"]
    base_elig += b["repair_eligible"]
    multi_rec += m["repair_eligible"] and m["repair_recovered"]
    base_rec += b["repair_eligible"] and b["repair_recovered"]
    if mr and br:
        counts["both_solved"] += 1
    elif mr:
        counts["multi_only"] += 1
    elif br:
        counts["baseline_only"] += 1
    else:
        counts["neither_solved"] += 1
        if m["FINAL_CLASSIFICATION"] != "resolved" or b["FINAL_CLASSIFICATION"] != "resolved":
            print(f"  !! {t} in neither_solved but classification not genuine_agent_failure: "
                  f"m={m['FINAL_CLASSIFICATION']} b={b['FINAL_CLASSIFICATION']}")

n = len(paired_clean)
print(f"  n={n}")
print(f"  final resolved:        multi {multi_res}/{n} ({100*multi_res/n:.1f}%)  baseline {base_res}/{n} ({100*base_res/n:.1f}%)")
print(f"  first-pass resolved:   multi {multi_fp}/{n} ({100*multi_fp/n:.1f}%)  baseline {base_fp}/{n} ({100*base_fp/n:.1f}%)")
print(f"  repair eligible:       multi {multi_elig}  baseline {base_elig}")
print(f"  repair recovered:      multi {multi_rec} ({100*multi_rec/multi_elig if multi_elig else 0:.1f}%)  baseline {base_rec} ({100*base_rec/base_elig if base_elig else 0:.1f}%)")
print(f"  outcome counts: {counts}")
n10, n01 = counts["multi_only"], counts["baseline_only"]
print(f"  discordant: n10(multi-only)={n10}, n01(baseline-only)={n01}, total discordant={n10+n01}")
assert multi_res == counts["both_solved"] + counts["multi_only"], "paired multi resolved must equal both+multi_only"
assert base_res == counts["both_solved"] + counts["baseline_only"], "paired baseline resolved must equal both+baseline_only"

# exact two-sided binomial McNemar
from math import comb
k, nn = min(n10, n01), n10 + n01
p = sum(comb(nn, i) for i in range(0, k + 1)) * 2 / 2 ** nn
p = min(1.0, p)
print(f"  exact McNemar two-sided p = {p}  (report says 0.625)")

# cross-check paired_analysis.json
pa = paired_analysis
print("\n  cross-check vs paired_analysis.json:")
for name, got, want in [
    ("task_count", n, pa["task_count"]),
    ("tasks", paired_clean, pa["tasks"]),
    ("multi final_resolved", multi_res, pa["multi_agent"]["final_resolved"]),
    ("multi first_pass", multi_fp, pa["multi_agent"]["first_pass_resolved"]),
    ("multi repair_eligible", multi_elig, pa["multi_agent"]["repair_eligible"]),
    ("multi repair_recovered", multi_rec, pa["multi_agent"]["repair_recovered"]),
    ("base final_resolved", base_res, pa["baseline_b"]["final_resolved"]),
    ("base first_pass", base_fp, pa["baseline_b"]["first_pass_resolved"]),
    ("base repair_eligible", base_elig, pa["baseline_b"]["repair_eligible"]),
    ("base repair_recovered", base_rec, pa["baseline_b"]["repair_recovered"]),
    ("both_solved", counts["both_solved"], pa["outcome_counts"]["both_solved"]),
    ("multi_only", counts["multi_only"], pa["outcome_counts"]["multi_only"]),
    ("baseline_only", counts["baseline_only"], pa["outcome_counts"]["baseline_only"]),
    ("neither_solved", counts["neither_solved"], pa["outcome_counts"]["neither_solved"]),
    ("mcnemar p", p, pa["mcnemar_exact_p_two_sided"]),
]:
    ok = "OK " if got == want else "MISMATCH"
    print(f"    [{ok}] {name}: recomputed={got} json={want}")

# ------------------------------------------------- D. per-task ledger vs raw JSONs
print()
print("=" * 78)
print("D. LEDGER vs RAW JSON (all 60 runs)")
print("=" * 78)


def norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    return v


mismatches = 0
for t in TASK_IDS:
    for sysname in SYSTEMS:
        le = L[t][sysname]
        r = raw(t, sysname)
        if r is None:
            print(f"  !! {t}/{sysname}: raw JSON missing")
            mismatches += 1
            continue
        checks = [
            ("end_to_end_resolved", le["final_resolved"], bool(r.get("end_to_end_resolved"))),
            ("first_pass_resolved", le["first_pass_resolved"], bool((r.get("repair") or {}).get("first_pass_resolved_hidden"))),
            ("hidden_tests_executed", le["hidden_tests_executed"], bool((r.get("regression") or {}).get("hidden_tests_executed"))),
            ("hidden_tests_passed", le["hidden_tests_executed"] and le["hidden_tests_passed"],
             bool((r.get("regression") or {}).get("hidden_tests_executed")) and bool((r.get("regression") or {}).get("hidden_tests_passed"))),
            ("localization_top1", le["localization_top1"], (r.get("localization") or {}).get("top1_correct")),
            ("localization_evaluable", le["localization_evaluable"], (r.get("localization") or {}).get("valid")),
            ("hallucinated_file", le["hallucinated_file"], (r.get("localization") or {}).get("hallucinated_file")),
            ("patch_generated", le["patch_generated"], (r.get("patch") or {}).get("generated")),
            ("patch_placeholder", le["patch_placeholder"], (r.get("patch") or {}).get("is_placeholder")),
            ("gen_tests_created", le["generated_tests_created"], (r.get("tests") or {}).get("generated")),
            ("provider_contam", le["provider_failure"], bool(r.get("provider_contamination") or (r.get("provider") or {}).get("contamination_detected"))),
            ("latency", le["latency_seconds"], (r.get("execution") or {}).get("latency_seconds")),
            ("llm_calls", le["llm_calls"], (r.get("execution") or {}).get("llm_calls")),
            ("total_tokens", le["total_tokens"], (r.get("execution") or {}).get("total_tokens")),
            ("cost", le["cost"], (r.get("cost") or {}).get("estimated_usd")),
        ]
        for name, lv, rv in checks:
            if isinstance(lv, float) or isinstance(rv, float):
                eq = lv is not None and rv is not None and abs(float(lv) - float(rv)) < 1e-9
            else:
                eq = lv == rv
            if not eq:
                print(f"  !! {t}/{sysname} {name}: ledger={lv!r} raw={rv!r}")
                mismatches += 1
print(f"  ledger-vs-raw mismatches: {mismatches}")

# served model verification
served = set()
for t in TASK_IDS:
    for sysname in SYSTEMS:
        e = L[t][sysname]
        served.update(e.get("served_model") or [])
        r = raw(t, sysname)
        if r:
            served.update((r.get("provider") or {}).get("served_models") or [])
print(f"  distinct served models across 60 runs: {sorted(served)}")

# ------------------------------------------------- E. ledger vs analysis.json
print()
print("=" * 78)
print("E. LEDGER vs analysis.json (full-30 blocks)")
print("=" * 78)
for sysname in SYSTEMS:
    entries = [L[t][sysname] for t in TASK_IDS]
    s = stats(entries, valid_only=False)
    aj = analysis["raw_full_30"][sysname]
    pairs = [
        ("final_resolved", s["final_resolved"], aj["final_resolved"]),
        ("first_pass_resolved", s["first_pass_resolved"], aj["first_pass_resolved"]),
        ("repair_eligible", s["repair_eligible"], aj["repair_eligible"]),
        ("repair_recovered", s["repair_recovered"], aj["repair_recovered"]),
        ("top1_evaluable", s["top1_evaluable"], aj["top1_evaluable"]),
        ("top1_correct", s["top1_correct"], aj["top1_correct"]),
        ("hallucinated", s["hallucinated"], aj["hallucinated"]),
        ("hidden_tests_executed", s["hidden_tests_executed"], aj["hidden_tests_executed"]),
        ("hidden_tests_passed", s["hidden_tests_passed"], aj["hidden_tests_passed"]),
        ("generated_tests_created", s["gen_tests_created"], aj["generated_tests_created"]),
        ("generated_tests_passed", s["gen_tests_passed"], aj["generated_tests_passed"]),
        ("patch_placeholder", s["placeholder"], aj["patch_placeholder"]),
        ("patch_syntax_fail", s["syntax_fail"], aj["patch_syntax_fail"]),
        ("provider_contaminated", s["provider_contaminated"], aj["provider_contaminated"]),
        ("infrastructure_failures", s["infrastructure"], aj["infrastructure_failures"]),
    ]
    for name, got, want in pairs:
        ok = "OK " if got == want else "MISMATCH"
        print(f"  [{ok}] {sysname}.{name}: ledger={got} analysis={want}")
    for name, got, want, tol in [
        ("latency_mean_s", s["latency_mean"], aj["latency_mean_s"], 0.15),
        ("latency_median_s", s["latency_median"], aj["latency_median_s"], 0.15),
        ("latency_p95_s", s["latency_p95"], aj["latency_p95_s"], 0.15),
        ("tokens_mean", s["tokens_mean"], aj["tokens_mean"], 1.0),
        ("tokens_median", s["tokens_median"], aj["tokens_median"], 1.0),
        ("llm_calls_mean", s["calls_mean"], aj["llm_calls_mean"], 0.01),
        ("cost_total_usd", s["cost_total"], aj["cost_total_usd"], 0.0002),
        ("cost_mean_usd", s["cost_mean"], aj["cost_mean_usd"], 0.00002),
    ]:
        ok = "OK " if abs(got - want) <= tol else "MISMATCH"
        print(f"  [{ok}] {sysname}.{name}: ledger={got:.4f} analysis={want} (tol {tol})")

print()
print("AUDIT COMPLETE — no files were modified.")
