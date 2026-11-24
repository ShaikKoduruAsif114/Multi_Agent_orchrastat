#!/usr/bin/env python3
"""Build canonical task_ledger.json for nara_laguna_adaptive_v3_final_20260910.

Reuses evaluation/build_ledger.py (provider_signature, build_entry, McNemar)
as the classification core. Two documented extensions:
  A) provider failure also detected from raw `provider.contamination` /
     `provider_contamination` records (task_020's 502 is only recorded there);
  B) for adaptive_multi_agent, repair/first-pass fields are taken from the
     dedicated `adaptive` controller block (build_ledger's baseline-style
     else-branch cannot read it).
Writes ONLY evaluation/results/<exp>/task_ledger.json. Reads everything else.
"""
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evaluation"))
import build_ledger as bl  # repo classification logic

EXP_ID = "nara_laguna_adaptive_v3_final_20260910"
EXP = ROOT / "evaluation" / "results" / EXP_ID
TASK_IDS = [f"task_{i:03d}" for i in range(1, 31)]
SYSTEMS = ("adaptive_multi_agent", "baseline_b")
LEDGER_OUT = EXP / "task_ledger.json"


def raw(t, s):
    return json.load(open(EXP / "raw" / f"{t}_{s}.json", encoding="utf-8"))


def sanitized(d):
    """Copy of raw dict safe for build_entry: baseline error runs record
    repair.attempts=null (no repair loop ran); build_ledger casts int() on it.
    Default null -> 1 (= no repair beyond the first attempt). No other field touched."""
    d = json.loads(json.dumps(d))
    rep = d.get("repair") or {}
    if rep.get("attempts") is None:
        rep["attempts"] = 1
        d["repair"] = rep
    return d


VALID_CLASSES = ("resolved", "genuine_agent_failure")


def contamination_records(d):
    """Extension A: explicit contamination metadata in the raw provider block."""
    prov = d.get("provider") or {}
    recs = []
    if prov.get("contamination_detected") or d.get("provider_contamination"):
        for c in prov.get("contamination") or []:
            sig = bl.provider_signature(c.get("error", ""))
            recs.append({
                "stage": c.get("stage"),
                "error": (c.get("error") or "")[:300],
                "failure_category": sig[1] or c.get("failure_category"),
                "http_status": sig[2] or None,
                "source": "provider.contamination record",
            })
    return recs


entries = []
for t in TASK_IDS:
    for s in SYSTEMS:
        d = raw(t, s)
        e = bl.build_entry(sanitized(d))  # canonical core (provider scan incl. runner error_message)

        # Extension A: honor explicit contamination records
        crecs = contamination_records(d)
        if crecs:
            e["provider_failure"] = True
            cats = set(e["provider_error_type"] or []) | {c["failure_category"] for c in crecs}
            stats_ = set(e["provider_http_status"] or []) | {c["http_status"] for c in crecs if c["http_status"]}
            e["provider_error_type"] = sorted(cats)
            e["provider_http_status"] = sorted(stats_)
            msgs = list(e["provider_error_message"] or [])
            e["provider_error_message"] = msgs + crecs

        # re-derive FINAL_CLASSIFICATION with extension A applied
        if e["provider_failure"]:
            e["FINAL_CLASSIFICATION"] = "provider_failure"
        e["provider_contamination_source"] = (
            "provider.contamination+execution.error_message" if crecs and (e["provider_error_message"] or [{}])[0].get("stage") != "runner"
            else "execution.error_message/llm_call_records" if e["provider_failure"]
            else None
        )

        # Extension B: adaptive repair accounting from the controller block
        ad = d.get("adaptive") or {}
        if s == "adaptive_multi_agent":
            rep = d.get("repair") or {}
            e["first_pass_resolved"] = rep.get("first_pass_resolved_hidden")
            e["first_pass_failure_category"] = None if e["first_pass_resolved"] else "first_patch_failed_hidden_tests"
            e["repair_eligible"] = bool(ad.get("repair_eligible"))
            e["repair_attempts"] = int(ad.get("repair_attempts") or 0)
            e["repair_recovered"] = bool(ad.get("repair_recovered"))
            e["adaptive_first_pass_discrepancy"] = (
                ad.get("first_pass_resolved") is not True and e["first_pass_resolved"] is True
            )
            e["adaptive_block_first_pass_resolved"] = ad.get("first_pass_resolved")
            e["retry_budget"] = rep.get("retry_budget")
            for k_src, k_dst in (("difficulty_score", "difficulty_score"),
                                 ("difficulty_class", "difficulty_class"),
                                 ("initial_path", "initial_path"),
                                 ("final_path", "final_path"),
                                 ("escalated", "escalated"),
                                 ("escalation_reason", "escalation_reason"),
                                 ("path_reason", "path_reason")):
                e[k_dst] = ad.get(k_src)
        else:
            e["retry_budget"] = (d.get("repair") or {}).get("retry_budget")
            e["escalated"] = None

        # re-derive first_pass_status per build_ledger conventions
        if e["FINAL_CLASSIFICATION"] == "provider_failure":
            e["first_pass_status"] = "PROVIDER_FAILURE"
        elif e["FINAL_CLASSIFICATION"] == "infrastructure_failure":
            e["first_pass_status"] = "INFRASTRUCTURE_FAILURE"
        else:
            fp = e["first_pass_resolved"]
            e["first_pass_status"] = ("FIRST_PASS_SUCCESS" if fp is True
                                      else "FIRST_PASS_FAILURE_REPAIR_RECOVERED" if e["repair_recovered"]
                                      else "FIRST_PASS_FAILURE_REPAIR_FAILED" if e["repair_eligible"]
                                      else "FIRST_PASS_FAILURE_NO_BUDGETED_REPAIR" if fp is False
                                      else "UNKNOWN")

        e["paired_clean_included"] = None  # filled after all entries exist
        e["exclusion_reason"] = None
        entries.append(e)

