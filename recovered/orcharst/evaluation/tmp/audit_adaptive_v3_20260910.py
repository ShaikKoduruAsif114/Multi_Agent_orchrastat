#!/usr/bin/env python3
"""READ-ONLY forensic audit of nara_laguna_adaptive_v3_final_20260910.

Recomputes every claimed metric from the 60 raw JSONs + manifest.
Prints per-task ground truth, outcome tables under every candidate inclusion
rule, McNemar variants, efficiency stats under candidate denominators, and
aggregates.json cross-checks. Reads only; writes nothing.
"""
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "evaluation" / "results" / "nara_laguna_adaptive_v3_final_20260910"
MAN = ROOT / "evaluation" / "benchmark_input_manifest_sha256_20260909.txt"
TASK_IDS = [f"task_{i:03d}" for i in range(1, 31)]
SYSTEMS = ("adaptive_multi_agent", "baseline_b")


def raw(t, s):
    with open(EXP / "raw" / f"{t}_{s}.json", encoding="utf-8") as f:
        return json.load(f)


R = {t: {s: raw(t, s) for s in SYSTEMS} for t in TASK_IDS}
agg = json.load(open(EXP / "aggregates" / "aggregates.json", encoding="utf-8"))


def truth(t, s):
    r = R[t][s]
    ex = r.get("execution") or {}
    rep = r.get("repair") or {}
    ad = r.get("adaptive") or {}
    loc = r.get("localization") or {}
    reg = r.get("regression") or {}
    return {
        "status": ex.get("status"),
        "failcat": ex.get("failure_category"),
        "errmsg": (ex.get("error_message") or "")[:90],
        "e2e": bool(r.get("end_to_end_resolved")),
        "hidden_exec": bool(reg.get("hidden_tests_executed")),
        "hidden_pass": bool(reg.get("hidden_tests_passed")),
        "hidden_total": reg.get("hidden_tests_total"),
        "hidden_passcount": reg.get("hidden_tests_passed_count"),
        "fp_repairblock": rep.get("first_pass_resolved_hidden"),
        "fp_adaptive": ad.get("first_pass_resolved"),
        "elig_repairblock": rep.get("repair_eligible"),
        "elig_adaptive": ad.get("repair_eligible"),
        "att_repairblock": rep.get("repair_attempt_count"),
        "att_adaptive": ad.get("repair_attempts"),
        "rec_repairblock": rep.get("repair_recovered"),
        "rec_adaptive": ad.get("repair_recovered"),
        "retry_budget": rep.get("retry_budget"),
        "attempts_rep_attempts": rep.get("attempts"),
        "loc_pred": loc.get("predicted_file"),
        "loc_gold": loc.get("gold_file"),
        "top1": loc.get("top1_correct"),
        "halluc": loc.get("hallucinated_file"),
        "loc_valid": loc.get("valid"),
        "calls": ex.get("llm_calls"),
        "tokens": ex.get("total_tokens"),
        "lat": ex.get("latency_seconds"),
        "cost": (r.get("cost") or {}).get("estimated_usd"),
        "contam": bool(r.get("provider_contamination") or (r.get("provider") or {}).get("contamination_detected")),
        "served": sorted(set((r.get("provider") or {}).get("served_models") or [])),
        "diff": ad.get("difficulty_score"),
        "dclass": ad.get("difficulty_class"),
        "ipath": ad.get("initial_path"),
        "fpath": ad.get("final_path"),
        "esc": ad.get("escalated"),
    }


T = {t: {s: truth(t, s) for s in SYSTEMS} for t in TASK_IDS}

print("=" * 100)
print("A. PER-TASK GROUND TRUTH (adaptive)")
print("=" * 100)
hdr = f"{'task':<9}{'status':<10}{'failcat':<24}{'e2e':<5}{'fpR':<6}{'fpA':<6}{'hid':<5}{'eligRB':<7}{'eligA':<6}{'attA':<5}{'recA':<5}{'top1':<6}{'hall':<5}{'calls':<6}{'tok':<6}{'lat':<7}{'cost':<9}{'path':<8}{'esc':<5}{'diff':<5}{'rb':<3}"
print(hdr)
for t in TASK_IDS:
    d = T[t]["adaptive_multi_agent"]
    print(f"{t:<9}{str(d['status']):<10}{str(d['failcat']):<24}{str(d['e2e'])[:1]:<5}"
          f"{str(d['fp_repairblock'])[:1]:<6}{str(d['fp_adaptive'])[:1]:<6}{str(d['hidden_pass'])[:1]:<5}"
          f"{str(d['elig_repairblock'])[:1]:<7}{str(d['elig_adaptive'])[:1]:<6}{str(d['att_adaptive']):<5}{str(d['rec_adaptive'])[:1]:<5}"
          f"{str(d['top1'])[:1]:<6}{str(d['halluc'])[:1]:<5}{str(d['calls']):<6}{str(d['tokens']):<6}{str(d['lat']):<7}{str(d['cost']):<9}"
          f"{str(d['ipath']):<8}{str(d['esc'])[:1]:<5}{str(d['diff']):<5}{str(d['retry_budget']):<3}")

