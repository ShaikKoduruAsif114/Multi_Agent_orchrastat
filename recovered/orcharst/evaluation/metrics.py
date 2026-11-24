"""
evaluation/metrics.py

Aggregates raw benchmark result JSONs into auditable summary artifacts.
Every percentage is reported with its denominator (X / N).

Usage:
    python evaluation/metrics.py --results-dir evaluation/results/<exp_id>/raw \
                                 --out evaluation/results/<exp_id>/aggregates
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_task_meta() -> dict:
    """task_id -> {category, difficulty, gold_file} from benchmark task JSONs."""
    meta = {}
    bench = REPO_ROOT / "evaluation" / "benchmark"
    for p in sorted(bench.glob("task_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            tid = d.get("task_id") or p.stem[:8]
            md = d.get("metadata", {}) or {}
            meta[tid] = {
                "category": d.get("category") or md.get("category") or "unknown",
                "difficulty": d.get("difficulty") or md.get("difficulty") or "unknown",
                "gold_file": d.get("gold_file"),
            }
        except Exception:
            continue
    return meta


def safe(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def pctl(values, q):
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * q
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def collect(results_dir: Path) -> list:
    rows = []
    for p in sorted(results_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and "task_id" in d and "system" in d:
            rows.append(d)
    return rows


def retries_of(r) -> int:
    a = safe(r, "repair", "attempts")
    if isinstance(a, (int, float)) and a >= 1:
        return int(a) - 1
    return 0


def failure_reason_of(r):
    for path in (("execution", "failure_category"), ("execution", "status"), ("execution", "error_message")):
        v = safe(r, *path)
        if v:
            return v
    return "unknown"


def agg_system(rows: list, meta: dict) -> dict:
    n = len(rows)
    if n == 0:
        return {"N": 0}

    def cnt(pred):
        return sum(1 for r in rows if pred(r))

    lat = [safe(r, "execution", "latency_seconds", default=0) or 0 for r in rows]
    llm = [x for x in (safe(r, "execution", "llm_calls") for r in rows) if isinstance(x, (int, float))]
    tools = [x for x in (safe(r, "execution", "tool_calls") for r in rows) if isinstance(x, (int, float))]
    retries = [retries_of(r) for r in rows]
    loc_eligible = sum(1 for r in rows if safe(r, "localization", "predicted_file") is not None)

    fail_counts = defaultdict(int)
    for r in rows:
        if r.get("end_to_end_resolved") is not True:
            fail_counts[str(failure_reason_of(r))] += 1

    return {
        "N": n,
        "e2e_resolved": cnt(lambda r: r.get("end_to_end_resolved") is True),
        "first_pass_resolved": cnt(
            lambda r: safe(r, "repair", "first_attempt_success") is True
            or (safe(r, "repair", "first_attempt_success") is None and r.get("end_to_end_resolved") is True)
        ),
        "hidden_tests_passed": cnt(lambda r: safe(r, "regression", "hidden_tests_passed") is True),
        "regression_free": cnt(lambda r: safe(r, "regression", "regression_free") is True),
        "patch_generated": cnt(lambda r: safe(r, "patch", "generated") is True),
        "patch_syntax_valid": cnt(lambda r: safe(r, "patch", "syntax_valid") is True),
        "patch_applied": cnt(lambda r: safe(r, "patch", "patch_apply_success") is True),
        "gen_tests_generated": cnt(lambda r: safe(r, "tests", "generated") is True),
        "gen_tests_passed": cnt(lambda r: safe(r, "tests", "generated_tests_passed") is True),
        "localized": cnt(lambda r: safe(r, "localization", "top1_correct") is True),
        "loc_eligible": loc_eligible,
        "hallucinated_file": cnt(lambda r: safe(r, "localization", "hallucinated_file") is True),
        "pr_created": cnt(lambda r: safe(r, "pr", "pr_created") is True),
        "retries_total": sum(retries),
        "retries_mean": round(statistics.mean(retries), 3) if retries else 0,
        "retries_median": statistics.median(retries) if retries else 0,
        "retries_p90": round(pctl(retries, 0.9), 3) if retries else 0,
        "llm_calls_mean": round(statistics.mean(llm), 3) if llm else None,
        "llm_calls_median": statistics.median(llm) if llm else None,
        "llm_calls_p90": round(pctl(llm, 0.9), 3) if llm else None,
        "llm_calls_N": len(llm),
        "tool_calls_mean": round(statistics.mean(tools), 3) if tools else None,
        "latency_mean_s": round(statistics.mean(lat), 2) if lat else None,
        "latency_median_s": round(statistics.median(lat), 2) if lat else None,
        "latency_p90_s": round(pctl(lat, 0.9), 2) if lat else None,
        "failure_reasons": dict(fail_counts),
    }


def rate(x, n):
    return f"{x}/{n} = {100.0 * x / n:.1f}%" if n else f"{x}/0 = n/a"


def main():
    parser = argparse.ArgumentParser(description="Aggregate raw benchmark results.")
    parser.add_argument("--results-dir", required=True, help="Path to <exp>/raw")
    parser.add_argument("--out", required=True, help="Path to <exp>/aggregates")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = collect(results_dir)
    meta = load_task_meta()
    if not rows:
        print(f"[ERROR] No result JSONs found in {results_dir}")
        return

    by_system = defaultdict(list)
    for r in rows:
        by_system[r["system"]].append(r)

    # Per-system aggregate
    systems = {}
    for sys_name in sorted(by_system):
        systems[sys_name] = agg_system(by_system[sys_name], meta)

    # CSV (one row per system)
    csv_path = out_dir / "aggregates.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = ["system", "N", "e2e_resolved", "first_pass_resolved",
                  "hidden_tests_passed", "regression_free", "localized", "loc_eligible",
                  "hallucinated_file", "retries_mean", "retries_p90",
                  "llm_calls_mean", "llm_calls_p90", "latency_mean_s", "latency_p90_s"]
        writer.writerow(header)
        for sys_name, a in systems.items():
            writer.writerow([
                sys_name, a.get("N"), a.get("e2e_resolved"), a.get("first_pass_resolved"),
                a.get("hidden_tests_passed"), a.get("regression_free"), a.get("localized"), a.get("loc_eligible"),
                a.get("hallucinated_file"), a.get("retries_mean"), a.get("retries_p90"),
                a.get("llm_calls_mean"), a.get("llm_calls_p90"), a.get("latency_mean_s"), a.get("latency_p90_s"),
            ])

    # JSON (full per-system aggregate incl. failure_reasons)
    json_path = out_dir / "aggregates.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"systems": systems, "meta": meta}, f, indent=2, default=str)

    # Human-readable summary
    print(f"\n{'='*70}\nAGGREGATES ({len(rows)} result rows, {len(systems)} systems)\n{'='*70}")
    for sys_name, a in systems.items():
        n = a.get("N", 0)
        print(f"\n[{sys_name}]  N={n}")
        print(f"  e2e_resolved:        {rate(a.get('e2e_resolved',0), n)}")
        print(f"  first_pass_resolved: {rate(a.get('first_pass_resolved',0), n)}")
        print(f"  hidden_tests_passed: {rate(a.get('hidden_tests_passed',0), n)}")
        print(f"  localized (top1):    {rate(a.get('localized',0), a.get('loc_eligible',0))}")
        print(f"  hallucinated_file:   {rate(a.get('hallucinated_file',0), n)}")
        print(f"  retries mean/p90:    {a.get('retries_mean')} / {a.get('retries_p90')}")
        print(f"  llm_calls mean/p90:  {a.get('llm_calls_mean')} / {a.get('llm_calls_p90')}")
        print(f"  latency mean/p90 s:  {a.get('latency_mean_s')} / {a.get('latency_p90_s')}")
        if a.get("failure_reasons"):
            print(f"  failure_reasons:     {a['failure_reasons']}")
    print(f"\nWrote: {csv_path}\nWrote: {json_path}")


if __name__ == "__main__":
    main()