by_ts = {(e["task_id"], e["system"]): e for e in entries}

# ---- paired inclusion tiers -------------------------------------------------
# Tier 1 (PRIMARY, "usable outcome"): exclude a task iff EITHER system's run
#   died to a fatal provider error (execution.status=error with provider
#   signature) -> no usable pipeline output to compare. Runs that COMPLETED
#   despite a recorded mid-run provider error (adaptive task_020: research
#   502, run continued and failed hidden tests) are KEPT as observed
#   outcomes, with their contamination documented separately.
# Tier 2 (STRICT sensitivity): additionally exclude any task where either
#   system recorded a provider error at all (drops adaptive task_020 too).
fatal_tasks = sorted({t for t in TASK_IDS for s in SYSTEMS
                      if by_ts[(t, s)]["final_status"] == "error" and by_ts[(t, s)]["provider_failure"]})
strict_excluded = sorted(set(fatal_tasks) | {t for t in TASK_IDS for s in SYSTEMS
                                             if by_ts[(t, s)]["FINAL_CLASSIFICATION"] == "provider_failure"})

paired_tasks = [t for t in TASK_IDS if t not in fatal_tasks]          # PRIMARY N=22
strict_tasks = [t for t in TASK_IDS if t not in strict_excluded]      # sensitivity N=21
excluded_tasks = fatal_tasks

for t in TASK_IDS:
    for s in SYSTEMS:
        e = by_ts[(t, s)]
        e["paired_primary_included"] = t in paired_tasks
        e["paired_strict_included"] = t in strict_tasks
        if t in fatal_tasks:
            side = s if by_ts[(t, s)]["final_status"] == "error" else "other arm"
            e["exclusion_reason"] = (
                f"FATAL provider error killed the {side} run (execution.status=error): "
                f"{by_ts[(t, s)]['provider_error_type']} http={by_ts[(t, s)]['provider_http_status']}"
                if by_ts[(t, s)]["final_status"] == "error" else "paired arm fatally provider-failed"
            )
        else:
            e["exclusion_reason"] = None

# ---- paired outcomes --------------------------------------------------------
def cell(t):
    a = by_ts[(t, "adaptive_multi_agent")]["final_resolved"]
    b = by_ts[(t, "baseline_b")]["final_resolved"]
    return "both" if a and b else "adaptive_only" if a else "baseline_only" if b else "neither"


cells = {k: [t for t in paired_tasks if cell(t) == k] for k in ("both", "adaptive_only", "baseline_only", "neither")}
n10, n01 = len(cells["adaptive_only"]), len(cells["baseline_only"])
p_clean = bl.mcnemar_exact(n10, n01)

strict_cells = {k: [t for t in strict_tasks if cell(t) == k] for k in ("both", "adaptive_only", "baseline_only", "neither")}
s10, s01 = len(strict_cells["adaptive_only"]), len(strict_cells["baseline_only"])
p_strict = bl.mcnemar_exact(s10, s01)