print()
print("=" * 100)
print("B. PER-TASK GROUND TRUTH (baseline_b)")
print("=" * 100)
print(f"{'task':<9}{'status':<10}{'failcat':<24}{'e2e':<5}{'fpR':<6}{'hid':<5}{'elig':<6}{'att':<4}{'rec':<5}{'top1':<6}{'hall':<5}{'calls':<6}{'tok':<6}{'lat':<7}{'cost':<9}{'rb':<3}{'contam':<7}{'served'}")
for t in TASK_IDS:
    d = T[t]["baseline_b"]
    print(f"{t:<9}{str(d['status']):<10}{str(d['failcat']):<24}{str(d['e2e'])[:1]:<5}{str(d['fp_repairblock'])[:1]:<6}"
          f"{str(d['hidden_pass'])[:1]:<5}{str(d['elig_repairblock'])[:1]:<6}{str(d['att_repairblock']):<4}{str(d['rec_repairblock'])[:1]:<5}"
          f"{str(d['top1'])[:1]:<6}{str(d['halluc'])[:1]:<5}{str(d['calls']):<6}{str(d['tokens']):<6}{str(d['lat']):<7}{str(d['cost']):<9}"
          f"{str(d['retry_budget']):<3}{str(d['contam'])[:1]:<7}{d['served']}")

print()
print("=" * 100)
print("C. HEADLINE RECOMPUTATION")
print("=" * 100)
for s in SYSTEMS:
    ds = [T[t][s] for t in TASK_IDS]
    e2e = sum(d["e2e"] for d in ds)
    fp_rb = sum(1 for d in ds if d["fp_repairblock"] is True)
    fp_ad = sum(1 for d in ds if d["fp_adaptive"] is True)
    hid = sum(d["hidden_pass"] for d in ds)
    err = [t for t in TASK_IDS if T[t][s]["status"] == "error" or T[t][s]["failcat"] == "benchmark_runner_error"]
    print(f"\n{s}:")
    print(f"  e2e resolved: {e2e}/30")
    print(f"  first-pass via repair.first_pass_resolved_hidden: {fp_rb}/30")
    print(f"  first-pass via adaptive.first_pass_resolved: {fp_ad}/30  (adaptive block only)")
    print(f"  hidden passed: {hid}/30")
    print(f"  runner-error tasks: {err}")
    fails = [t for t in TASK_IDS if not T[t][s]["e2e"]]
    print(f"  all non-resolved: {fails} categories: {[T[t][s]['failcat'] for t in fails]}")

print()
print("=" * 100)
print("D. PAIRED OUTCOME TABLES (all candidate inclusion rules)")
print("=" * 100)


def outcomes(include):
    cells = {"both": [], "adaptive_only": [], "baseline_only": [], "neither": []}
    for t in TASK_IDS:
        if not include(t):
            continue
        a, b = T[t]["adaptive_multi_agent"]["e2e"], T[t]["baseline_b"]["e2e"]
        if a and b:
            cells["both"].append(t)
        elif a:
            cells["adaptive_only"].append(t)
        elif b:
            cells["baseline_only"].append(t)
        else:
            cells["neither"].append(t)
    return cells


def mcnemar(n10, n01):
    n = n10 + n01
    if n == 0:
        return 1.0, 1.0
    k = min(n10, n01)
    two = min(1.0, 2 * sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n)
    one = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return one, two


rules = {
    "ALL 30 (no exclusions)": lambda t: True,
    "both systems ran (status!=error)": lambda t: T[t]["adaptive_multi_agent"]["status"] != "error" and T[t]["baseline_b"]["status"] != "error",
    "neither system infra-failed": lambda t: T[t]["adaptive_multi_agent"]["failcat"] != "benchmark_runner_error" and T[t]["baseline_b"]["failcat"] != "benchmark_runner_error",
    "both e2e-or-genuine (hidden tests ran both sides)": lambda t: T[t]["adaptive_multi_agent"]["hidden_exec"] and T[t]["baseline_b"]["hidden_exec"],
}
for name, rule in rules.items():
    cells = outcomes(rule)
    n = sum(len(v) for v in cells.values())
    n10, n01 = len(cells["adaptive_only"]), len(cells["baseline_only"])
    one, two = mcnemar(n10, n01)
    print(f"\n--- rule: {name}  (N={n}) ---")
    for k, v in cells.items():
        print(f"  {k:<14} {len(v):2d}  {v}")
    print(f"  discordant: adaptive-only {n10} vs baseline-only {n01}; exact one-sided p={one:.4f}, two-sided p={two:.4f}")

