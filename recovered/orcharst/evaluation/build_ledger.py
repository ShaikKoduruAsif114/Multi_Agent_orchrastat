"""
evaluation/build_ledger.py

Build the CANONICAL evaluation package from raw benchmark result files:
    task_ledger.json     per-run canonical entries + per-system aggregates
    analysis.json        machine-readable per-system metrics (labeled denominators)
    paired_analysis.json canonical paired analysis (explicit inclusion tiers)

The ledger is the single authoritative record every metric is derived from —
no ad-hoc log parsing, no invented denominators.

Usage:
    python evaluation/build_ledger.py --experiment <experiment_id>
    python evaluation/build_ledger.py --experiment <exp> --skip-manifest-gate

FINAL CLASSIFICATION precedence (a run gets exactly one; provider beats all):
  provider_failure        any recorded LLM call failed with a provider error,
                          INCLUDING errors recorded only in the provider
                          contamination block and HTTP-200-wrapped
                          "upstream_error" payloads (precedence rule: provider
                          contamination beats generic runner/infrastructure
                          labels)
  infrastructure_failure  runner-level error without any provider signature
  resolved                deterministic verifier conditions all hold
  genuine_agent_failure   valid clean run, hidden tests executed and failed
  invalid_evaluation      raw record missing/unusable fields

DENOMINATORS are explicit code (see paired_analysis.denominator_rules()):
  all_runs          every run of the system
  runs_with_output  runs that made >= 1 LLM call (headline efficiency set)
  valid_only        FINAL_CLASSIFICATION in {resolved, genuine_agent_failure}
  paired:valid      PRIMARY clean paired set (both arms valid)
  paired:fatal      sensitivity set (neither arm fatally died to provider error)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # allow direct imports
import paired_analysis as PA                      # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUESTED_MODEL = os.getenv("NARAROUTER_MODEL", "laguna-s-2.1")
PROVIDER = "nara"

ADAPTIVE_SYSTEMS = {"adaptive_multi_agent"}
VALID_CLASSES = PA.VALID_CLASSES


def provider_signature(text: str) -> tuple[bool, str, str]:
    """Return (is_provider_failure, category, http_status) for an error string."""
    t = (text or "").lower()
    if "error code: 502" in t:
        return True, "provider_server_error", "502"
    if "error code: 503" in t:
        return True, "provider_unavailable", "503"
    if "error code: 429" in t or "rate limit" in t:
        return True, "provider_rate_limit", "429"
    if "error code: 401" in t or "error code: 403" in t:
        return True, "provider_auth_error", "401/403"
    if "upstream_error" in t or "temporarily unavailable" in t:
        return True, "provider_upstream_error", "200"
    if "provider_timeout" in t or "timed out" in t:
        return True, "provider_timeout", ""
    if "model_not_found" in t or "model not found" in t:
        return True, "provider_model_unavailable", ""
    if "connection" in t and ("error" in t or "failed" in t):
        return True, "provider_unavailable", ""
    return False, "", ""


def served_models_of(d: dict) -> list:
    out = set()
    em = d.get("eval_metrics") or {}
    for c in em.get("llm_calls", []) or []:
        if c.get("served_model"):
            out.add(c["served_model"])
    for c in (d.get("repair", {}) or {}).get("llm_calls", []) or []:
        if c.get("served_model"):
            out.add(c["served_model"])
    for m in (d.get("provider", {}) or {}).get("served_models", []) or []:
        out.add(m)
    return sorted(out)


def llm_call_records(d: dict) -> list:
    em = d.get("eval_metrics") or {}
    recs = list(em.get("llm_calls", []) or [])
    for c in (d.get("repair", {}) or {}).get("llm_calls", []) or []:
        recs.append(c)
    return recs


def contamination_records(d: dict) -> list:
    """Explicit contamination metadata in the raw provider block.

    PRECEDENCE RULE: a provider.contamination / provider_contamination record
    outranks generic benchmark-runner or infrastructure labels. Some provider
    errors are recorded ONLY here (e.g. adaptive task_020: 502 during research
    recorded in provider.contamination while the run completed).
    """
    prov = d.get("provider") or {}
    recs = []
    flagged = bool(prov.get("contamination_detected") or d.get("provider_contamination"))
    if flagged:
        for c in prov.get("contamination") or []:
            sig = provider_signature(c.get("error", ""))
            recs.append({
                "stage": c.get("stage"),
                "error": (c.get("error") or "")[:300],
                "failure_category": sig[1] or c.get("failure_category") or "provider_error",
                "http_status": sig[2] or None,
                "source": "provider.contamination record",
            })
        if not recs:
            # Flag set with no detail rows: still a contamination signal.
            recs.append({
                "stage": None, "error": "(no detail rows recorded)",
                "failure_category": "provider_error", "http_status": None,
                "source": "provider.contamination_detected flag",
            })
    return recs


def _attempts_int(v) -> int:
    """Null-safe attempt count. repair.attempts=null means the repair loop
    never ran beyond the first attempt -> 1 total attempt (regression: some
    baseline error runs record attempts=null and must not crash the ledger)."""
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return 1


def outcome_consistency_flags(d: dict, resolved_final: bool) -> list:
    """Detect internally inconsistent outcome fields in a raw record."""
    flags = []
    reg = d.get("regression", {}) or {}
    status = (d.get("execution", {}) or {}).get("status")
    if resolved_final and reg.get("hidden_tests_executed") is not True:
        flags.append("resolved_but_hidden_tests_not_executed")
    if resolved_final and reg.get("hidden_tests_passed") is not True:
        flags.append("resolved_but_hidden_tests_failed")
    if status == "resolved" and not resolved_final:
        flags.append("status_resolved_but_outcome_false")
    if status != "resolved" and resolved_final:
        flags.append("outcome_true_but_status_not_resolved")
    rep = d.get("repair", {}) or {}
    if rep.get("repair_recovered") is True and rep.get("first_pass_resolved_hidden") is not False \
            and rep.get("first_attempt_success") is not False:
        flags.append("recovered_without_recorded_first_pass_failure")
    tests = d.get("tests", {}) or {}
    if tests.get("generated") is False and tests.get("generated_tests_executed") is True:
        # Recorded quirk (task_002/task_001 class): run-level generated flag
        # false while test execution happened. Informational, not fatal.
        flags.append("info:tests_generated_false_but_executed_true")
    if reg.get("hidden_tests_passed") is True and reg.get("hidden_tests_executed") is not True:
        flags.append("hidden_passed_without_execution")
    # record-level outcome contradictions (such runs classify as
    # invalid_evaluation: the verifier result and the provenance disagree)
    loc = d.get("localization", {}) or {}
    if resolved_final and loc.get("top1_correct") is False:
        flags.append("e2e_true_but_top1_false")
    if resolved_final and (d.get("patch", {}) or {}).get("syntax_valid") is False:
        flags.append("e2e_true_but_syntax_invalid")
    return flags


def build_entry(d: dict) -> dict:
    """Build one canonical ledger entry from a raw result dict."""
    sysname = d.get("system", "")
    task_id = d.get("task_id", "")
    recs = llm_call_records(d)

    # ---- provider failure scan (authoritative) -----------------------------
    provider_failure = False
    provider_cats = set()
    provider_status = set()
    provider_msgs = []
    for c in recs:
        if c.get("ok") is False:
            sig = provider_signature(c.get("error", ""))
            if sig[0]:
                provider_failure = True
                provider_cats.add(sig[1])
                if sig[2]:
                    provider_status.add(sig[2])
                provider_msgs.append({"stage": c.get("stage"),
                                      "error": (c.get("error") or "")[:300]})
    runner_err = (d.get("execution", {}) or {}).get("error_message") or ""
    rsig = provider_signature(runner_err)
    if rsig[0]:
        provider_failure = True
        provider_cats.add(rsig[1] + "[runner]")
        if rsig[2]:
            provider_status.add(rsig[2])
        provider_msgs.append({"stage": "runner", "error": runner_err[:300]})

    # PRECEDENCE: explicit contamination records outrank generic runner labels.
    crecs = contamination_records(d)
    if crecs:
        provider_failure = True
        provider_cats.update(c["failure_category"] for c in crecs)
        provider_status.update(c["http_status"] for c in crecs if c["http_status"])
        provider_msgs.extend(crecs)

    ex_status = (d.get("execution", {}) or {}).get("status")
    # Deterministic patch-quality gate rejections (syntax/placeholder/apply)
    # are GENUINE AGENT failures: all LLM calls succeeded, the model simply
    # produced invalid code. Only non-gate runner/environment errors count
    # as infrastructure failures. Provider contamination always wins.
    gate_rejection = runner_err.startswith("patch_quality_gate_failed") or ex_status in (
        "patch_failed", "patch_placeholder", "syntax_error",
    )
    infra_failure = ex_status == "error" and not provider_failure and not gate_rejection

    # ---- repair accounting --------------------------------------------------
    repair = d.get("repair", {}) or {}
    adaptive = d.get("adaptive", {}) or {}
    if sysname in ADAPTIVE_SYSTEMS:
        # Adaptive controller block is authoritative for repair accounting.
        first_pass_resolved = repair.get("first_pass_resolved_hidden")
        repair_attempt_count = int(adaptive.get("repair_attempts") or 0)
        repair_eligible = bool(adaptive.get("repair_eligible"))
        repair_recovered = bool(adaptive.get("repair_recovered"))
    elif sysname == "multi_agent":
        repair_attempt_count = int(repair.get("repair_attempt_count",
                                              max(0, _attempts_int(repair.get("attempts")) - 1)))
        first_pass_resolved = repair.get("first_pass_resolved_hidden")
        repair_eligible = bool(repair.get("repair_eligible", False))
        repair_recovered = bool(repair.get("repair_recovered", False))
    else:
        # baseline_b / others: repair loop = attempts beyond the first;
        # first-pass semantic is native (attempt-0 hidden tests).
        repair_attempt_count = max(0, _attempts_int(repair.get("attempts")) - 1)
        fp = repair.get("first_pass_resolved_hidden", repair.get("first_attempt_success"))
        first_pass_resolved = fp
        repair_eligible = (fp is False) and repair_attempt_count > 0
        repair_recovered = bool(
            fp is False and repair_attempt_count > 0 and d.get("end_to_end_resolved") is True
        )

    # Contradictory first-pass fields (V3 regression: adaptive block said
    # first_pass_resolved=false while hidden tests recorded a first-pass
    # success). Canonical source: repair.first_pass_resolved_hidden.
    first_pass_field_conflict = None
    if sysname in ADAPTIVE_SYSTEMS:
        ctrl_fp = adaptive.get("first_pass_resolved")
        if ctrl_fp is not None and first_pass_resolved is not None and ctrl_fp != first_pass_resolved:
            first_pass_field_conflict = {
                "canonical_value": first_pass_resolved,
                "adaptive_block_value": ctrl_fp,
                "note": "canonical = repair.first_pass_resolved_hidden (hidden-test-derived)",
            }

    # ---- localization --------------------------------------------------------
    loc = d.get("localization", {}) or {}
    top1 = loc.get("top1_correct")
    top3 = loc.get("top3_correct", top1)
    hall = loc.get("hallucinated_file")
    localization_evaluable = loc.get("predicted_file") is not None
    if not localization_evaluable:
        top1 = None
        top3 = None

    # ---- patch / tests / efficiency -----------------------------------------
    patch = d.get("patch", {}) or {}
    tests = d.get("tests", {}) or {}
    reg = d.get("regression", {}) or {}
    ex = d.get("execution", {}) or {}
    cost = (d.get("cost", {}) or {}).get("estimated_usd")

    resolved_final = d.get("end_to_end_resolved") is True
    consistency = outcome_consistency_flags(d, resolved_final)

    # hidden passed-count vs run-level boolean (task_002-class discrepancy:
    # summed per-test counts and run-level booleans can disagree).
    passed_count = reg.get("hidden_tests_passed_count")
    hidden_total = reg.get("hidden_tests_total")
    hidden_exec = reg.get("hidden_tests_executed")
    hidden_pass = reg.get("hidden_tests_passed")
    hidden_count_inconsistent = None
    if hidden_pass is True and isinstance(passed_count, int) and passed_count == 0 \
            and (hidden_exec is True):
        hidden_count_inconsistent = "passed=true but passed_count=0"
    if hidden_pass is False and isinstance(passed_count, int) \
            and isinstance(hidden_total, int) and hidden_total > 0 \
            and passed_count == hidden_total:
        hidden_count_inconsistent = "passed=false but passed_count==hidden_tests_total"

    # ---- FINAL CLASSIFICATION (precedence order) ----------------------------
    if provider_failure:
        final_classification = "provider_failure"
    elif infra_failure:
        final_classification = "infrastructure_failure"
    elif resolved_final and top1 is not False and patch.get("syntax_valid") is not False:
        final_classification = "resolved"
    elif gate_rejection:
        final_classification = "genuine_agent_failure"
    elif hidden_exec and hidden_pass is False:
        final_classification = "genuine_agent_failure"
    else:
        final_classification = "invalid_evaluation"

    first_pass_status = (
        "FIRST_PASS_SUCCESS" if first_pass_resolved is True
        else ("FIRST_PASS_FAILURE_REPAIR_RECOVERED" if repair_recovered
              else ("FIRST_PASS_FAILURE_REPAIR_FAILED" if (repair_eligible and not repair_recovered)
                    else ("FIRST_PASS_FAILURE_NO_BUDGETED_REPAIR" if first_pass_resolved is False
                          else "UNKNOWN")))
    )
    if provider_failure:
        first_pass_status = "PROVIDER_FAILURE"
    if infra_failure:
        first_pass_status = "INFRASTRUCTURE_FAILURE"

    entry = {
        "task_id": task_id,
        "system": sysname,
        "provider": PROVIDER,
        "requested_model": REQUESTED_MODEL,
        "served_model": sorted(served_models_of(d)),
        "first_pass_status": first_pass_status,
        "first_pass_resolved": first_pass_resolved,
        "first_pass_failure_category": None if first_pass_resolved else "first_patch_failed_hidden_tests",
        "first_pass_field_conflict": first_pass_field_conflict,
        "repair_eligible": repair_eligible,
        "repair_attempts": repair_attempt_count,
        "repair_recovered": repair_recovered,
        "final_status": ex_status,
        "final_resolved": resolved_final,
        "provider_failure": provider_failure,
        "provider_http_status": sorted(provider_status) or None,
        "provider_error_type": sorted(provider_cats) or None,
        "provider_error_message": provider_msgs or None,
        "provider_contamination_source": (
            "provider.contamination record" if crecs
            else "execution.error_message/llm_call_records" if provider_failure else None),
        "localization_top1": top1,
        "localization_top3": top3,
        "localization_evaluable": localization_evaluable,  # single-file prediction systems
        "hallucinated_file": hall,
        "patch_generated": patch.get("generated"),
        "patch_placeholder": patch.get("is_placeholder"),
        "patch_syntax_valid": patch.get("syntax_valid"),
        "patch_apply_success": patch.get("patch_apply_success"),
        "modified_target_correct": loc.get("valid", None),
        "generated_tests_created": tests.get("generated"),
        "generated_tests_executed": tests.get("generated_tests_executed"),
        "generated_tests_passed": tests.get("generated_tests_passed"),
        "hidden_tests_executed": hidden_exec,
        "hidden_tests_passed": hidden_pass,
        "hidden_tests_total": hidden_total,
        "hidden_tests_passed_count": passed_count,
        "hidden_count_inconsistent": hidden_count_inconsistent,
        "outcome_consistency_flags": consistency or None,
        "llm_calls": ex.get("llm_calls"),
        "input_tokens": ex.get("input_tokens"),
        "output_tokens": ex.get("output_tokens"),
        "total_tokens": ex.get("total_tokens"),
        "latency_seconds": ex.get("latency_seconds"),
        "cost": cost,
        "infrastructure_failure": infra_failure,
        "FINAL_CLASSIFICATION": final_classification,
        "final_classification_values": ["resolved", "genuine_agent_failure",
                                        "provider_failure", "infrastructure_failure",
                                        "invalid_evaluation"],
    }

    # ---- adaptive / path metadata -------------------------------------------
    if sysname in ADAPTIVE_SYSTEMS:
        for k_src in ("difficulty_score", "difficulty_class", "initial_path",
                      "final_path", "escalated", "escalation_reason", "path_reason"):
            entry[k_src] = adaptive.get(k_src)
    entry["retry_budget"] = repair.get("retry_budget")
    entry["paired_valid_included"] = None      # filled by build_paired_tiers
    entry["paired_fatal_included"] = None
    entry["exclusion_reason"] = None
    return entry


def mcnemar_exact(b: int, c: int) -> float:
    """Backwards-compatible alias; exact two-sided McNemar."""
    return PA.mcnemar_exact_two_sided(b, c)


# ------------------------------------------------------------- aggregates ----
def _num(entries: list, key: str) -> list:
    return [e[key] for e in entries if isinstance(e.get(key), (int, float))]


def efficiency_block(entries: list, paired_valid_tasks: list, paired_fatal_tasks: list) -> dict:
    """Per-system efficiency over EXPLICITLY LABELED denominators."""
    out = {}
    for sysname in sorted({e["system"] for e in entries}):
        es = [e for e in entries if e["system"] == sysname]
        rwo = [e for e in es if (e.get("llm_calls") or 0) > 0]
        valid = [e for e in es if e["FINAL_CLASSIFICATION"] in VALID_CLASSES]
        pv = [e for e in es if e["task_id"] in paired_valid_tasks]
        pf = [e for e in es if e["task_id"] in paired_fatal_tasks]

        def block(sel: list) -> dict:
            b = {"n": len(sel)}
            for key, nd in (("llm_calls", 3), ("total_tokens", 1),
                            ("latency_seconds", 2), ("cost", 6)):
                vals = _num(sel, key)
                b[f"{key}_n"] = len(vals)
                b[f"{key}_mean"] = round(statistics.mean(vals), nd) if vals else None
            tok = _num(sel, "total_tokens")
            if tok:
                b["total_tokens_sum"] = sum(tok)
                b["total_tokens_median"] = statistics.median(tok)
            lat = sorted(_num(sel, "latency_seconds"))
            if lat:
                b["latency_median_s"] = round(statistics.median(lat), 2)
                b["latency_p90_nearest_rank_s"] = round(
                    lat[min(len(lat) - 1, math.ceil(0.9 * len(lat)) - 1)], 2)
            calls = _num(sel, "llm_calls")
            if calls:
                b["llm_calls_median"] = statistics.median(calls)
                b["llm_calls_max"] = max(calls)
            costs = _num(sel, "cost")
            if costs:
                b["cost_total_usd"] = round(sum(costs), 6)
            return b

        def cost_per_resolved(sel: list):
            rc = [e["cost"] for e in sel
                  if isinstance(e.get("cost"), (int, float)) and e.get("final_resolved") is True]
            return round(sum(rc) / len(rc), 6) if rc else None

        out[sysname] = {
            "all_runs": block(es),
            "runs_with_output": block(rwo),
            "runs_with_output_task_ids": [e["task_id"] for e in rwo],
            "valid_only": block(valid),
            "paired_valid": block(pv),
            "paired_fatal": block(pf),
            "paired_valid_cost_per_resolved_usd": cost_per_resolved(pv),
            "denominator_labels": {
                "all_runs": "every run of the system (dead error runs included; latency mean NOT meaningful here)",
                "runs_with_output": "runs that made >=1 LLM call — HEADLINE efficiency denominator",
                "valid_only": "FINAL_CLASSIFICATION in {resolved, genuine_agent_failure}",
                "paired_valid": "PRIMARY clean paired set (both arms valid)",
                "paired_fatal": "sensitivity paired set (neither arm fatally died)",
            },
        }
    return out


def per_system_block(entries: list) -> dict:
    out = {}
    for sysname in sorted({e["system"] for e in entries}):
        es = [e for e in entries if e["system"] == sysname]
        valid = [e for e in es if e["FINAL_CLASSIFICATION"] in VALID_CLASSES]
        out[sysname] = {
            "n": len(es),
            "final_resolved": sum(1 for e in es if e["final_resolved"] is True),
            "final_resolved_valid_only": sum(1 for e in valid if e["final_resolved"] is True),
            "valid_n": len(valid),
            "first_pass_resolved": sum(1 for e in es if e["first_pass_resolved"] is True),
            "repair_eligible": sum(1 for e in valid if e["repair_eligible"]),
            "repair_recovered": sum(1 for e in valid
                                    if e["repair_eligible"] and e["repair_recovered"]),
            "repair_attempts_mean_all_runs": (
                round(statistics.mean(a), 3) if (a := _num(es, "repair_attempts")) else None),
            "top1_evaluable": sum(1 for e in es if e["localization_evaluable"]),
            "top1_correct": sum(1 for e in es if e["localization_evaluable"]
                                and e["localization_top1"] is True),
            "hallucinated_count": sum(1 for e in es if e["hallucinated_file"] is True),
            "provider_contaminated": sum(1 for e in es if e["provider_failure"]),
            "infrastructure_failures": sum(
                1 for e in es if e["FINAL_CLASSIFICATION"] == "infrastructure_failure"),
            "hidden_tests_executed": sum(1 for e in es if e["hidden_tests_executed"] is True),
            "hidden_tests_passed": sum(1 for e in es if e["hidden_tests_passed"] is True),
            "classifications": dict(Counter(e["FINAL_CLASSIFICATION"] for e in es)),
            "retry_budgets": dict(Counter(
                "unrecorded" if e.get("retry_budget") is None
                else str(e.get("retry_budget")) for e in es)),
            "escalations": sum(1 for e in es if e.get("escalated") is True),
            "path_distribution": dict(Counter(
                e.get("final_path") or "unrecorded" for e in es if e.get("final_path"))),
        }
    return out


def build_paired_tiers(entries: list) -> tuple:
    """Attach per-entry paired flags/exclusion reasons; return
    (paired_analysis_dict, valid_tasks, fatal_tasks)."""
    systems = tuple(sorted({e["system"] for e in entries}))
    if len(systems) != 2:
        return ({"error": f"paired analysis requires exactly 2 systems, found {sorted(systems)}",
                 "systems_found": sorted(systems)},
                [], [])
    pa = PA.paired_analysis(entries, systems)
    valid_tasks = pa["tiers"]["valid"]["tasks"]
    fatal_tasks = pa["tiers"]["fatal"]["tasks"]
    by_key = PA.index_entries(entries)
    for e in entries:
        t = e["task_id"]
        e["paired_valid_included"] = t in valid_tasks
        e["paired_fatal_included"] = t in fatal_tasks
        if e["paired_valid_included"]:
            e["exclusion_reason"] = None
        else:
            reason = pa["tiers"]["valid"]["excluded_tasks"].get(t)
            side = e["system"] if not PA.is_valid_run(e) else "other arm"
            e["exclusion_reason"] = f"{side}: {reason}" if reason else "excluded from primary pair set"
    return pa, valid_tasks, fatal_tasks


def build_package(experiment: str, raw_dir: Path, out_dir: Path,
                  skip_manifest_gate: bool = False) -> tuple:
    """Build all three canonical artifacts. Returns (paths, warnings)."""
    warnings = []

    # ---- immutable-input gate ------------------------------------------------
    manifest_report = None
    if not skip_manifest_gate:
        from verify_manifest import verify_manifest
        manifest_report = verify_manifest()
        if not manifest_report["ok"]:
            raise SystemExit(
                "[LEDGER] ABORT: frozen benchmark inputs failed verification "
                f"(changed={len(manifest_report['changed'])} missing={len(manifest_report['missing'])} "
                f"extra={len(manifest_report['extra'] or [])}). Refusing to emit a ledger for a "
                "comparability-breaking input set. Use --skip-manifest-gate only for forensic "
                "post-hoc analysis.")

    # ---- load raw ------------------------------------------------------------
    rows = []
    for f in sorted(raw_dir.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            warnings.append(f"unparseable raw file skipped: {f.name} ({exc})")
            continue
        if isinstance(d, dict) and "task_id" in d and "system" in d:
            rows.append(build_entry(d))
    if not rows:
        raise SystemExit(f"[LEDGER] no raw results found in {raw_dir}")

    # ---- paired tiers (also stamps per-entry flags) ---------------------------
    pa, valid_tasks, fatal_tasks = build_paired_tiers(rows)
    systems = tuple(sorted({e["system"] for e in rows}))

    # ---- artifacts -----------------------------------------------------------
    per_system = per_system_block(rows)
    efficiency = efficiency_block(rows, valid_tasks, fatal_tasks)
    contaminated = sorted(
        (e["task_id"], e["system"]) for e in rows if e["provider_failure"])
    infra = sorted(
        (e["task_id"], e["system"]) for e in rows
        if e["FINAL_CLASSIFICATION"] == "infrastructure_failure")
    budgets_equal = (len(per_system) == 2 and
                     sorted(per_system[systems[0]]["retry_budgets"].keys()) ==
                     sorted(per_system[systems[1]]["retry_budgets"].keys()))
    retry_disclosure = {
        s: per_system[s]["retry_budgets"] for s in systems
    } | {
        "budgets_equal_across_arms": budgets_equal,
        "verdict": ("retry budgets matched across arms"
                    if budgets_equal else
                    "UNEQUAL retry budgets across arms; first-pass and repair "
                    "comparisons are NOT budget-equivalent and must be disclosed"),
    }

    analysis = {
        "experiment": experiment,
        "requested_model": REQUESTED_MODEL,
        "provider": PROVIDER,
        "n_runs": len(rows),
        "systems": per_system,
        "efficiency": efficiency,
        "contamination": {
            "provider_contaminated_runs": contaminated,
            "provider_contaminated_count": len(contaminated),
            "genuine_infrastructure_failures": infra,
            "genuine_infrastructure_failure_count": len(infra),
            "precedence_rule": "provider contamination outranks generic runner/infrastructure labels",
        },
        "retry_budget_disclosure": retry_disclosure,
    }

    ledger = {
        "experiment": experiment,
        "generator": "evaluation/build_ledger.py",
        "provider": PROVIDER,
        "requested_model": REQUESTED_MODEL,
        "systems": list(systems),
        "classification_precedence": ["provider_failure", "infrastructure_failure",
                                      "resolved", "genuine_agent_failure",
                                      "invalid_evaluation"],
        "manifest_verification": manifest_report and {
            "ok": manifest_report["ok"],
            "verified": manifest_report["verified"],
            "manifest_entries": manifest_report["manifest_entries"],
        },
        "entries": rows,
        "analysis_ref": "analysis.json",
        "paired_analysis_ref": "paired_analysis.json",
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "task_ledger": out_dir / "task_ledger.json",
        "analysis": out_dir / "analysis.json",
        "paired_analysis": out_dir / "paired_analysis.json",
    }
    paths["task_ledger"].write_text(json.dumps(ledger, indent=2, default=str), encoding="utf-8")
    paths["analysis"].write_text(json.dumps(analysis, indent=2, default=str), encoding="utf-8")
    paths["paired_analysis"].write_text(json.dumps(pa, indent=2, default=str), encoding="utf-8")
    return paths, warnings


def main():
    ap = argparse.ArgumentParser(description="Build canonical 3-artifact evaluation package.")
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--raw-dir", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--skip-manifest-gate", action="store_true",
                    help="forensic only: skip frozen-input verification")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    exp_dir = REPO_ROOT / "evaluation" / "results" / args.experiment
    raw_dir = Path(args.raw_dir) if args.raw_dir else exp_dir / "raw"
    out_dir = Path(args.out) if args.out else exp_dir

    paths, warnings = build_package(args.experiment, raw_dir, out_dir,
                                    skip_manifest_gate=args.skip_manifest_gate)
    ledger = json.loads(paths["task_ledger"].read_text(encoding="utf-8"))
    if not args.quiet:
        for w in warnings:
            print(f"[WARN] {w}")
        print(f"[LEDGER] {len(ledger['entries'])} entries -> {paths['task_ledger']}")
        print(f"[LEDGER] analysis -> {paths['analysis']}")
        print(f"[LEDGER] paired   -> {paths['paired_analysis']}")
        ps = ledger.get("entries", [])
        for s in ledger["systems"]:
            es = [e for e in ps if e["system"] == s]
            print(f"  [{s}] n={len(es)} resolved={sum(1 for e in es if e['final_resolved'])} "
                  f"contaminated={sum(1 for e in es if e['provider_failure'])}")
        pa = json.loads(paths["paired_analysis"].read_text(encoding="utf-8"))
        if "tiers" in pa:
            for tier, t in pa["tiers"].items():
                print(f"  [paired:{tier}] N={t['N']} outcomes={t['outcome_counts']} "
                      f"mcnemar_p={t['mcnemar_exact_two_sided_p']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
