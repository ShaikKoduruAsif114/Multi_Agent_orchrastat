#!/usr/bin/env python3
"""Final probes: baseline error classification, PATH_A/B stats, leftover dirs."""
import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "evaluation" / "results" / "nara_laguna_adaptive_v3_final_20260910"
TASK_IDS = [f"task_{i:03d}" for i in range(1, 31)]


def raw(t, s):
    return json.load(open(EXP / "raw" / f"{t}_{s}.json", encoding="utf-8"))


print("== baseline_b error runs: provider vs infra? ==")
for t in TASK_IDS:
    r = raw(t, "baseline_b")
    ex = r["execution"]
    if ex.get("status") == "error":
        print(f"{t}: failcat={ex.get('failure_category')} lat={ex.get('latency_seconds')} calls={ex.get('llm_calls')}")
        print(f"   err={(ex.get('error_message') or '')[:220]}")

print("\n== adaptive path-level stats ==")
for path in ("PATH_A", "PATH_B"):
    ts = [t for t in TASK_IDS if (raw(t, "adaptive_multi_agent").get("adaptive") or {}).get("initial_path") == path]
    e2e = sum(1 for t in ts if raw(t, "adaptive_multi_agent")["end_to_end_resolved"])
    fpA = sum(1 for t in ts if (raw(t, "adaptive_multi_agent").get("adaptive") or {}).get("first_pass_resolved") is True)
    calls = [raw(t, "adaptive_multi_agent")["execution"]["llm_calls"] for t in ts if raw(t, "adaptive_multi_agent")["execution"].get("llm_calls")]
    tok = [raw(t, "adaptive_multi_agent")["execution"]["total_tokens"] for t in ts if raw(t, "adaptive_multi_agent")["execution"].get("total_tokens")]
    lat = [raw(t, "adaptive_multi_agent")["execution"]["latency_seconds"] for t in ts if raw(t, "adaptive_multi_agent")["execution"].get("latency_seconds") and raw(t, "adaptive_multi_agent")["execution"]["status"] != "error"]
    print(f"{path}: n={len(ts)} resolved={e2e}/{len(ts)} fpA={fpA}/{len(ts)} calls_mean={statistics.mean(calls):.2f} "
          f"tok_mean={statistics.mean(tok):.0f} lat_mean_valid={statistics.mean(lat):.1f}")

print("\n== subdirectory contents ==")
for d in ("ablations", "baselines", "failures", "reports", "charts"):
    p = EXP / d
    if p.exists():
        items = sorted(x.name for x in p.rglob("*") if x.is_file())
        print(f"{d}/: {len(items)} files -> {items[:12]}")