print()
print("=" * 100)
print("E. REPORT'S CLAIMED TABLE vs REALITY")
print("=" * 100)
claimed_disc = ["task_002", "task_003", "task_004", "task_006", "task_017", "task_018", "task_022", "task_023", "task_024"]
claimed_base = ["task_020", "task_027", "task_030"]
print("claimed adaptive-only wins, actual cells:")
for t in claimed_disc:
    a, b = T[t]["adaptive_multi_agent"]["e2e"], T[t]["baseline_b"]["e2e"]
    cell = "both" if a and b else "adaptive_only" if a else "baseline_only" if b else "neither"
    print(f"  {t}: adaptive e2e={a}, baseline e2e={b} -> {cell}  (adaptive failcat={T[t]['adaptive_multi_agent']['failcat']}, baseline failcat={T[t]['baseline_b']['failcat']})")
print("claimed baseline-only wins, actual cells:")
for t in claimed_base:
    a, b = T[t]["adaptive_multi_agent"]["e2e"], T[t]["baseline_b"]["e2e"]
    cell = "both" if a and b else "adaptive_only" if a else "baseline_only" if b else "neither"
    print(f"  {t}: adaptive e2e={a}, baseline e2e={b} -> {cell}  (adaptive failcat={T[t]['adaptive_multi_agent']['failcat']}, baseline failcat={T[t]['baseline_b']['failcat']})")

print()
print("=" * 100)
print("F. EFFICIENCY UNDER CANDIDATE DENOMINATORS")
print("=" * 100)


def eff(s, tasks, field):
    vals = [T[t][s][field] for t in tasks if isinstance(T[t][s][field], (int, float))]
    return vals


for s in SYSTEMS:
    all30 = TASK_IDS
    valid = [t for t in TASK_IDS if T[t][s]["status"] != "error"]
    nonzero = [t for t in TASK_IDS if (T[t][s]["calls"] or 0) > 0]
    print(f"\n{s}:")
    for name, ts in (("all 30", all30), ("status!=error", valid), ("calls>0", nonzero)):
        calls = eff(s, ts, "calls")
        tok = eff(s, ts, "tokens")
        lat = eff(s, ts, "lat")
        cost = eff(s, ts, "cost")
        if not calls:
            continue
        print(f"  {name:<15} n={len(ts):2d} calls_mean={statistics.mean(calls):.3f} tok_total={sum(tok):6d} tok_mean={statistics.mean(tok):7.1f} "
              f"lat_mean={statistics.mean(lat):6.2f} lat_med={statistics.median(lat):6.2f} lat_p90={sorted(lat)[math.ceil(0.9*len(lat))-1]:6.2f} "
              f"cost_total=${sum(cost):.4f} cost_mean=${statistics.mean(cost):.5f}")

print()
print("=" * 100)
print("G. LOCALIZATION / HALLUCINATION")
print("=" * 100)
for s in SYSTEMS:
    ds = [(t, T[t][s]) for t in TASK_IDS]
    evaluable = [t for t, d in ds if d["top1"] is not None]
    loc_valid = [t for t, d in ds if d["loc_valid"] is True]
    correct = [t for t in evaluable if T[t][s]["top1"] is True]
    hall = [t for t, d in ds if d["halluc"]]
    wrong = [t for t in evaluable if T[t][s]["top1"] is False]
    print(f"\n{s}: top1 not-null (evaluable) n={len(evaluable)} {evaluable}")
    print(f"  loc.valid=True: {len(loc_valid)}; top1 correct: {len(correct)}/{len(evaluable)}; top1 false: {wrong}; hallucinated flag: {hall}")
    for t in wrong + hall:
        d = T[t][s]
        print(f"    {t}: predicted={d['loc_pred']} gold={d['loc_gold']} top1={d['top1']} halluc={d['halluc']} loc_valid={d['loc_valid']} status={d['status']}")

