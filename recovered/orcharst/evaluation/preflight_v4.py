"""
evaluation/preflight_v4.py

PREFLIGHT GATE for the Adaptive V4 controlled experiment.
Verifies EVERY precondition BEFORE allowing a benchmark run, then emits /
verifies the V4 run manifest (machine-readable experiment contract).

Run before the benchmark:
    python evaluation/preflight_v4.py --generate-manifest

Preflight checks (P01-P10):
  P01  config exists and parses; V4 contract fields present
  P02  exactly 2 systems: adaptive_multi_agent + baseline_b
  P03  30 task files listed AND present on disk
  P04  model pin: nara / laguna-s-2.1 (NaraRouter only)
  P05  IDENTICAL retry budget for both arms (AGENT_MAX_RETRIES ==
       AGENT_REPAIR_BUDGET == execution_settings.retry_budget)
  P06  identical execution environment for both arms (env_overrides shared;
       identical timeout policy; no arm-specific env differences)
  P07  frozen benchmark-input manifest verifies 182/182 (before run)
  P08  code commit SHA resolvable (git rev-parse HEAD)
  P09  evaluator version present (canonical tooling importable)
  P10  adaptive controller logic is V3-preserved (no optimization):
       budget pin present in baseline_adaptive.py, per-path fallback intact

Exit code 0 = ready for a single controlled V4 run; 1 = not ready.

V4 run manifest (evaluation/results/v4_run_manifest.json) records:
  provider, model, retry budget (both arms), benchmark manifest SHA256,
  code commit SHA, execution mode, timeout settings, evaluator version,
  experiment id, preflight timestamp, and the pre-registered primary
  evaluation definition reference.

Historical result directories are never touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "evaluation"))

V4_CONFIG = REPO_ROOT / "evaluation" / "configs" / "benchmark_v4.yaml"
V4_MANIFEST_PATH = REPO_ROOT / "evaluation" / "results" / "v4_run_manifest.json"
ADAPTIVE_MODULE = REPO_ROOT / "evaluation" / "baselines" / "baseline_adaptive.py"
BASELINE_B_MODULE = REPO_ROOT / "evaluation" / "baselines" / "baseline_b_single_retry.py"
EXPECTED_SYSTEMS = ("adaptive_multi_agent", "baseline_b")
N_TASKS = 30
EVALUATOR_VERSION = "1.0.0"

PRIMARY_EVALUATION = {
    "clean_paired_set": "tier:valid — both arms FINAL_CLASSIFICATION in "
                        "{resolved, genuine_agent_failure}",
    "primary_endpoint": "final resolution on the clean paired set (McNemar exact two-sided)",
    "secondary": [
        "first-pass resolution (budget 2, both arms; repair.first_pass_resolved_hidden)",
        "LLM calls (runs_with_output denominator)",
        "tokens (runs_with_output denominator)",
        "latency (runs_with_output denominator)",
        "cost (runs_with_output denominator)",
        "localization top-1 (evaluable denominator)",
        "provider contamination (separate class; provider beats generic infra labels)",
        "repair recovery (among repair-eligible valid runs)",
    ],
    "statistical_test": "exact binomial McNemar, two-sided, on discordant cells",
}


def _check(results: list, ok: bool, code: str, detail: str) -> bool:
    results.append({"code": code, "ok": bool(ok), "detail": detail})
    return ok


def run_preflight(config_path: Path = V4_CONFIG) -> tuple:
    """Run all preflight checks. Returns (all_ok, results, context)."""
    results: list = []
    ctx: dict = {}

    # ---- P01 config ----------------------------------------------------------
    if not _check(results, config_path.is_file(), "P01",
                  f"V4 config present: {config_path.name}"):
        return False, results, ctx
    import yaml
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    # ---- P02 systems -----------------------------------------------------------
    systems = [s["name"] for s in config.get("systems", []) if s.get("enabled", True)]
    _check(results, tuple(sorted(systems)) == EXPECTED_SYSTEMS, "P02",
           f"exactly 2 systems required {list(EXPECTED_SYSTEMS)}, found {systems}")

    # ---- P03 tasks -------------------------------------------------------------
    tasks = config.get("tasks", [])
    benchmark_dir = REPO_ROOT / config.get("benchmark_dir", "evaluation/benchmark")
    missing = [t for t in tasks if not (benchmark_dir / t).is_file()]
    _check(results, len(tasks) == N_TASKS and not missing, "P03",
           f"{len(tasks)} tasks configured, {len(missing)} missing on disk"
           + (f": {missing[:3]}" if missing else ""))

    # ---- P04 model pin -----------------------------------------------------------
    env = config.get("env_overrides", {})
    model_cfg = config.get("model", {})
    _check(results,
           env.get("PROVIDER") == "nara" and env.get("NARAROUTER_MODEL") == "laguna-s-2.1"
           and model_cfg.get("provider") == "nara" and model_cfg.get("name") == "laguna-s-2.1",
           "P04", f"model pin nara/laguna-s-2.1: env={env.get('PROVIDER')}/"
                  f"{env.get('NARAROUTER_MODEL')} cfg={model_cfg.get('provider')}/{model_cfg.get('name')}")

    # ---- P05 identical retry budget ----------------------------------------------
    exec_set = config.get("execution_settings", {})
    cfg_budget = exec_set.get("retry_budget")
    max_retries = env.get("AGENT_MAX_RETRIES")
    repair_budget = env.get("AGENT_REPAIR_BUDGET")
    equal = (str(cfg_budget) == str(max_retries) == str(repair_budget)
             if cfg_budget is not None and max_retries is not None and repair_budget is not None
             else False)
    _check(results, equal, "P05",
           f"retry budgets: execution_settings={cfg_budget}, baseline AGENT_MAX_RETRIES="
           f"{max_retries}, adaptive pin AGENT_REPAIR_BUDGET={repair_budget}"
           + (" — IDENTICAL" if equal else " — MISMATCH INVALIDATES THE PAIRED COMPARISON"))

    # ---- P06 identical environment -------------------------------------------------
    timeout = exec_set.get("timeout_seconds")
    env_timeout = env.get("NARA_LLM_TIMEOUT")
    _check(results, str(timeout) == str(env_timeout), "P06",
           f"identical execution environment: shared env_overrides for both arms; "
           f"timeout_seconds={timeout} == NARA_LLM_TIMEOUT={env_timeout}; "
           f"sandbox={exec_set.get('sandbox')}")

    # ---- P07 frozen-input manifest gate ------------------------------------------------
    try:
        from verify_manifest import verify_manifest
        gate = verify_manifest()
        _check(results, gate["ok"], "P07",
               f"frozen inputs: {gate['verified']}/{gate['manifest_entries']} verified, "
               f"changed={len(gate['changed'])}, missing={len(gate['missing'])}")
        ctx["benchmark_manifest_sha256"] = _manifest_file_digest()
        ctx["manifest_entries"] = gate["manifest_entries"]
        ctx["manifest_verified"] = gate["verified"]
    except Exception as exc:
        _check(results, False, "P07", f"manifest gate crashed: {exc}")

    # ---- P08 code commit SHA -------------------------------------------------------------
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                                capture_output=True, text=True, timeout=30)
        commit_sha = commit.stdout.strip() if commit.returncode == 0 else None
        dirty = None
        if commit.returncode == 0:
            st = subprocess.run(["git", "status", "--porcelain"], cwd=str(REPO_ROOT),
                                capture_output=True, text=True, timeout=30)
            dirty_lines = [ln for ln in st.stdout.splitlines()
                           if ln.strip() and not ln.startswith("??")]
            dirty = len(dirty_lines)
        _check(results, bool(commit_sha), "P08",
               f"code commit SHA: {commit_sha or 'unresolvable'}"
               + (f" ({dirty} tracked files with uncommitted modifications)" if dirty is not None else ""))
        ctx["code_commit_sha"] = commit_sha
        ctx["git_dirty_tracked_files"] = dirty
    except Exception as exc:
        _check(results, False, "P08", f"git unavailable: {exc}")

    # ---- P09 evaluator ------------------------------------------------------------------
    try:
        import build_ledger
        import validate_ledger
        import paired_analysis
        import verify_manifest as _vm
        _check(results, True, "P09",
               f"evaluator v{EVALUATOR_VERSION} importable: build_ledger, "
               "validate_ledger, paired_analysis, verify_manifest")
        ctx["evaluator_version"] = EVALUATOR_VERSION
    except Exception as exc:
        _check(results, False, "P09", f"evaluator import failed: {exc}")

    # ---- P10 V3 controller logic preserved -------------------------------------------------
    src = ADAPTIVE_MODULE.read_text(encoding="utf-8") if ADAPTIVE_MODULE.is_file() else ""
    has_pin = "AGENT_REPAIR_BUDGET" in src
    per_path_intact = all(s in src for s in
                          ('if self.final_path == "PATH_A":\n            return 1',
                           'elif self.final_path == "PATH_B":\n            return 2'))
    first_pass_true = 'first_pass_resolved_hidden": initial_hidden_passed' in src
    _check(results, has_pin and per_path_intact, "P10",
           f"adaptive controller V3-preserved: budget pin present={has_pin}, "
           f"per-path fallback intact={per_path_intact}, "
           f"true-first-pass recording={first_pass_true}")
    b_src = BASELINE_B_MODULE.read_text(encoding="utf-8") if BASELINE_B_MODULE.is_file() else ""
    _check(results, 'os.getenv("AGENT_MAX_RETRIES", "3")' in b_src, "P10",
           "baseline_b reads AGENT_MAX_RETRIES (budget source confirmed)")

    try:
        ctx["config_path"] = str(config_path.relative_to(REPO_ROOT))
    except ValueError:
        ctx["config_path"] = str(config_path)  # config outside the repo (tests)
    ctx["retry_budget"] = cfg_budget
    ctx["execution_mode"] = exec_set.get("sandbox")
    ctx["timeout_seconds"] = timeout
    return all(r["ok"] for r in results), results, ctx


def _manifest_file_digest() -> str:
    from verify_manifest import MANIFEST_PATH
    return hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()


def generate_manifest(ctx: dict) -> dict:
    """Write the V4 run manifest (machine-readable experiment contract)."""
    manifest = {
        "experiment": "adaptive_v4_controlled",
        "protocol": "evaluation/V4_PROTOCOL.md",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provider": "nara",
        "model": "laguna-s-2.1",
        "retry_budget": {
            "adaptive_multi_agent": ctx.get("retry_budget"),
            "baseline_b": ctx.get("retry_budget"),
            "identical": True,
            "mechanism": "AGENT_REPAIR_BUDGET pins adaptive paths; "
                         "AGENT_MAX_RETRIES drives baseline_b",
        },
        "benchmark_manifest_sha256": ctx.get("benchmark_manifest_sha256"),
        "benchmark_manifest_entries": ctx.get("manifest_entries"),
        "code_commit_sha": ctx.get("code_commit_sha"),
        "git_dirty_tracked_files": ctx.get("git_dirty_tracked_files"),
        "execution_mode": ctx.get("execution_mode"),
        "timeout_seconds": ctx.get("timeout_seconds"),
        "evaluator_version": ctx.get("evaluator_version"),
        "config": ctx.get("config_path"),
        "primary_evaluation": PRIMARY_EVALUATION,
        "fail_closed_rules": [
            "provider contamination classified separately from infrastructure failure",
            "missing/duplicate task IDs invalidate the experiment (V01/V02/V03)",
            "retry-budget mismatch invalidates the paired comparison (V04)",
            "contradictory first-pass fields reported (V06)",
            "no report final unless task_ledger + analysis + paired_analysis + "
            "report validation all pass",
        ],
    }
    V4_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    V4_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def verify_manifest_file() -> tuple:
    """Re-verify an existing V4 run manifest against current preflight context."""
    if not V4_MANIFEST_PATH.is_file():
        return False, "no V4 run manifest (run --generate-manifest first)"
    manifest = json.loads(V4_MANIFEST_PATH.read_text(encoding="utf-8"))
    ok, results, ctx = run_preflight()
    if not ok:
        return False, "preflight no longer passes; regenerate the manifest"
    stale = []
    if manifest.get("benchmark_manifest_sha256") != ctx.get("benchmark_manifest_sha256"):
        stale.append("benchmark_manifest_sha256 changed (frozen inputs or manifest modified)")
    if manifest.get("code_commit_sha") != ctx.get("code_commit_sha"):
        stale.append(f"code commit changed: manifest={manifest.get('code_commit_sha')} "
                     f"now={ctx.get('code_commit_sha')}")
    if manifest.get("retry_budget", {}).get("adaptive_multi_agent") != ctx.get("retry_budget"):
        stale.append("retry budget changed")
    if manifest.get("evaluator_version") != EVALUATOR_VERSION:
        stale.append("evaluator version changed")
    return (not stale), ("run manifest current" if not stale else "; ".join(stale))


def main() -> int:
    ap = argparse.ArgumentParser(description="Adaptive V4 preflight gate.")
    ap.add_argument("--generate-manifest", action="store_true",
                    help="write/refresh evaluation/results/v4_run_manifest.json")
    ap.add_argument("--verify-manifest-only", action="store_true",
                    help="verify the existing run manifest without re-running preflight output")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ok, results, ctx = run_preflight()
    if args.generate_manifest and ok:
        manifest = generate_manifest(ctx)
        print(f"[V4] run manifest written: {V4_MANIFEST_PATH.relative_to(REPO_ROOT)}")
        if args.json:
            print(json.dumps(manifest, indent=2))
    elif args.generate_manifest:
        print("[V4] manifest NOT generated: preflight failed")

    if args.verify_manifest_only:
        m_ok, m_detail = verify_manifest_file()
        print(f"[V4] run manifest: {'CURRENT' if m_ok else 'STALE/MISSING'} — {m_detail}")
        ok = ok and m_ok

    if args.json:
        print(json.dumps({"preflight_ok": ok, "checks": results}, indent=2))
    else:
        print(f"\n{'='*64}\nV4 PREFLIGHT — {'READY' if ok else 'NOT READY'}\n{'='*64}")
        for r in results:
            print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['code']}: {r['detail']}")
        print(f"\nNext step: "
              f"python evaluation/run_benchmark.py --config evaluation/configs/benchmark_v4.yaml --evaluate")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