all30 = {k: [] for k in ("both", "adaptive_only", "baseline_only", "neither")}
for t in TASK_IDS:
    all30[cell(t)].append(t)
a30_10, a30_01 = len(all30["adaptive_only"]), len(all30["baseline_only"])
p_all30 = bl.mcnemar_exact(a30_10, a30_01)

# ---- efficiency under labeled denominators ---------------------------------
def eff(s, tasks):
    vals = {k: [by_ts[(t, s)][k] for t in tasks if isinstance(by_ts[(t, s)][k], (int, float))]
            for k in ("llm_calls", "total_tokens", "latency_seconds", "cost")}
    out = {"n_tasks_in_denominator": len(tasks)}
    for k, short, nd in (("llm_calls", "llm_calls", 3), ("total_tokens", "tokens", 1),
                         ("latency_seconds", "latency", 2), ("cost", "cost", 6)):
        v = vals[k]
        out[f"{short}_n"] = len(v)
        if not v:
            out[f"{short}_mean"] = None
            continue
        out[f"{short}_mean"] = round(statistics.mean(v), nd)
    tok, lat, cost = vals["total_tokens"], sorted(vals["latency_seconds"]), vals["cost"]
    if tok:
        out["tokens_total"] = sum(tok)
        out["tokens_median"] = statistics.median(tok)
    if lat:
        out["latency_median_s"] = round(statistics.median(lat), 2)
        out["latency_p90_nearest_s"] = round(lat[min(len(lat) - 1, int(math.ceil(0.9 * len(lat))) - 1)], 2)
    if cost:
        out["cost_total_usd"] = round(sum(cost), 6)
    if vals["llm_calls"]:
        out["llm_calls_median"] = statistics.median(vals["llm_calls"])
        out["llm_calls_max"] = max(vals["llm_calls"])
    return out


eff_block = {}
for s in SYSTEMS:
    rwo = [t for t in TASK_IDS if (by_ts[(t, s)]["llm_calls"] or 0) > 0]
    valid = [t for t in TASK_IDS if by_ts[(t, s)]["FINAL_CLASSIFICATION"] in VALID_CLASSES]
    eff_block[s] = {
        "all_30": eff(s, TASK_IDS),
        "runs_with_output": eff(s, rwo),
        "runs_with_output_tasks": rwo,
        "valid_only": eff(s, valid),
        "primary_paired_22": eff(s, paired_tasks),
        "strict_paired_21": eff(s, strict_tasks),
    }
    for tier, tset in (("primary_paired_22", paired_tasks), ("strict_paired_21", strict_tasks)):
        rc = [by_ts[(t, s)]["cost"] for t in tset if by_ts[(t, s)]["final_resolved"]]
        eff_block[s][f"{tier}_cost_per_resolved_usd"] = round(sum(rc) / max(1, len(rc)), 6)

# ---- per-system full-30 summary --------------------------------------------
per_system = {}
for s in SYSTEMS:
    es = [by_ts[(t, s)] for t in TASK_IDS]
    val = [e for e in es if e["FINAL_CLASSIFICATION"] in VALID_CLASSES]
    per_system[s] = {
        "n": 30,
        "final_resolved": sum(e["final_resolved"] for e in es),
        "final_resolved_valid_only": sum(e["final_resolved"] for e in val),
        "valid_n": len(val),
        "first_pass_resolved": sum(1 for e in es if e["first_pass_resolved"] is True),
        "repair_eligible": sum(1 for e in val if e["repair_eligible"]),
        "repair_recovered": sum(1 for e in val if e["repair_eligible"] and e["repair_recovered"]),
        "top1_evaluable": sum(1 for e in val if e["localization_evaluable"]),
        "top1_correct": sum(1 for e in val if e["localization_evaluable"] and e["localization_top1"] is True),
        "hallucinated_flag": sum(1 for e in es if e["hallucinated_file"] is True),
        "provider_contaminated": sum(1 for e in es if e["provider_failure"]),
        "infrastructure_failures": sum(1 for e in es if e["FINAL_CLASSIFICATION"] == "infrastructure_failure"),
        "classifications": dict(Counter(e["FINAL_CLASSIFICATION"] for e in es)),
        "retry_budgets": dict(Counter(e["retry_budget"] for e in es)),
    }