print()
print("=" * 100)
print("H. ADAPTIVE PATH DISTRIBUTION / ESCALATIONS / REPAIR")
print("=" * 100)
from collections import Counter
ip = Counter(T[t]["adaptive_multi_agent"]["ipath"] for t in TASK_IDS)
fc = Counter(T[t]["adaptive_multi_agent"]["dclass"] for t in TASK_IDS)
esc = [t for t in TASK_IDS if T[t]["adaptive_multi_agent"]["esc"]]
print(f"initial_path: {dict(ip)}   difficulty_class: {dict(fc)}   escalated tasks: {esc}")
print("final_path != initial_path:", [t for t in TASK_IDS if T[t]["adaptive_multi_agent"]["fpath"] != T[t]["adaptive_multi_agent"]["ipath"]])
diffs = [T[t]["adaptive_multi_agent"]["diff"] for t in TASK_IDS if T[t]["adaptive_multi_agent"]["diff"] is not None]
print(f"difficulty scores: n={len(diffs)} min={min(diffs)} max={max(diffs)} mean={statistics.mean(diffs):.2f} median={statistics.median(diffs):.2f}")
print("adaptive repair fields (task, eligA, attA, recA, fpA, fpRB, e2e):")
for t in TASK_IDS:
    d = T[t]["adaptive_multi_agent"]
    if d["elig_adaptive"] or d["att_adaptive"] or d["rec_adaptive"] or d["fp_adaptive"] is False:
        print(f"  {t}: elig={d['elig_adaptive']} att={d['att_adaptive']} rec={d['rec_adaptive']} fpA={d['fp_adaptive']} fpRB={d['fp_repairblock']} e2e={d['e2e']} stage_reason={R[t]['adaptive_multi_agent']['adaptive'].get('path_reason','')[:60]}")
print("baseline repair fields (task, elig, attRB, rec, fpRB, e2e):")
for t in TASK_IDS:
    d = T[t]["baseline_b"]
    if d["elig_repairblock"] or d["rec_repairblock"] or d["fp_repairblock"] is False:
        print(f"  {t}: elig={d['elig_repairblock']} att={d['att_repairblock']} rec={d['rec_repairblock']} fpRB={d['fp_repairblock']} e2e={d['e2e']}")

print()
print("=" * 100)
print("I. CONTAMINATION / RETRY BUDGETS / SERVED MODELS")
print("=" * 100)
contam = [(t, s) for t in TASK_IDS for s in SYSTEMS if T[t][s]["contam"]]
print(f"contaminated runs: {contam}")
rb_a = Counter(T[t]["adaptive_multi_agent"]["retry_budget"] for t in TASK_IDS)
rb_b = Counter(T[t]["baseline_b"]["retry_budget"] for t in TASK_IDS)
print(f"adaptive retry_budget values: {dict(rb_a)}   baseline retry_budget values: {dict(rb_b)}")
served = set()
for t in TASK_IDS:
    for s in SYSTEMS:
        served.update(T[t][s]["served"])
print(f"distinct served models: {served}")

print()
print("=" * 100)
print("J. AGGREGATES.JSON CROSS-CHECK")
print("=" * 100)
for s, key in (("adaptive_multi_agent", "adaptive_multi_agent"), ("baseline_b", "baseline_b")):
    a = agg["systems"][key]
    ds = [T[t][s] for t in TASK_IDS]
    checks = [
        ("N", a["N"], 30),
        ("e2e_resolved", a["e2e_resolved"], sum(d["e2e"] for d in ds)),
        ("first_pass_resolved", a["first_pass_resolved"], sum(1 for d in ds if d["fp_repairblock"] is True)),
        ("hidden_tests_passed", a["hidden_tests_passed"], sum(d["hidden_pass"] for d in ds)),
        ("localized", a["localized"], sum(1 for d in ds if d["top1"] is True)),
        ("loc_eligible", a["loc_eligible"], sum(1 for d in ds if d["top1"] is not None)),
        ("hallucinated_file", a["hallucinated_file"], sum(1 for d in ds if d["halluc"])),
        ("llm_calls_mean(N=llm>0)", round(a["llm_calls_mean"], 3), round(statistics.mean([d["calls"] for d in ds if (d["calls"] or 0) > 0]), 3)),
        ("llm_calls_N", a["llm_calls_N"], sum(1 for d in ds if (d["calls"] or 0) > 0)),
        ("latency_mean_s", a["latency_mean_s"], round(statistics.mean([d["lat"] for d in ds if d["status"] != "error"]), 2)),
    ]
    for name, got, want in checks:
        ok = "OK " if got == want else "DIFF"
        print(f"  [{ok}] {s}.{name}: aggregates={got} recomputed={want}")

print()
print("=" * 100)
print("K. MANIFEST INTEGRITY")
print("=" * 100)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


ok = bad = 0
badlist = []
for line in MAN.read_text(encoding="utf-8-sig").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    path, _, expected = line.partition("|")
    p = ROOT / path
    if not p.exists():
        bad += 1
        badlist.append((path, "MISSING"))
    elif sha(p) == expected:
        ok += 1
    else:
        bad += 1
        badlist.append((path, "MISMATCH"))
print(f"manifest: {ok} OK, {bad} problems {badlist[:5]}")

print("\nAUDIT COMPLETE (read-only)")
