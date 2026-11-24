"""
evaluation/analyze.py

Deeper, auditable analyses on top of metrics.py aggregation:
  1. Baseline comparison (multi_agent vs baseline_a / baseline_b) — absolute
     and relative improvement on the headline metrics.
  2. Retry analysis — Recovery Rate = (initially-failed that later succeed) /
     (initially-failed), with explicit numerator/denominator.
  3. Failure analysis — failure category | count | % of all | % of failures.
  4. Difficulty analysis — difficulty | N | success | success %.

Every percentage is reported with its denominator (X / N). No metric is
inferred or fabricated; everything is read from the raw result JSONs.

Usage:
    python evaluation/analyze.py --results-dir evaluation/results/<exp>/raw \
                                 --out evaluation/results/<exp>/aggregates
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Windows consoles often default to cp1252; force UTF-8 so Δ/· glyphs never crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from metrics import collect, load_task_meta, safe, agg_system, rate


def pct(x, n):
    return (100.0 * x / n) if n else 0.0


def _by_system(rows):
    d = defaultdict(list)
    for r in rows:
        d[r["system"]].append(r)
    return d


def baseline_comparison(rows):
    """multi_agent vs each single-agent baseline on headline metrics."""
    by_sys = _by_system(rows)
    systems = {name: agg_system(rs, load_task_meta()) for name, rs in by_sys.items()}
    primary = "multi_agent"
    if primary not in systems:
        return None
    out = {"primary": primary, "comparisons": []}
    for name in sorted(systems):
        if name == primary:
            continue
        p, b = systems[primary], systems[name]
        n_p, n_b = p.get("N", 0), b.get("N", 0)
        if not n_p or not n_b:
            continue
        rows_cmp = []
        for metric, label in [
            ("e2e_resolved", "End-to-end resolved"),
            ("first_pass_resolved", "First-pass resolved"),
            ("hidden_tests_passed", "Hidden tests passed"),
            ("localized", "Localized (top-1)"),
        ]:
            pv, bv = p.get(metric, 0), b.get(metric, 0)
            pn = n_p if metric != "localized" else p.get("loc_eligible", 0)
            bn = n_b if metric != "localized" else b.get("loc_eligible", 0)
            abs_pp = pct(pv, pn) - pct(bv, bn)
            rel = (abs_pp / pct(bv, bn)) if pct(bv, bn) else None
            rows_cmp.append({
                "metric": label,
                "primary": f"{pv}/{pn} = {pct(pv,pn):.1f}%",
                "baseline": f"{bv}/{bn} = {pct(bv,bn):.1f}%",
                "baseline_name": name,
                "abs_pp": round(abs_pp, 1),
                "rel_pct": round(rel, 1) if rel is not None else None,
            })
        out["comparisons"].append({"baseline": name, "rows": rows_cmp})
    return out


def retry_analysis(rows):
    """Recovery Rate per system: initially-failed that later succeed / initially-failed."""
    by_sys = _by_system(rows)
    out = {}
    for name, rs in sorted(by_sys.items()):
        n = len(rs)
        # initially failed = first attempt did NOT resolve
        initially_failed = [r for r in rs if safe(r, "repair", "first_attempt_success") is False]
        # of those, recovered = end-to-end resolved (via retry)
        recovered = [r for r in initially_failed if r.get("end_to_end_resolved") is True]
        # first-pass successes (for context)
        first_pass = [r for r in rs if safe(r, "repair", "first_attempt_success") is True]
        # tasks that used at least one retry
        used_retry = [r for r in rs if (safe(r, "repair", "attempts") or 1) > 1]
        denom = len(initially_failed)
        out[name] = {
            "N": n,
            "first_pass_success": len(first_pass),
            "initially_failed": denom,
            "recovered_via_retry": len(recovered),
            "recovery_rate": f"{len(recovered)}/{denom} = {pct(len(recovered), denom):.1f}%",
            "used_at_least_one_retry": len(used_retry),
            "retries_mean": round(sum((safe(r, "repair", "attempts") or 1) - 1 for r in rs) / n, 3) if n else 0,
        }
    return out


def failure_analysis(rows):
    """Failure category | count | % of all | % of failures (per system + overall)."""
    by_sys = _by_system(rows)
    out = {"overall": {}, "by_system": {}}

    def _table(rs):
        n = len(rs)
        failed = [r for r in rs if r.get("end_to_end_resolved") is not True]
        nf = len(failed)
        counts = defaultdict(int)
        for r in failed:
            # derive a stable failure category
            status = safe(r, "execution", "status") or "unknown"
            cat = safe(r, "execution", "failure_category")
            if cat:
                key = cat
            else:
                key = status
            counts[key] += 1
        table = []
        for key, c in sorted(counts.items(), key=lambda kv: -kv[1]):
            table.append({
                "category": key,
                "count": c,
                "pct_of_all": f"{c}/{n} = {pct(c, n):.1f}%",
                "pct_of_failures": f"{c}/{nf} = {pct(c, nf):.1f}%",
            })
        return {"N": n, "failures": nf, "rows": table}

    out["overall"] = _table(rows)
    for name, rs in sorted(by_sys.items()):
        out["by_system"][name] = _table(rs)
    return out


def difficulty_analysis(rows):
    """difficulty | N | success | success % (per system + overall)."""
    meta = load_task_meta()
    by_sys = _by_system(rows)
    order = ["easy", "medium", "hard"]

    def _table(rs):
        buckets = defaultdict(lambda: [0, 0])  # diff -> [success, N]
        for r in rs:
            diff = meta.get(r.get("task_id"), {}).get("difficulty", "unknown")
            buckets[diff][1] += 1
            if r.get("end_to_end_resolved") is True:
                buckets[diff][0] += 1
        table = []
        for diff in order + [d for d in buckets if d not in order]:
            if diff not in buckets:
                continue
            s, n = buckets[diff]
            table.append({"difficulty": diff, "N": n, "success": s,
                          "success_pct": f"{s}/{n} = {pct(s, n):.1f}%"})
        return table

    out = {"overall": _table(rows), "by_system": {}}
    for name, rs in sorted(by_sys.items()):
        out["by_system"][name] = _table(rs)
    return out


def main():
    parser = argparse.ArgumentParser(description="Deep benchmark analyses.")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = collect(results_dir)
    if not rows:
        print(f"[ERROR] No result JSONs in {results_dir}")
        return

    analyses = {
        "baseline_comparison": baseline_comparison(rows),
        "retry_analysis": retry_analysis(rows),
        "failure_analysis": failure_analysis(rows),
        "difficulty_analysis": difficulty_analysis(rows),
    }

    out_path = out_dir / "analyses.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(analyses, f, indent=2, default=str)

    # ---- Human-readable report ----
    lines = []
    lines.append("=" * 72)
    lines.append("ANALYSES  (%d result rows)" % len(rows))
    lines.append("=" * 72)

    bc = analyses["baseline_comparison"]
    if bc:
        lines.append("\n[1] BASELINE COMPARISON — %s vs single-agent baselines" % bc["primary"])
        for cmp in bc["comparisons"]:
            lines.append("\n  vs %s:" % cmp["baseline"])
            for row in cmp["rows"]:
                rel = ("(rel %+.1f%%)" % row["rel_pct"]) if row["rel_pct"] is not None else ""
                lines.append("    %-22s  primary %-22s  baseline %-22s  Δ%+.1fpp %s" % (
                    row["metric"], row["primary"], row["baseline"], row["abs_pp"], rel))

    lines.append("\n[2] RETRY ANALYSIS — Recovery Rate = initially-failed that later succeed / initially-failed")
    for name, a in analyses["retry_analysis"].items():
        lines.append("  %-14s N=%-3d first_pass=%-3d initially_failed=%-3d recovered=%-3d  recovery=%s  retries_mean=%.2f" % (
            name, a["N"], a["first_pass_success"], a["initially_failed"],
            a["recovered_via_retry"], a["recovery_rate"], a["retries_mean"]))

    lines.append("\n[3] FAILURE ANALYSIS — category | count | % of all | % of failures")
    for scope, tbl in [("OVERALL", analyses["failure_analysis"]["overall"])] + \
                      [(s, t) for s, t in analyses["failure_analysis"]["by_system"].items()]:
        lines.append("  %s (N=%d, failures=%d):" % (scope, tbl["N"], tbl["failures"]))
        for row in tbl["rows"]:
            lines.append("    %-28s %3d   %-16s %-16s" % (
                row["category"], row["count"], row["pct_of_all"], row["pct_of_failures"]))

    lines.append("\n[4] DIFFICULTY ANALYSIS — difficulty | N | success | success %")
    for scope, tbl in [("OVERALL", analyses["difficulty_analysis"]["overall"])] + \
                      [(s, t) for s, t in analyses["difficulty_analysis"]["by_system"].items()]:
        lines.append("  %s:" % scope)
        for row in tbl:
            lines.append("    %-8s N=%-3d success=%-3d  %s" % (
                row["difficulty"], row["N"], row["success"], row["success_pct"]))

    report = "\n".join(lines)
    print(report)
    report_path = out_dir / "analyses.txt"
    report_path.write_text(report + "\n", encoding="utf-8")
    print(f"\nWrote: {out_path}\nWrote: {report_path}")


if __name__ == "__main__":
    main()