ledger = {
    "experiment": EXP_ID,
    "generated": "2026-09-10 (post-hoc canonical ledger built from existing raw artifacts; no task was rerun, no raw JSON modified)",
    "generator": "evaluation/tmp/build_v3_ledger.py importing evaluation/build_ledger.py (provider_signature + FINAL_CLASSIFICATION precedence); extension A: provider.contamination records; extension B: adaptive controller repair block",
    "provider": "nara",
    "requested_model": "laguna-s-2.1",
    "systems": list(SYSTEMS),
    "retry_budget_disclosure": {
        "adaptive_multi_agent": "retry_budget=1 on 23 tasks, 2 on 5 tasks (from raw repair blocks)",
        "baseline_b": "retry_budget=3 on 23 tasks",
        "verdict": "UNEQUAL retry budgets across arms. First-pass and repair comparisons are NOT budget-equivalent and must not be presented as matched.",
    },
    "classification_precedence": ["provider_failure", "infrastructure_failure", "resolved", "genuine_agent_failure", "invalid_evaluation"],
    "paired_clean_rule": "task included iff FINAL_CLASSIFICATION in {resolved, genuine_agent_failure} for BOTH systems",
    "entries": entries,
    "paired_analysis": {
        "primary": {
            "rule": "PRIMARY (usable-outcome paired set): exclude task iff either system's run FATAL-ly died to a provider error (execution.status=error with provider signature -> no usable output). Contaminated-but-completed runs are kept as observed outcomes.",
            "task_count": len(paired_tasks),
            "tasks": paired_tasks,
            "excluded_tasks": excluded_tasks,
            "exclusion_reasons": {
                "task_003": "baseline_b run died: raw 502 (provider_server_error), status=error",
                "task_004": "baseline_b run died: raw 502, status=error",
                "task_008": "adaptive died: HTTP-200-wrapped upstream_error (request b1e31b5e); baseline_b also died: raw 502",
                "task_010": "adaptive died: HTTP-200-wrapped upstream_error (request f13ce35b); baseline_b run completed but failed hidden tests (genuine)",
                "task_017": "baseline_b run died: raw 502, status=error",
                "task_018": "baseline_b run died: raw 502, status=error",
                "task_023": "baseline_b run died: raw 502, status=error",
                "task_024": "baseline_b run died: raw 502, status=error",
            },
            "outcomes": {k: len(v) for k, v in cells.items()},
            "outcome_tasks": cells,
            "adaptive_resolved": sum(1 for t in paired_tasks if by_ts[(t, "adaptive_multi_agent")]["final_resolved"]),
            "baseline_resolved": sum(1 for t in paired_tasks if by_ts[(t, "baseline_b")]["final_resolved"]),
            "discordant": {"adaptive_only_wins": n10, "baseline_only_wins": n01},
            "mcnemar_exact_two_sided_p": p_clean,
        },
        "strict_sensitivity": {
            "rule": "STRICT: additionally exclude any task where either system recorded ANY provider error (drops adaptive task_020, whose run was contaminated mid-research yet completed and failed).",
            "task_count": len(strict_tasks),
            "tasks": strict_tasks,
            "outcomes": {k: len(v) for k, v in strict_cells.items()},
            "adaptive_resolved": sum(1 for t in strict_tasks if by_ts[(t, "adaptive_multi_agent")]["final_resolved"]),
            "baseline_resolved": sum(1 for t in strict_tasks if by_ts[(t, "baseline_b")]["final_resolved"]),
            "discordant": {"adaptive_only_wins": s10, "baseline_only_wins": s01},
            "mcnemar_exact_two_sided_p": p_strict,
        },
        "task_020_separate_disclosure": "adaptive_multi_agent run on task_020 recorded a provider error (502 at research, in provider.contamination ONLY) yet COMPLETED and failed hidden tests. In the PRIMARY set it is kept as an observed adaptive failure (baseline legitimately resolved task_020). In the STRICT set it is excluded. Both tiers give McNemar p=1.0, so the conclusion is unchanged.",
        "all_30_descriptive": {
            "note": "CONFOUNDED descriptive table (asymmetric provider contamination): counted over all 30 tasks with no exclusions.",
            "outcomes": {k: len(v) for k, v in all30.items()},
            "outcome_tasks": all30,
            "discordant": {"adaptive_only_wins": a30_10, "baseline_only_wins": a30_01},
            "mcnemar_exact_two_sided_p": p_all30,
            "mcnemar_one_sided_p_all30": min(1.0, p_all30 / 2),
            "correction_note": "The original report's 'p=0.070 (two-tailed)' is the ONE-SIDED p-value mislabeled; the exact two-sided p for 9v3 is 0.146.",
        },
        "claimed_N28_note": "The original report's 'Paired N = 28' matches no inclusion rule and is not derivable from the raw data.",
    },
    "per_system_full30": per_system,
    "efficiency": {
        "denominator_labels": {
            "all_30": "runs with numeric fields over all 30 tasks (dead error runs carry latency only; latency mean here is NOT meaningful)",
            "runs_with_output": "runs that made >=1 LLM call (adaptive 28 incl. contaminated task_020; baseline 23) — HEADLINE efficiency denominator",
            "valid_only": "FINAL_CLASSIFICATION in {resolved, genuine_agent_failure} (adaptive 27, baseline 23)",
            "primary_paired_22": "the 22 primary paired tasks",
            "strict_paired_21": "the 21 strict paired tasks",
        },
        "by_system": eff_block,
    },
    "validity": {
        "paired_clean_22": "VALID as descriptive comparison ONLY: same provider/model, same tasks, but retry budgets unequal (adaptive 1-2 vs baseline 3) and the 502 burst hit baseline asymmetrically (7 runs) vs adaptive (3 runs). Not budget-matched; not significance-tested.",
        "all_30_cross_system": "CONFOUNDED/INVALID: 6 of 9 adaptive-only wins are baseline provider failures.",
        "genuine_infrastructure_failures": 0,
        "provider_contaminated_runs": sum(1 for e in entries if e["provider_failure"]),
    },
}

