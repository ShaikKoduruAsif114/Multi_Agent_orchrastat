#!/usr/bin/env python3
"""Targeted probes: task_020 contamination, escalation details, token medians/p90,
max calls, error messages, and stale-number origin in earlier experiment dirs."""
import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "evaluation" / "results" / "nara_laguna_adaptive_v3_final_20260910"
TASK_IDS = [f"task_{i:03d}" for i in range(1, 31)]
SYSTEMS = ("adaptive_multi_agent", "baseline_b")


def raw(t, s):
    return json.load(open(EXP / "raw" / f"{t}_{s}.json", encoding="utf-8"))


print("== task_020 adaptive contamination block ==")
r = raw("task_020", "adaptive_multi_agent")
print(json.dumps(r.get("provider"), indent=1)[:800])
print("provider_contamination top-level:", r.get("provider_contamination"))
ex = r["execution"]
print("status:", ex.get("status"), "| failure_category:", ex.get("failure_category"))
print("error_message:", (ex.get("error_message") or "")[:300])

print("\n== adaptive error runs (008, 010) ==")
for t in ("task_008", "task_010"):
    r = raw(t, "adaptive_multi_agent")
    ex = r["execution"]
    print(f"{t}: status={ex.get('status')} failcat={ex.get('failure_category')} lat={ex.get('latency_seconds')} err={(ex.get('error_message') or '')[:200]}")

print("\n== escalation details (adaptive) ==")
for t in TASK_IDS:
    ad = raw(t, "adaptive_multi_agent").get("adaptive") or {}
    if ad.get("escalated"):
        print(f"{t}: initial={ad.get('initial_path')} final={ad.get('final_path')} reason={ad.get('escalation_reason')} "
              f"e2e={raw(t,'adaptive_multi_agent').get('end_to_end_resolved')}")

print("\n== tokens/calls distribution ==")
for s in SYSTEMS:
    tok = [raw(t, s)["execution"].get("total_tokens") for t in TASK_IDS]
    calls = [raw(t, s)["execution"].get("llm_calls") for t in TASK_IDS]
    tokv = sorted(x for x in tok if isinstance(x, (int, float)))
    cv = sorted(x for x in calls if isinstance(x, (int, float)))
    n30tok = sum(tokv) / 30
    print(f"{s}: n_runs_with_tokens={len(tokv)} total={sum(tokv)} mean_over_30={n30tok:.1f} mean_over_valid={statistics.mean(tokv):.1f} "
          f"median={statistics.median(tokv)} p90_nearest={tokv[min(len(tokv)-1, int(0.9*len(tokv)))]}")
    print(f"   calls: n={len(cv)} max={max(cv)} mean_over_valid={statistics.mean(cv):.3f} mean_over_30={sum(cv)/30:.3f} p90={cv[min(len(cv)-1, int(0.9*len(cv)))]}")
    print(f"   tokens sorted: {tokv}")

print("\n== stale-number origin check: other adaptive experiment aggregates ==")
for d in sorted((ROOT / "evaluation" / "results").glob("*adaptive*")):
    agg = d / "aggregates" / "aggregates.json"
    if agg.exists():
        a = json.load(open(agg, encoding="utf-8"))
        for s in ("adaptive_multi_agent", "baseline_b"):
            if s in a.get("systems", {}):
                st = a["systems"][s]
                print(f"{d.name} [{s}]: N={st.get('N')} e2e={st.get('e2e_resolved')} tok_mean={st.get('tokens_mean') if 'tokens_mean' in st else 'n/a'} "
                      f"calls_mean={st.get('llm_calls_mean')} lat_mean={st.get('latency_mean_s')}")
    else:
        print(f"{d.name}: (no aggregates/aggregates.json; files: {[p.name for p in d.glob('*.json')][:5]})")

print("\n== baseline retries_total source (aggregates says 16) ==")
tot = 0
for t in TASK_IDS:
    r = raw(t, "baseline_b")
    rep = r.get("repair") or {}
    n = len(rep.get("llm_calls") or [])
    att = rep.get("attempts")
    if n or (att and att > 1):
        print(f"  {t}: repair.llm_calls={n} attempts={att} first_attempt_success={rep.get('first_attempt_success')}")
    tot += n
print("sum of repair.llm_calls over 30:", tot)

print("\n== hidden_tests_total sanity (adaptive) ==")
for t in TASK_IDS:
    reg = raw(t, "adaptive_multi_agent").get("regression") or {}
    if reg.get("hidden_tests_executed") and not reg.get("hidden_tests_total"):
        print(f"  {t}: executed=True but total={reg.get('hidden_tests_total')} passcount={reg.get('hidden_tests_passed_count')}")
