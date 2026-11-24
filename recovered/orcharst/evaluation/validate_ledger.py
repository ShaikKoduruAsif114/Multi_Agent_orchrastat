"""
evaluation/validate_ledger.py

Validate a canonical evaluation package (task_ledger.json + analysis.json +
paired_analysis.json) against its raw result JSONs. FAILS (exit 1) on any of:

  V01  missing task IDs            (expected task grid not covered)
  V02  duplicate task IDs          (duplicate raw/ledger (task, system) keys)
  V03  missing counterpart         (a system's run without the paired arm's)
  V04  retry-budget mismatch       (arms run with different retry budgets)
  V05  provider/model mismatch     (served model != requested model)
  V06  contradictory first-pass    (e.g. adaptive block vs hidden-test-derived)
  V07  inconsistent outcome fields (resolved but tests failed/not executed...)
  V08  undefined paired denominator(no primary tier derivable / N mismatch
                                    between artifacts)
  V09  stale aggregate artifacts   (aggregates.json / analyses.json / legacy
                                    ledger disagree with the canonical one)
  V10  hidden passed-count mismatch(run-level boolean vs per-test counts,
                                    reported as warnings + hard totals check)

Usage:
    python evaluation/validate_ledger.py --experiment <exp_id>
    python evaluation/validate_ledger.py --ledger <dir>
    python evaluation/validate_ledger.py --ledger <dir> --expected-tasks 30
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paired_analysis as PA          # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt_errs(code: str, items: list) -> list:
    return [f"{code}: {x}" for x in items]


def validate_package(pkg_dir: Path, expected_task_count: int | None = None,
                     expect_systems: list | None = None,
                     require_two_systems: bool = True) -> dict:
    """Run every validator. Returns report; `ok` False means hard failures."""
    errors: list = []
    warnings: list = []
    checks: dict = {}

    ledger_path = pkg_dir / "task_ledger.json"
    analysis_path = pkg_dir / "analysis.json"
    paired_path = pkg_dir / "paired_analysis.json"
    for p, name in ((ledger_path, "task_ledger.json"), (analysis_path, "analysis.json"),
                    (paired_path, "paired_analysis.json")):
        if not p.is_file():
            errors.append(f"V08: missing canonical artifact {name} in {pkg_dir}")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "checks": checks}

    ledger = _load(ledger_path)
    analysis = _load(analysis_path)
    paired = _load(paired_path)
    entries = ledger.get("entries") or []
    raw_dir = pkg_dir / "raw"
    raw_records = []
    if raw_dir.is_dir():
        for f in sorted(raw_dir.glob("*.json")):
            try:
                d = _load(f)
            except Exception as exc:
                errors.append(f"V02: unparseable raw file {f.name}: {exc}")
                continue
            if isinstance(d, dict) and "task_id" in d and "system" in d:
                raw_records.append(d)

    systems = sorted({e["system"] for e in entries}) or sorted(
        {r["system"] for r in raw_records})
    task_ids = sorted({e["task_id"] for e in entries})
    checks["n_entries"] = len(entries)
    checks["systems"] = systems

    # ---- V01 missing task IDs -----------------------------------------------
    if expected_task_count and len(task_ids) != expected_task_count:
        errors.append(f"V01: expected {expected_task_count} tasks, ledger covers "
                      f"{len(task_ids)} ({len(task_ids) - expected_task_count} missing)")
    if raw_dir.is_dir():
        raw_keys = {(r.get("task_id"), r.get("system")) for r in raw_records}
        led_keys = {(e["task_id"], e["system"]) for e in entries}
        missing_raw = sorted(f"{t}/{s}" for (t, s) in raw_keys - led_keys)
        if missing_raw:
            errors.append(_fmt_errs("V01", [
                f"raw runs missing from ledger: {missing_raw}"])[0])

    # ---- V02 duplicate task IDs ----------------------------------------------
    led_keys = [(e["task_id"], e["system"]) for e in entries]
    dupes = sorted({k for k in led_keys if led_keys.count(k) > 1})
    if dupes:
        errors.append(f"V02: duplicate (task_id, system) ledger entries: {dupes}")
    raw_keys_list = [(r.get("task_id"), r.get("system")) for r in raw_records]
    raw_dupes = sorted({k for k in raw_keys_list if k in raw_keys_list and
                        raw_keys_list.count(k) > 1 and k[0] is not None})
    if raw_dupes:
        errors.append(f"V02: duplicate (task_id, system) raw files: {raw_dupes}")

    # ---- V03 missing counterpart ----------------------------------------------
    by_key = {}
    for e in entries:
        by_key.setdefault(e["task_id"], {})[e["system"]] = e
    if expect_systems:
        missing_arms = sorted(set(expect_systems) - set(systems))
        if missing_arms:
            errors.append(f"V03: expected systems {sorted(expect_systems)} but ledger "
                          f"covers only {systems} (missing arms: {missing_arms})")
    if require_two_systems and len(systems) < 2:
        errors.append(f"V03: canonical paired package must cover 2 systems, "
                      f"found {systems} (pass require_two_systems=False for "
                      "single-arm forensic validation)")
    if len(systems) == 2:
        for t, m in sorted(by_key.items()):
            for s in systems:
                if s not in m:
                    errors.append(f"V03: task {t} has no run for system {s}")
    elif len(systems) > 2:
        errors.append(f"V03: paired package expects <=2 systems, found {systems}")

    # ---- V04 retry-budget mismatch ---------------------------------------------
    budgets = {}
    for s in systems:
        es = [e for e in entries if e["system"] == s]
        bset = sorted({str(e.get("retry_budget")) for e in es if e.get("retry_budget") is not None})
        budgets[s] = bset
    checks["retry_budgets"] = budgets
    if len(systems) == 2 and budgets[systems[0]] and budgets[systems[1]] \
            and budgets[systems[0]] != budgets[systems[1]]:
        errors.append(
            f"V04: retry-budget mismatch across arms: {systems[0]}={budgets[systems[0]]} "
            f"vs {systems[1]}={budgets[systems[1]]} (first-pass/repair comparisons "
            "are not budget-equivalent)")

    # ---- V05 provider/model mismatch --------------------------------------------
    requested = ledger.get("requested_model")
    mism = sorted({(e["task_id"], e["system"], m)
                   for e in entries for m in (e.get("served_model") or [])
                   if requested and m != requested})
    if mism:
        errors.append(f"V05: served model != requested model {requested!r}: {mism[:10]}"
                      + (f" (+{len(mism) - 10} more)" if len(mism) > 10 else ""))
    if not requested:
        errors.append("V05: ledger has no requested_model recorded")

    # ---- V06 contradictory first-pass fields --------------------------------------
    conflicts = []
    for e in entries:
        if e.get("first_pass_field_conflict"):
            conflicts.append(f"{e['task_id']}/{e['system']}: "
                             f"{e['first_pass_field_conflict']}")
    if conflicts:
        errors.append(_fmt_errs("V06", [
            "contradictory first-pass fields (canonical=repair.first_pass_resolved_hidden): "
            + "; ".join(conflicts)])[0])

    # ---- V07 inconsistent outcome fields --------------------------------------------
    for e in entries:
        for flag in (e.get("outcome_consistency_flags") or []):
            if not flag.startswith("info:"):
                errors.append(f"V07: {e['task_id']}/{e['system']}: {flag}")
    checks["outcome_info_flags"] = sorted(
        {f"{e['task_id']}/{e['system']}: {f}"
         for e in entries for f in (e.get("outcome_consistency_flags") or [])
         if f.startswith("info:")})

    # ---- V08 paired denominator defined + artifacts agree ------------------------------
    tiers = paired.get("tiers") or {}
    if "valid" not in tiers:
        errors.append("V08: paired_analysis.json has no 'valid' (primary) tier")
    else:
        n_tier = tiers["valid"]["N"]
        n_listed = len(tiers["valid"]["tasks"])
        if n_tier != n_listed:
            errors.append(f"V08: paired tier 'valid' N={n_tier} but lists {n_listed} tasks")
        cells = tiers["valid"]["outcome_counts"]
        if sum(cells.values()) != n_tier:
            errors.append(f"V08: paired tier 'valid' outcome cells sum {sum(cells.values())} "
                          f"!= N {n_tier} — undefined/leaky denominator")
    if analysis.get("n_runs") != len(entries):
        errors.append(f"V08: analysis.json n_runs={analysis.get('n_runs')} != "
                      f"ledger entries {len(entries)}")
    for s in systems:
        ps_block = (analysis.get("systems") or {}).get(s)
        if not ps_block:
            errors.append(f"V08: analysis.json missing system block {s}")
        elif ps_block.get("n") != sum(1 for e in entries if e["system"] == s):
            errors.append(f"V08: analysis.json {s} n={ps_block.get('n')} != ledger")

    # ---- V10 hidden passed-count totals vs run-level booleans ---------------------------
    count_mism = []
    for e in entries:
        if e.get("hidden_count_inconsistent"):
            count_mism.append(f"{e['task_id']}/{e['system']}: {e['hidden_count_inconsistent']}")
    if count_mism:
        warnings.append("V10: hidden-test passed-count vs run-level boolean discrepancies "
                        f"(raw artifact quirk, disclosed not altered): {count_mism}")

    # ---- V09 stale aggregate artifacts ----------------------------------------------------
    agg_path = pkg_dir / "aggregates" / "aggregates.json"
    ana_path = pkg_dir / "aggregates" / "analyses.json"
    stale = []

    def e2e_from_raw(system: str) -> int:
        return sum(1 for e in entries if e["system"] == system and e["final_resolved"] is True)

    if agg_path.is_file():
        try:
            agg = _load(agg_path)
            for s, block in (agg.get("systems") or {}).items():
                raw_e2e = e2e_from_raw(s)
                stale_e2e = block.get("e2e_resolved")
                if stale_e2e is not None and stale_e2e != raw_e2e:
                    stale.append(f"aggregates.json {s}.e2e_resolved={stale_e2e} "
                                 f"but canonical ledger says {raw_e2e}")
                lm = block.get("latency_mean_s")
                if lm is not None:
                    es = [e for e in entries if e["system"] == s]
                    lat = [e["latency_seconds"] for e in es
                           if isinstance(e.get("latency_seconds"), (int, float))]
                    if lat and abs(round(sum(lat) / len(lat), 2) - lm) > 0.01:
                        stale.append(f"aggregates.json {s}.latency_mean_s={lm} is an "
                                     "all-runs (incl. dead error runs) figure; ledger "
                                     f"all_runs={round(sum(lat)/len(lat),2)}, "
                                     "headline denominator is runs_with_output")
        except Exception as exc:
            stale.append(f"aggregates.json unparseable: {exc}")
    if ana_path.is_file():
        try:
            ana = _load(ana_path)
            if ana.get("baseline_comparison") is None:
                stale.append("aggregates/analyses.json baseline_comparison is null "
                             "(legacy artifact never populated)")
        except Exception as exc:
            stale.append(f"analyses.json unparseable: {exc}")
    legacy = pkg_dir / "task_ledger.json"
    if legacy.is_file():
        gen = str(ledger.get("generator") or "")
        if "tmp/" in gen:
            stale.append(f"canonical task_ledger.json was generated by a temporary "
                         f"forensic script ({gen}); rebuild with evaluation/build_ledger.py")
    if stale:
        errors.append(_fmt_errs("V09", stale)[0])

    # ---- cross-check canonical ledger against raw fields (fidelity) --------------------
    fid_errors = _fidelity_check(entries, raw_records)
    errors.extend(fid_errors)

    ok = not errors
    return {"ok": ok, "errors": errors, "warnings": warnings, "checks": checks,
            "n_raw": len(raw_records), "n_entries": len(entries), "systems": systems}


def _fidelity_check(entries: list, raw_records: list) -> list:
    """Every ledger outcome field must match the raw record it came from."""
    import build_ledger as BL
    errors = []
    raw_by_key = {(r.get("task_id"), r.get("system")): r for r in raw_records}
    for e in entries:
        r = raw_by_key.get((e["task_id"], e["system"]))
        if r is None:
            continue
        rebuilt = BL.build_entry(r)
        for field in ("final_resolved", "provider_failure", "FINAL_CLASSIFICATION",
                      "first_pass_resolved", "repair_eligible", "repair_recovered",
                      "localization_top1", "hidden_tests_passed", "llm_calls",
                      "total_tokens", "latency_seconds", "cost", "infrastructure_failure"):
            if e.get(field) != rebuilt.get(field):
                errors.append(f"V01: ledger/raw fidelity: {e['task_id']}/{e['system']} "
                              f"field {field}: ledger={e.get(field)!r} "
                              f"raw-recompute={rebuilt.get(field)!r}")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a canonical evaluation package.")
    ap.add_argument("--experiment", default=None)
    ap.add_argument("--ledger", default=None, help="package directory (alternative)")
    ap.add_argument("--expected-tasks", type=int, default=None)
    args = ap.parse_args()

    if args.experiment:
        pkg_dir = REPO_ROOT / "evaluation" / "results" / args.experiment
    elif args.ledger:
        pkg_dir = Path(args.ledger)
    else:
        ap.error("one of --experiment / --ledger is required")

    report = validate_package(pkg_dir, expected_task_count=args.expected_tasks)
    print(json.dumps(report if report["ok"] else
                     {"ok": report["ok"], "errors": report["errors"],
                      "warnings": report["warnings"], "n_entries": report["n_entries"]},
                     indent=2))
    print(f"[VALIDATE] {'OK' if report['ok'] else 'FAILED'} — "
          f"{len(report['errors'])} errors, {len(report['warnings'])} warnings")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