LEDGER_OUT.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
print(f"wrote {LEDGER_OUT.relative_to(ROOT)} ({len(entries)} entries)")

# ---- number sheet for the corrected reports --------------------------------
print("\n===== NUMBER SHEET =====")
print("paired_clean n:", len(paired_tasks), "tasks:", paired_tasks)
print("excluded:", excluded_tasks)
print("clean outcomes:", {k: len(v) for k, v in cells.items()}, cells)
print("clean mcnemar two-sided p:", p_clean)
print("all30 outcomes:", {k: len(v) for k, v in all30.items()})
print("all30 mcnemar two-sided p:", p_all30, "one-sided:", min(1.0, p_all30 / 2))
for s in SYSTEMS:
    print(f"\n{s} per_system: {json.dumps(per_system[s])}")
    print(f"{s} efficiency:")
    for dk in ("all_30", "runs_with_output", "valid_only", "primary_paired_22", "strict_paired_21"):
        print(f"  {dk}: {json.dumps(eff_block[s][dk])}")
    print(f"  primary cost/resolved: {eff_block[s]['primary_paired_22_cost_per_resolved_usd']}  strict: {eff_block[s]['strict_paired_21_cost_per_resolved_usd']}")
pa = per_system["adaptive_multi_agent"]
pb = per_system["baseline_b"]
print("\nclean resolved: adaptive", sum(1 for t in paired_tasks if by_ts[(t, 'adaptive_multi_agent')]['final_resolved']),
      "baseline", sum(1 for t in paired_tasks if by_ts[(t, 'baseline_b')]['final_resolved']))
print("budgets: adaptive", dict(Counter(by_ts[(t, 'adaptive_multi_agent')]['retry_budget'] for t in TASK_IDS)),
      "baseline", dict(Counter(by_ts[(t, 'baseline_b')]['retry_budget'] for t in TASK_IDS)))
print("provider-contaminated runs:", sum(1 for e in entries if e["provider_failure"]),
      sorted({(e['task_id'], e['system']) for e in entries if e['provider_failure']}))
print("escalations:", [(t, by_ts[(t, 'adaptive_multi_agent')]['final_path'],
                        by_ts[(t, 'adaptive_multi_agent')]['final_resolved']) for t in TASK_IDS if by_ts[(t, 'adaptive_multi_agent')]['escalated']])
print("adaptive repair:", [(t, by_ts[(t, 'adaptive_multi_agent')]['repair_eligible'],
                            by_ts[(t, 'adaptive_multi_agent')]['repair_attempts'],
                            by_ts[(t, 'adaptive_multi_agent')]['repair_recovered']) for t in TASK_IDS
                           if by_ts[(t, 'adaptive_multi_agent')]['repair_eligible']])
print("adaptive fp discrepancy tasks:", [t for t in TASK_IDS if by_ts[(t, 'adaptive_multi_agent')].get('adaptive_first_pass_discrepancy')])
print("baseline repair recovered:", [t for t in TASK_IDS if by_ts[(t, 'baseline_b')]['repair_recovered']])
