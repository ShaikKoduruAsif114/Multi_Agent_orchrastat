"""
evaluation/run_benchmark.py

Main benchmark entry point. Runs all configured systems against all tasks
and collects real, machine-readable results.

Usage:
    python evaluation/run_benchmark.py --config evaluation/configs/benchmark.yaml
    python evaluation/run_benchmark.py --config evaluation/configs/benchmark.yaml --system baseline_a
    python evaluation/run_benchmark.py --config evaluation/configs/benchmark.yaml --task task_001_calculator.json
    python evaluation/run_benchmark.py --smoke  # Run only task_001 with all systems
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import traceback
from pathlib import Path

# Windows consoles often default to cp1252; force UTF-8 so result output
# containing any unicode never crashes the run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)

# Project root
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "github-issue-agent"))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / "github-issue-agent" / ".env")

# Fixture routing: benchmark repos exist only locally under
# evaluation/benchmark/fixture_repos/. Install the task-aware resolver into
# the production agent's tools so research/localization hit real fixtures.
sys.path.insert(0, str(REPO_ROOT / "evaluation"))
from fixture_router import install_agent_resolver, set_current_task  # noqa: E402

_RESOLVER_INSTALLED = install_agent_resolver()
if not _RESOLVER_INSTALLED:
    print("[WARN] fixture resolver NOT installed — agent would hit GitHub for fixture repos")


def load_config(config_path: str) -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def load_task(task_path: Path) -> dict:
    with open(task_path, "r") as f:
        return json.load(f)


def load_system_module(module_path: str):
    """Dynamically load a baseline/system module."""
    full_path = REPO_ROOT / module_path
    spec = importlib.util.spec_from_file_location("system_module", full_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def purge_agent_modules():
    """Force a fresh import of the agent package.

    Needed for ablations that change env vars read at import time (e.g.
    AGENT_MAX_RETRIES in agent.edges). Without this, the cached module keeps
    the value from the first import.
    """
    for name in list(sys.modules):
        if name == "agent" or name.startswith("agent."):
            del sys.modules[name]


# Mutable single-element holder so nested functions in this module can reach the
# lifecycle module reference after run_benchmark() configures it.
lc_local: list = [None]


def run_single_system_task(system: dict, task: dict, results_dir: Path,
                           env_overrides: dict = None, *, lifecycle=None) -> dict:
    """Run one system against one task. Returns the result dict.

    If ``lifecycle`` is provided, it must be a callable ``(exp_dir, raw_dir) -> None``
    used to record durable-result completion for the lifecycle state machine.
    """
    system_name = system["name"]
    task_id = task["task_id"]
    out_path = results_dir / f"{task_id}_{system_name}.json"

    # Skip if already completed (resume support)
    if out_path.exists():
        print(f"  [SKIP] {task_id} × {system_name} — result already exists at {out_path}")
        with open(out_path) as f:
            return json.load(f)

    set_current_task(task_id)

    old_env = {}
    task_env = dict(env_overrides or {})
    if system_name == "multi_agent":
        # V2 is part of this experiment definition, not a shell-side toggle.
        # Set it before loading baseline_c, which imports the LangGraph app.
        task_env["AGENT_LOCALIZATION_V2"] = "1"
    if task_env:
        for k, v in task_env.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = str(v)

    print(f"\n{'='*60}")
    print(f"  Running: {system_name} × {task_id}")
    print(f"{'='*60}")
    if system_name == "multi_agent":
        print(f"[V2 localization enabled] AGENT_LOCALIZATION_V2={os.environ.get('AGENT_LOCALIZATION_V2')}")
        print(f"[EVAL CONFIG] NARAROUTER_MODEL={os.environ.get('NARAROUTER_MODEL')} eval_mode=True strict={os.environ.get('AGENT_STRICT_LLM')}")

    start = time.monotonic()
    result = None
    error = None

    try:
        mod = load_system_module(system["module"])
        result = mod.run_task(task)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        error = traceback.format_exc()
        print(f"[ERROR] {system_name} × {task_id}: {e}")
        print(error)
        result = {
            "task_id": task_id,
            "system": system_name,
            "repository": task.get("repository", ""),
            "issue_title": task.get("issue_title", ""),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "end_to_end_resolved": False,
            "execution": {
                "status": "error",
                "failure_category": "benchmark_runner_error",
                "latency_seconds": round(time.monotonic() - start, 3),
                "llm_calls": None,
                "input_tokens": None,
                "output_tokens": None,
                "error_message": str(e),
            },
            "localization": {"predicted_file": None, "gold_file": task.get("gold_file"), "top1_correct": None},
            "patch": {"generated": False, "syntax_valid": None},
            "tests": {"generated": False, "generated_tests_passed": None},
            "regression": {"hidden_tests_passed": None, "regression_free": None},
            "repair": {"attempts": None, "first_attempt_success": None, "resolved_within_retry_budget": False},
            "cost": {"estimated_usd": None},
            "pr": {"branch_created": False, "commit_created": False, "pr_created": False},
        }
    finally:
        # Restore any env vars we overrode (e.g. AGENT_MAX_RETRIES for ablations)
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # Save result
    results_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  Saved -> {out_path}")

    # Fail-closed lifecycle: mark this raw result as durably written.
    if lifecycle is not None:
        lifecycle(exp_dir=results_dir.parent.parent, raw_dir=results_dir)

    # Print brief summary
    resolved = result.get("end_to_end_resolved", False)
    latency = result.get("execution", {}).get("latency_seconds", "?")
    cost = result.get("cost", {}).get("estimated_usd", "?")
    status = result.get("execution", {}).get("status", "?")
    print(f"  Status: {status} | Resolved: {resolved} | Latency: {latency}s | Cost: ${cost}")

    return result



def get_experiment_id() -> str:
    """Unique, non-resumable experiment directory identifier."""
    return os.environ.get(
        "EXPERIMENT_ID",
        "exp_%s_full30" % time.strftime("%Y%m%d_%H%M%S"),
    )


def _v4_arm_system_module(config: dict, arm_system: str) -> dict:
    """Return the single enabled config system entry whose name matches the
    requested V4 arm. V4 arm executions run exactly ONE system per experiment
    directory so the outer 600s wrapper can schedule the two arms as two
    independent 30-task packages."""
    systems = [s for s in config["systems"] if s.get("enabled", True)]
    matches = [s for s in systems if s["name"] == arm_system]
    if len(matches) != 1:
        print(f"[ERROR] V4 arm '{arm_system}' not uniquely found among enabled systems:"
              f" {[s['name'] for s in matches]} (config systems: {[s['name'] for s in systems]})")
        sys.exit(1)
    return matches[0]


def _v4_arm_env_overrides(config: dict, arm_system: str) -> dict:
    """V4 arms share the exact same env_overrides as the full run. No
    arm-specific overrides are permitted; the config is the single source of
    truth for provider/model/retry budget/temperature/hidden tests."""
    return dict(config.get("env_overrides", {}) or {})


def run_v4_arm(config: dict, arm_system: str, *, lifecycle=None, config_path=None):
    """Run ONE V4 arm as a standalone 30-task package.

    This is the execution-scheduling path added for V4. It runs the exact same
    benchmark_v4.yaml, the same 30 frozen tasks, the same provider/model,
    the same retry budget, and the same hidden tests as the two-arm run; the
    only difference is scheduling — one arm per experiment directory so the two
    arms can be executed independently under the 600s outer wrapper.

    The resulting directory is a COMPLETE lifecycle state ONLY after all 30
    raw results for that arm are durably written and the post-arm evaluation
    pipeline has validated the single-arm package.

    IMPORTANT: this does not change any treatment, config, provider, model,
    temperature, hidden-test set, retry budget, or evaluation definition. It
    only splits execution into two independently validated packages.
    """
    system = _v4_arm_system_module(config, arm_system)
    benchmark_dir = REPO_ROOT / config["benchmark_dir"]
    experiment_id = get_experiment_id()
    exp_dir = REPO_ROOT / config["results_dir"] / experiment_id
    results_dir = exp_dir / "raw"

    for sub in ("aggregates", "baselines", "ablations", "failures", "reports", "charts"):
        (exp_dir / sub).mkdir(parents=True, exist_ok=True)

    provider = os.getenv("PROVIDER", "nara").strip().lower() or "nara"
    if provider != "nara":
        print(f"[ERROR] Unsupported PROVIDER {provider!r}; only 'nara' (NaraRouter) is supported.")
        sys.exit(1)
    model_name = os.getenv("NARAROUTER_MODEL", "laguna-s-2.1").strip() or "laguna-s-2.1"

    lc = lifecycle or _import_lifecycle()

    # Fail-closed: refuse to silently resume/overwrite a stale directory.
    lc.init_lifecycle(
        exp_dir,
        config_path=config_path or REPO_ROOT / "evaluation" / "configs" / "benchmark_v4.yaml",
        benchmark_manifest_sha="filled-by-caller",
        commit_sha="filled-by-caller",
        provider=provider,
        model=model_name,
    )

    print(f"[V4 ARM] id={experiment_id}  arm={arm_system}  raw={results_dir}")
    print(f"[V4 ARM] provider={provider}  model={model_name}")

    os.environ["NARAROUTER_MODEL"] = model_name

    env_overrides = _v4_arm_env_overrides(config, arm_system)
    if env_overrides:
        print(f"[V4 ARM] env_overrides={len(env_overrides)} variables from config")
        for k, v in env_overrides.items():
            if k not in ("PROVIDER", "NARAROUTER_MODEL", "NARAROUTER_BASE_URL"):
                os.environ[k] = str(v)

    # Load all 30 frozen tasks (the same task set as the full run).
    task_files = config["tasks"]
    tasks = []
    for tf in task_files:
        task_path = benchmark_dir / tf
        if not task_path.exists():
            print(f"[WARN] Task file not found: {task_path}")
            continue
        tasks.append(load_task(task_path))

    if not tasks:
        print("[ERROR] No tasks loaded. Check benchmark_dir and task file names.")
        sys.exit(1)
    if len(tasks) != 30:
        print(f"[ERROR] V4 arm requires exactly 30 frozen tasks, found {len(tasks)}."
              " The arm package cannot be declared COMPLETE with a partial task set.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"V4 ARM: {arm_system} × {len(tasks)} tasks = {len(tasks)} runs")
    print(f"{'='*60}")
    print(f"  System: {system['name']} — {system['description']}")
    for t in tasks:
        print(f"  Task:   {t['task_id']} — {t['issue_title'][:60]}")

    all_results = []
    completed = 0
    failed = 0
    benchmark_start = time.monotonic()

    def on_raw_result_written(*, exp_dir, raw_dir):
        if lc is not None:
            lc.write_status(exp_dir, lc.IN_PROGRESS, force=True)

    for task in tasks:
        result = run_single_system_task(
            system, task, results_dir,
            env_overrides=env_overrides,
            lifecycle=on_raw_result_written,
        )
        all_results.append(result)
        completed += 1
        if not result.get("end_to_end_resolved"):
            failed += 1
        print(f"  Progress: {completed}/{len(tasks)}")

    benchmark_elapsed = round(time.monotonic() - benchmark_start, 1)

    print(f"\n{'='*60}")
    print(f"V4 ARM COMPLETE")
    print(f"{'='*60}")
    print(f"  Arm:            {arm_system}")
    print(f"  Total runs:     {completed}")
    print(f"  Resolved:       {completed - failed}/{completed}")
    print(f"  Failed:         {failed}/{completed}")
    print(f"  Total time:     {benchmark_elapsed}s")
    print(f"  Results dir:    {results_dir}")

    if lc is not None:
        lc.write_status(exp_dir, lc.IN_PROGRESS, force=True)

    return all_results


def _import_lifecycle():
    import lifecycle as L  # noqa: F811
    return L


def run_benchmark(config: dict, filter_system: str = None, filter_task: str = None,
                  smoke: bool = False, *, lifecycle=None, config_path=None):
    """Run the full benchmark.

    If ``lifecycle`` is provided it must be a module exposing
    ``init_lifecycle``, ``classify_state``, and ``finalize_experiment``.
    """
    benchmark_dir = REPO_ROOT / config["benchmark_dir"]
    experiment_id = get_experiment_id()
    exp_dir = REPO_ROOT / config["results_dir"] / experiment_id
    results_dir = exp_dir / "raw"

    # Create subdirectories (empty dirs only).
    for sub in ("aggregates", "baselines", "ablations", "failures", "reports", "charts"):
        (exp_dir / sub).mkdir(parents=True, exist_ok=True)

    # Single provider/model for every evaluated system (controlled benchmark):
    # NaraRouter + $NARAROUTER_MODEL (default laguna-s-2.1). Any other value of
    # PROVIDER is rejected by agent.provider.provider_name().
    provider = os.getenv("PROVIDER", "nara").strip().lower() or "nara"
    if provider != "nara":
        print(f"[ERROR] Unsupported PROVIDER {provider!r}; only 'nara' (NaraRouter) is supported.")
        sys.exit(1)
    model_name = os.getenv("NARAROUTER_MODEL", "laguna-s-2.1").strip() or "laguna-s-2.1"

    lc_local[0] = lifecycle or _import_lifecycle()
    lc = lc_local[0]

    # Fail-closed lifecycle: refuse to silently resume/overwrite a stale directory.
    lc.init_lifecycle(exp_dir, config_path=config_path or Path('evaluation/configs/benchmark_v4.yaml'),
                       benchmark_manifest_sha="filled-by-caller",
                       commit_sha="filled-by-caller",
                       provider=provider,
                       model=model_name)

    print(f"[EXPERIMENT] id={experiment_id}  raw={results_dir}")

    # Single provider/model for every evaluated system (controlled benchmark):
    # NaraRouter + $NARAROUTER_MODEL (default laguna-s-2.1). Any other value of
    # PROVIDER is rejected by agent.provider.provider_name().
    provider = os.getenv("PROVIDER", "nara").strip().lower() or "nara"
    if provider != "nara":
        print(f"[ERROR] Unsupported PROVIDER {provider!r}; only 'nara' (NaraRouter) is supported.")
        sys.exit(1)
    model_name = os.getenv("NARAROUTER_MODEL", "laguna-s-2.1").strip() or "laguna-s-2.1"
    os.environ["NARAROUTER_MODEL"] = model_name
    print(f"[PROVIDER] {provider}")
    print(f"[MODEL] {model_name}")
    print(f"[BASE URL] {os.getenv('NARAROUTER_BASE_URL', '').strip()}")
    
    # Apply config-level env overrides
    env_overrides = config.get("env_overrides", {})
    if env_overrides:
        print(f"[ENV OVERRIDES] {len(env_overrides)} variables set from config")
        for k, v in env_overrides.items():
            if k not in ("PROVIDER", "NARAROUTER_MODEL", "NARAROUTER_BASE_URL"):
                os.environ[k] = str(v)

    # Load tasks
    task_files = config["tasks"]
    if smoke:
        task_files = task_files[:1]
        print("[SMOKE MODE] Running only first task.")
    if filter_task:
        task_files = [t for t in task_files if filter_task in t]

    tasks = []
    for tf in task_files:
        task_path = benchmark_dir / tf
        if not task_path.exists():
            print(f"[WARN] Task file not found: {task_path}")
            continue
        tasks.append(load_task(task_path))

    if not tasks:
        print("[ERROR] No tasks loaded. Check benchmark_dir and task file names.")
        sys.exit(1)

    # Load systems
    systems = [s for s in config["systems"] if s.get("enabled", True)]
    if filter_system:
        systems = [s for s in systems if s["name"] == filter_system]

    if not systems:
        print("[ERROR] No systems selected.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"BENCHMARK: {len(tasks)} task(s) × {len(systems)} system(s) = {len(tasks)*len(systems)} runs")
    print(f"{'='*60}")
    for s in systems:
        print(f"  System: {s['name']} — {s['description']}")
    for t in tasks:
        print(f"  Task:   {t['task_id']} — {t['issue_title'][:60]}")

    # Run
    all_results = []
    total_runs = len(tasks) * len(systems)
    completed = 0
    failed = 0

    benchmark_start = time.monotonic()

    # Inline lifecycle callback: durable raw-result bookkeeping only.
    def on_raw_result_written(*, exp_dir, raw_dir):
        if lc is not None:
            lc.write_status(exp_dir, lc.IN_PROGRESS, force=True)

    for system in systems:
        for task in tasks:
            result = run_single_system_task(system, task, results_dir,
                                             env_overrides=env_overrides,
                                             lifecycle=on_raw_result_written)
            all_results.append(result)
            completed += 1
            if not result.get("end_to_end_resolved"):
                failed += 1
            print(f"  Progress: {completed}/{total_runs}")

    benchmark_elapsed = round(time.monotonic() - benchmark_start, 1)

    # Print aggregate summary
    print(f"\n{'='*60}")
    print("BENCHMARK COMPLETE")
    print(f"{'='*60}")
    print(f"  Total runs:     {completed}")
    print(f"  Resolved:       {completed - failed}/{completed}")
    print(f"  Failed:         {failed}/{completed}")
    print(f"  Total time:     {benchmark_elapsed}s")
    print(f"  Results dir:    {results_dir}")
    print(f"\nRun metrics: python evaluation/metrics.py")

    # After durable raw results are written, refresh the lifecycle status to
    # reflect the final durable raw result count (still IN_PROGRESS until
    # evaluation finalizes it).
    lc = lc_local[0] if isinstance(lc_local, list) else None
    if lc is not None:
        lc.write_status(exp_dir, lc.IN_PROGRESS, force=True)

    return all_results


def run_ablations(config: dict, experiment_id: str, filter_task: str = None, smoke: bool = False):
    """Run configured ablations (e.g. multi-agent with retry_budget=0).

    Each ablation reuses the multi-agent pipeline module but overrides the
    retry budget via AGENT_MAX_RETRIES and forces a fresh agent import so the
    graph's edges re-read the value. Results are written to
    <exp>/ablations/<ablation_name>/ with the ablation name as the system tag.
    """
    ablations = [a for a in config.get("ablations", []) if a.get("enabled", True)]
    if not ablations:
        print("[ABLATIONS] None enabled.")
        return []

    # The ablation targets the multi-agent pipeline.
    multi = next((s for s in config["systems"] if s["name"] == "multi_agent"), None)
    if multi is None:
        print("[ABLATIONS] No multi_agent system found; skipping ablations.")
        return []

    benchmark_dir = REPO_ROOT / config["benchmark_dir"]
    task_files = config["tasks"]
    if smoke:
        task_files = task_files[:1]
    if filter_task:
        task_files = [t for t in task_files if filter_task in t]

    tasks = []
    for tf in task_files:
        tp = benchmark_dir / tf
        if not tp.exists():
            print(f"[WARN] Task file not found: {tp}")
            continue
        tasks.append(load_task(tp))
    if not tasks:
        print("[ABLATIONS] No tasks loaded.")
        return []

    all_results = []
    for abl in ablations:
        abl_name = abl["name"]
        retry_budget = abl.get("retry_budget", 0)
        abl_dir = REPO_ROOT / config["results_dir"] / experiment_id / "ablations" / abl_name
        abl_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"ABLATION: {abl_name} — {abl.get('description','')} (retry_budget={retry_budget})")
        print(f"{'='*60}")

        # Synthetic system: same module as multi_agent, tagged with ablation name.
        abl_system = dict(multi)
        abl_system["name"] = abl_name

        # Force edges.py to re-read AGENT_MAX_RETRIES on next import.
        os.environ["AGENT_MAX_RETRIES"] = str(retry_budget)
        purge_agent_modules()
        # Purging re-imports agent.tools, which resets the fixture resolver to
        # None. Re-install it so research/localization still hit local fixtures.
        install_agent_resolver()

        for task in tasks:
            result = run_single_system_task(
                abl_system, task, abl_dir,
                env_overrides={"AGENT_MAX_RETRIES": retry_budget},
                lifecycle=lambda *, exp_dir=abl_dir.parent.parent, raw_dir=abl_dir: None,
            )
            all_results.append(result)

        # Restore default retry budget for any subsequent runs.
        os.environ.pop("AGENT_MAX_RETRIES", None)
        purge_agent_modules()
        install_agent_resolver()

    print(f"\n[ABLATIONS] Complete. {len(all_results)} ablation runs.")
    return all_results


def main():
    parser = argparse.ArgumentParser(
        description="GitHub Issue Agent Benchmark Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full benchmark
  python evaluation/run_benchmark.py --config evaluation/configs/benchmark.yaml

  # Smoke test (1 task, all systems)
  python evaluation/run_benchmark.py --config evaluation/configs/benchmark.yaml --smoke

  # Single system
  python evaluation/run_benchmark.py --config evaluation/configs/benchmark.yaml --system baseline_a

  # Single task
  python evaluation/run_benchmark.py --config evaluation/configs/benchmark.yaml --task task_001
        """
    )
    parser.add_argument("--config", default="evaluation/configs/benchmark.yaml",
                        help="Path to benchmark config YAML")
    parser.add_argument("--system", default=None,
                        help="Run only this system (e.g., baseline_a, baseline_b, multi_agent)")
    parser.add_argument("--task", default=None,
                        help="Run only tasks matching this string (e.g., task_001)")
    parser.add_argument("--smoke", action="store_true",
                        help="Quick smoke test: run only 1 task with all systems")
    parser.add_argument("--ablations", action="store_true",
                        help="Run configured ablations (e.g. multi-agent no-retry)")
    parser.add_argument("--metrics", action="store_true",
                        help="Run metrics aggregation after benchmark")
    parser.add_argument("--evaluate", action="store_true",
                        help="Run the canonical evaluation pipeline after the benchmark: "
                             "frozen-input manifest gate, 3-artifact ledger build "
                             "(task_ledger/analysis/paired_analysis), and validation "
                             "(V01-V10). Non-zero exit on any validation failure.")
    parser.add_argument("--v4-arm", default=None,
                        help="V4 independent-arm execution mode. Exactly one V4 arm system "
                             "(adaptive_multi_agent or baseline_b). Runs a standalone 30-task "
                             "arm package under the same benchmark_v4.yaml config so the two "
                             "arms can be scheduled independently under the 600s outer wrapper.")

    args = parser.parse_args()

    config_path = REPO_ROOT / args.config if not Path(args.config).is_absolute() else Path(args.config)
    if not config_path.exists():
        print(f"[ERROR] Config not found: {config_path}")
        sys.exit(1)

    config = load_config(str(config_path))
    experiment_id = get_experiment_id()

    # ---- V4 fail-closed contract enforcement --------------------------------
    eval_settings = config.get("evaluation_settings", {}) or {}
    is_v4 = "benchmark_v4" in config_path.name or eval_settings.get("require_evaluate")
    if is_v4:
        if args.v4_arm:
            if not args.evaluate:
                print("[ERROR] V4 arm execution REQUIRES --evaluate so each arm package "
                      "is post-validated before it can be merged.")
                print("        Rerun with --evaluate (manifest gate + single-arm ledger + "
                      "V01-V10 validation).")
                sys.exit(1)
            if eval_settings.get("require_preflight"):
                print("[V4] Verifying preflight run manifest...")
                import preflight_v4
                m_ok, m_detail = preflight_v4.verify_manifest_file()
                if not m_ok:
                    print(f"[ERROR] V4 preflight run manifest not current: {m_detail}")
                    print("        Run: python evaluation/preflight_v4.py --generate-manifest")
                    sys.exit(1)
                print(f"[V4] run manifest CURRENT — {m_detail}")
        elif not args.evaluate:
            print("[ERROR] V4 config REQUIRES the canonical evaluation pipeline.")
            print("        Rerun with --evaluate (manifest gate + task_ledger/analysis/"
                  "paired_analysis + V01-V10 validation).")
            sys.exit(1)
        elif eval_settings.get("require_preflight"):
            print("[V4] Verifying preflight run manifest...")
            import preflight_v4
            m_ok, m_detail = preflight_v4.verify_manifest_file()
            if not m_ok:
                print(f"[ERROR] V4 preflight run manifest not current: {m_detail}")
                print("        Run: python evaluation/preflight_v4.py --generate-manifest")
                sys.exit(1)
            print(f"[V4] run manifest CURRENT — {m_detail}")

    if args.v4_arm:
        run_v4_arm(
            config=config,
            arm_system=args.v4_arm,
            config_path=config_path,
        )
    elif args.ablations:
        run_ablations(
            config=config,
            experiment_id=experiment_id,
            filter_task=args.task,
            smoke=args.smoke,
        )
    else:
        run_benchmark(
            config=config,
            filter_system=args.system,
            filter_task=args.task,
            smoke=args.smoke,
        )

    if args.metrics:
        print("\n[INFO] Running metrics aggregation...")
        metrics_path = REPO_ROOT / "evaluation" / "metrics.py"
        raw_dir = REPO_ROOT / config["results_dir"] / experiment_id / "raw"
        agg_dir = REPO_ROOT / config["results_dir"] / experiment_id / "aggregates"
        if metrics_path.exists():
            os.system(f"{sys.executable} {metrics_path} --results-dir {raw_dir} --out {agg_dir}")

    if args.evaluate:
        lc = lifecycle or _import_lifecycle()

        if args.v4_arm:
            print("\n[EVALUATE] V4 single-arm canonical pipeline...")
            from verify_manifest import verify_manifest
            gate = verify_manifest()
            if not gate["ok"]:
                print("[EVALUATE] ABORT: frozen benchmark inputs changed "
                      f"(changed={len(gate['changed'])} missing={len(gate['missing'])} "
                      f"extra={len(gate['extra'] or [])}) — arm results are not comparable.")
                sys.exit(1)
            print(f"[EVALUATE] manifest gate OK: {gate['verified']}/{gate['manifest_entries']} unchanged")

            exp_dir = REPO_ROOT / config["results_dir"] / experiment_id
            print("\n[EVALUATE] 2/4 single-arm canonical ledger build...")
            import build_ledger
            paths, warnings = build_ledger.build_package(
                experiment_id, raw_dir=exp_dir / "raw", out_dir=exp_dir)
            for w in warnings:
                print(f"[EVALUATE] [WARN] {w}")
            print(f"[EVALUATE] wrote {paths['task_ledger']}")
            print(f"[EVALUATE] wrote {paths['analysis']}")
            print(f"[EVALUATE] wrote {paths['paired_analysis']}")

            print("\n[EVALUATE] 3/4 single-arm validation (V01-V10, single-arm mode)...")
            import validate_ledger
            report = validate_ledger.validate_package(
                exp_dir,
                expect_systems=[args.v4_arm],
                require_two_systems=False,
            )
            for e in report["errors"]:
                print(f"[EVALUATE] [FAIL] {e}")
            for w in report["warnings"]:
                print(f"[EVALUATE] [WARN] {w}")

            print("\n[EVALUATE] 4/4 single-arm lifecycle finalization...")
            finalization = lc.finalize_experiment(
                exp_dir,
                validation_ok=report["ok"],
                validation_errors=report["errors"],
                validation_warnings=report["warnings"],
            )
            print(f"[EVALUATE] lifecycle state = {finalization['status']}")
            print(f"[EVALUATE] reason = {finalization['completion_reason']}")

            if finalization["status"] != lc.COMPLETE:
                print("\n[EVALUATE] INCOMPLETE/INVALID ARM PACKAGE: "
                      "--evaluate refuses to declare this arm COMPLETE because "
                      "the 30-result single-arm invariant or canonical validation is not satisfied.")
                print(f"[EVALUATE] raw counts = {json.dumps(finalization['raw_counts'], indent=2)}")
                sys.exit(1)

            print(f"\n[EVALUATE] OK: arm package valid + lifecycle COMPLETE "
                  f"({report['n_entries']} entries, "
                  f"{len(report['warnings'])} disclosed warnings).")
        else:
            # Canonical evaluation pipeline (permanent methodology):
            #   1. frozen-input manifest gate (182/182, read-only)
            #   2. build task_ledger.json + analysis.json + paired_analysis.json
            #   3. validate the package (V01-V10); hard-fail on any error
            #   4. fail-closed lifecycle finalization (60-result invariant required)
            print("\n[EVALUATE] 1/4 frozen-input manifest gate...")
            from verify_manifest import verify_manifest
            gate = verify_manifest()
            if not gate["ok"]:
                print("[EVALUATE] ABORT: frozen benchmark inputs changed during the run "
                      f"(changed={len(gate['changed'])} missing={len(gate['missing'])} "
                      f"extra={len(gate['extra'] or [])}) — results are not comparable.")
                sys.exit(1)
            print(f"[EVALUATE] gate OK: {gate['verified']}/{gate['manifest_entries']} frozen inputs unchanged")

            print("\n[EVALUATE] 2/4 canonical ledger build...")
            import build_ledger
            exp_dir = REPO_ROOT / config["results_dir"] / experiment_id
            paths, warnings = build_ledger.build_package(
                experiment_id, raw_dir=exp_dir / "raw", out_dir=exp_dir)
            for w in warnings:
                print(f"[EVALUATE] [WARN] {w}")
            print(f"[EVALUATE] wrote {paths['task_ledger']}")
            print(f"[EVALUATE] wrote {paths['analysis']}")
            print(f"[EVALUATE] wrote {paths['paired_analysis']}")

            print("\n[EVALUATE] 3/4 validation...")
            import validate_ledger
            report = validate_ledger.validate_package(exp_dir)
            for e in report["errors"]:
                print(f"[EVALUATE] [FAIL] {e}")
            for w in report["warnings"]:
                print(f"[EVALUATE] [WARN] {w}")

            print("\n[EVALUATE] 4/4 lifecycle finalization...")
            finalization = lc.finalize_experiment(
                exp_dir,
                validation_ok=report["ok"],
                validation_errors=report["errors"],
                validation_warnings=report["warnings"],
            )
            print(f"[EVALUATE] lifecycle state = {finalization['status']}")
            print(f"[EVALUATE] reason = {finalization['completion_reason']}")

            if finalization["status"] != lc.COMPLETE:
                print("\n[EVALUATE] INCOMPLETE/INVALID EXPERIMENT: "
                      "--evaluate refuses to declare this experiment COMPLETE because "
                      "the 60-result invariant or canonical validation is not satisfied.")
                print(f"[EVALUATE] raw counts = {json.dumps(finalization['raw_counts'], indent=2)}")
                sys.exit(1)

            print(f"\n[EVALUATE] OK: package valid + lifecycle COMPLETE "
                  f"({report['n_entries']} entries, "
                  f"{len(report['warnings'])} disclosed warnings).")


if __name__ == "__main__":
    main()
