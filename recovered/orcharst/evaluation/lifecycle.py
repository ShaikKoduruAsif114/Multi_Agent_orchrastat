"""
evaluation/lifecycle.py

Fail-closed experiment lifecycle for the V4 controlled benchmark.

This module is the single authoritative lifecycle state machine. The runner
writes IN_PROGRESS as soon as the experiment directory is created, updates it
after each raw result is durably written, and only transitions to COMPLETE
after the 60-result invariant plus canonical validation are both satisfied.

States (experiment_status field):
    IN_PROGRESS      directory created; benchmark executing
    COMPLETE         60 raw results + evaluation artifacts + validation OK
    INVALID_PARTIAL  directory exists but the 60-result invariant is broken
    FAILED           benchmark aborted before durable results could be recorded

All state transitions are read-only with respect to the existing experiment
directory once written. Nothing here reruns tasks or removes results.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evaluation"))

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Canonical constants for the controlled V4 experiment
# ---------------------------------------------------------------------------
EXPECTED_TASKS = 30
EXPECTED_ARMS = 2
EXPECTED_RAW_RESULTS = 60
ARMS = ("adaptive_multi_agent", "baseline_b")
TASK_IDS = [f"task_{i:03d}" for i in range(1, EXPECTED_TASKS + 1)]
RAW_STATES = (IN_PROGRESS := "IN_PROGRESS",
              COMPLETE := "COMPLETE",
              INVALID_PARTIAL := "INVALID_PARTIAL",
              FAILED := "FAILED")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def config_sha(config_path: Path) -> str:
    return sha256_file(config_path)


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_status(exp_dir: Path, status: str, *, force: bool = False) -> Path:
    """Write experiment_status.json into the experiment directory.

    The status file is the single source of truth for lifecycle state.
    """
    exp_dir.mkdir(parents=True, exist_ok=True)
    status_path = exp_dir / "experiment_status.json"
    payload = {
        "experiment_id": exp_dir.name,
        "status": status,
        "updated_utc": _utc_now_iso(),
    }
    # Preserve any prior fields the runner already wrote (config_sha, etc.)
    if status_path.exists() and not force:
        prior = json.loads(status_path.read_text(encoding="utf-8"))
        payload.update({k: v for k, v in prior.items() if k not in payload})
    status_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return status_path


EXPECTED_SINGLE_ARM_TASKS = 30


def init_lifecycle(exp_dir: Path,
                   config_path: Path,
                   *,
                   arm_system: str = None,
                   benchmark_manifest_sha: str = None,
                   commit_sha: str = None,
                   provider: str = None,
                   model: str = None) -> dict:
    """Create the experiment directory and write the initial IN_PROGRESS status.

    Raises if the target directory already exists and is non-empty (stale
    experiment directory guard, requirement 9).
    """
    if exp_dir.exists():
        raw = exp_dir / "raw"
        if raw.exists() and any(raw.iterdir()):
            raise RuntimeError(
                f"ABORT: target experiment directory is not empty: {exp_dir}\n"
                "A stale/partial experiment already exists there. Refusing to silently "
                "resume or overwrite it. Use a fresh experiment directory or clean it up explicitly.")
        if (exp_dir / "experiment_status.json").exists():
            raise RuntimeError(
                f"ABORT: experiment_status.json already exists in {exp_dir}. "
                "Refusing to silently resume an existing experiment lifecycle.")
    exp_dir.mkdir(parents=True, exist_ok=True)

    status = {
        "experiment_id": exp_dir.name,
        "status": IN_PROGRESS,
        "start_time": _utc_now_iso(),
        "config_path": str(config_path),
        "config_sha": config_sha(config_path),
        "arm_system": arm_system or "",
        "benchmark_manifest_sha": benchmark_manifest_sha or "",
        "commit_sha": commit_sha or "",
        "provider": provider or "",
        "model": model or "",
        "expected_tasks": EXPECTED_SINGLE_ARM_TASKS if arm_system else EXPECTED_TASKS,
        "expected_arms": EXPECTED_ARMS,
        "expected_raw_results": EXPECTED_SINGLE_ARM_TASKS if arm_system else EXPECTED_RAW_RESULTS,
        "protocol_version": "1.0.0 (frozen before the run)",
        "updated_utc": _utc_now_iso(),
    }
    status_path = exp_dir / "experiment_status.json"
    status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    return status


def raw_result_counts(raw_dir: Path) -> dict:
    """Return per-arm raw-result counts and task-ID coverage for raw_dir."""
    if not raw_dir.exists():
        return {"adaptive_multi_agent": 0, "baseline_b": 0,
                "adaptive_task_ids": [], "baseline_task_ids": [],
                "adaptive_duplicates": [], "baseline_duplicates": [],
                "raw_file_count": 0}
    return _raw_result_counts_from_dir(raw_dir)


def _raw_result_counts_from_dir(raw_dir: Path) -> dict:
    counts = {"adaptive_multi_agent": 0, "baseline_b": 0}
    task_id_sets = {"adaptive_multi_agent": [], "baseline_b": []}
    seen = {"adaptive_multi_agent": set(), "baseline_b": set()}
    dups = {"adaptive_multi_agent": [], "baseline_b": []}
    for p in sorted(raw_dir.glob("*.json")):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        system = rec.get("system")
        task_id = rec.get("task_id")
        if system not in ARMS or not task_id:
            continue
        counts[system] += 1
        task_id_sets[system].append(task_id)
        if task_id in seen[system]:
            dups[system].append(task_id)
        else:
            seen[system].add(task_id)
    return {
        "adaptive_multi_agent": counts["adaptive_multi_agent"],
        "baseline_b": counts["baseline_b"],
        "adaptive_task_ids": sorted(task_id_sets["adaptive_multi_agent"]),
        "baseline_task_ids": sorted(task_id_sets["baseline_b"]),
        "adaptive_duplicates": dups["adaptive_multi_agent"],
        "baseline_duplicates": dups["baseline_b"],
        "raw_file_count": sum(counts.values()),
    }


def _single_arm_counts(counts: dict[str, object], arm_system: str) -> dict:
    """Derived single-arm counters from the dict returned by raw_result_counts.

    Because raw_result_counts always returns a fixed two-arm schema, we index
    into that dict directly. When the underlying raw directory is missing, the
    fallback schema from raw_result_counts is used instead.
    """
    task_ids = list(counts.get(f"{arm_system}_task_ids") or [])
    duplicates = list(counts.get(f"{arm_system}_duplicates") or [])
    own_count = int(counts.get(arm_system, 0) or 0)
    other = "baseline_b" if arm_system == "adaptive_multi_agent" else "adaptive_multi_agent"
    other_count = int(counts.get(other, 0) or 0)
    raw_file_count = int(counts.get("raw_file_count", 0) or 0)
    return {
        "arm_count": own_count,
        "arm_task_ids": task_ids,
        "arm_duplicates": duplicates,
        "other_count": other_count,
        "raw_file_count": raw_file_count,
    }


def _single_arm_invariant_ok(counts: dict[str, object], status_doc: dict | None = None) -> tuple[bool, list[str]]:
    """Variant of invariant_ok used by the V4 single-arm lifecycle path.

    An arm-only experiment directory is COMPLETE only when exactly one V4 arm
    has 30 distinct task_001..task_030 raw results and the other arm has zero
    noisy entries.
    """
    arm = status_doc.get("arm_system") if status_doc else None
    issues: list[str] = []
    if not arm or arm not in ARMS:
        # Legacy inspector path without arm metadata: fall back to the original
        # 60-result invariant so existing two-arm tooling still derives the same
        # terminal state.
        return invariant_ok(counts)

    sc = _single_arm_counts(counts, arm)
    if sc["arm_count"] != EXPECTED_SINGLE_ARM_TASKS:
        issues.append(f"{arm} raw results = {sc['arm_count']}, expected {EXPECTED_SINGLE_ARM_TASKS}")
    if sorted(sc["arm_task_ids"]) != TASK_IDS:
        missing = sorted(set(TASK_IDS) - set(sc["arm_task_ids"]))
        extra = sorted(set(sc["arm_task_ids"]) - set(TASK_IDS))
        issues.append(f"{arm} task IDs incomplete; missing={missing} extra={extra}")
    if sc["arm_duplicates"]:
        issues.append(f"duplicate {arm} task IDs: {sc['arm_duplicates']}")
    if sc["other_count"]:
        issues.append(f"unexpected {sc['other_count']} raw results for the non-executed arm in an arm-only package")
    return len(issues) == 0, issues


def invariant_ok(counts: dict) -> tuple[bool, list[str]]:
    """Check the 60-result invariant for a controlled 30-task × 2-arm run."""
    issues: list[str] = []
    a_count = counts["adaptive_multi_agent"]
    b_count = counts["baseline_b"]

    if a_count != EXPECTED_TASKS:
        issues.append(f"adaptive raw results = {a_count}, expected {EXPECTED_TASKS}")
    if b_count != EXPECTED_TASKS:
        issues.append(f"baseline raw results = {b_count}, expected {EXPECTED_TASKS}")
    if a_count != EXPECTED_TASKS or b_count != EXPECTED_TASKS:
        issues.append("60-result invariant not satisfied")

    if sorted(counts["adaptive_task_ids"]) != TASK_IDS:
        missing = sorted(set(TASK_IDS) - set(counts["adaptive_task_ids"]))
        extra = sorted(set(counts["adaptive_task_ids"]) - set(TASK_IDS))
        issues.append(f"adaptive task IDs incomplete; missing={missing} extra={extra}")
    if sorted(counts["baseline_task_ids"]) != TASK_IDS:
        missing = sorted(set(TASK_IDS) - set(counts["baseline_task_ids"]))
        extra = sorted(set(counts["baseline_task_ids"]) - set(TASK_IDS))
        issues.append(f"baseline task IDs incomplete; missing={missing} extra={extra}")

    if counts["adaptive_duplicates"]:
        issues.append(f"duplicate adaptive task IDs: {counts['adaptive_duplicates']}")
    if counts["baseline_duplicates"]:
        issues.append(f"duplicate baseline task IDs: {counts['baseline_duplicates']}")

    return len(issues) == 0, issues


def _terminal_invariant_ok(counts: dict, status_doc: dict | None = None) -> tuple[bool, list[str]]:
    """Terminal invariant used by finalize_experiment and the inspector path.

    Two-arm directories must satisfy the original 60-result invariant. Arm-only
    directories must satisfy the single-arm 30-result invariant (recorded arm
    has 30 distinct tasks, other arm has zero noisy entries).
    """
    arm = status_doc.get("arm_system") if status_doc else None
    if not arm or arm not in ARMS:
        return invariant_ok(counts)
    return _single_arm_invariant_ok(counts, status_doc)


def classify_state(exp_dir: Path, *, require_validation_ok: bool = False,
                   validation_ok: bool = None) -> str:
    """Classify the lifecycle state of an existing experiment directory.

    This is the post-hoc/inspector path used by validators and by --evaluate
    before declaring an experiment complete.
    """
    status_path = exp_dir / "experiment_status.json"
    raw_dir = exp_dir / "raw"

    if not exp_dir.exists():
        return FAILED

    if status_path.exists():
        try:
            status_doc = json.loads(status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            status_doc = {}
        prior = status_doc.get("status")
        if prior == COMPLETE:
            return COMPLETE
        if prior == FAILED:
            return FAILED

    # Evaluate the durable state from the filesystem.
    if not raw_dir.exists() or not any(raw_dir.iterdir()):
        return FAILED

    counts = raw_result_counts(raw_dir)
    if not _single_arm_invariant_ok(counts, status_doc):
        return INVALID_PARTIAL

    if require_validation_ok and validation_ok is False:
        return INVALID_PARTIAL

    return COMPLETE


def finalize_experiment(exp_dir: Path, *, validation_ok: bool,
                        validation_errors: list[str] = None,
                        validation_warnings: list[str] = None) -> dict:
    """Finalize lifecycle state after the run + evaluation pipeline.

    - 60-result invariant satisfied AND canonical validation OK -> COMPLETE
    - otherwise -> INVALID_PARTIAL (or FAILED if no durable results)
    """
    raw_dir = exp_dir / "raw"
    status_path = exp_dir / "experiment_status.json"
    status_doc = None
    if status_path.exists():
        try:
            status_doc = json.loads(status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            status_doc = None

    if not raw_dir.exists() or not any(raw_dir.iterdir()):
        counts = {"adaptive_multi_agent": 0, "baseline_b": 0,
                  "adaptive_task_ids": [], "baseline_task_ids": [],
                  "adaptive_duplicates": [], "baseline_duplicates": [],
                  "raw_file_count": 0}
    else:
        counts = raw_result_counts(raw_dir)

    ok, issues = _terminal_invariant_ok(counts, status_doc)

    if not raw_dir.exists() or counts["raw_file_count"] == 0:
        new_state = FAILED
        reason = "no durable raw results recorded"
    elif not ok:
        new_state = INVALID_PARTIAL
        if status_doc and status_doc.get("arm_system"):
            reason = "single-arm 30-result invariant not satisfied: " + "; ".join(issues)
        else:
            reason = "60-result invariant not satisfied: " + "; ".join(issues)
    elif not validation_ok:
        new_state = INVALID_PARTIAL
        reason = "canonical validation failed: " + (
            "; ".join(validation_errors) if validation_errors else "unknown")
    else:
        new_state = COMPLETE
        if status_doc and status_doc.get("arm_system"):
            reason = "30 raw results + evaluation artifacts + canonical validation OK"
        else:
            reason = "60 raw results + evaluation artifacts + canonical validation OK"

    doc = {
        "experiment_id": exp_dir.name,
        "status": new_state,
        "completion_reason": reason,
        "final_invariant_ok": ok,
        "invariant_issues": issues if not ok else [],
        "validation_ok": validation_ok,
        "validation_errors": validation_errors or [],
        "validation_warnings": validation_warnings or [],
        "raw_counts": counts,
        "updated_utc": _utc_now_iso(),
    }
    status_path = exp_dir / "experiment_status.json"
    status_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return doc


def dry_run_lifecycle(tmp_root: Path, config_path: Path) -> Path:
    """Exercise the full lifecycle path without any API calls.

    Creates a fresh experiment directory, writes IN_PROGRESS, emits a few mock
    raw results, and demonstrates the INVALID_PARTIAL transition. This is the
    validation-mode entry point (requirement 10).
    """
    exp_dir = tmp_root / "dry_run_exp_full30"
    init_lifecycle(exp_dir, config_path,
                   benchmark_manifest_sha="dry-run-manifest-sha",
                   commit_sha="dry-run-commit-sha",
                   provider="nara",
                   model="laguna-s-2.1")

    raw_dir = exp_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Write exactly 3 mock adaptive raw results (deliberately incomplete).
    for i, task_id in enumerate(["task_001", "task_002", "task_003"], start=1):
        rec = {
            "task_id": task_id,
            "system": "adaptive_multi_agent",
            "repository": "https://example.invalid/dry-run",
            "issue_title": f"Dry-run task {i}",
            "timestamp": _utc_now_iso(),
            "end_to_end_resolved": False,
            "execution": {
                "status": "error",
                "failure_category": "dry_run_marker",
                "latency_seconds": 0.0,
                "llm_calls": None,
                "input_tokens": None,
                "output_tokens": None,
                "error_message": "dry-run placeholder",
            },
            "localization": {"predicted_file": None, "gold_file": "src/dry.py", "top1_correct": None},
            "patch": {"generated": False, "syntax_valid": None},
            "tests": {"generated": False, "generated_tests_passed": None},
            "regression": {"hidden_tests_passed": None, "regression_free": None},
            "repair": {"attempts": None, "first_attempt_success": None, "resolved_within_retry_budget": False},
            "cost": {"estimated_usd": None},
            "pr": {"branch_created": False, "commit_created": False, "pr_created": False},
        }
        (raw_dir / f"{task_id}_adaptive_multi_agent.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8")

    counts = raw_result_counts(raw_dir)
    ok, issues = invariant_ok(counts)
    # Dry-run helper must end in the same terminal state the inspector would
    # derive from durable files, not remain IN_PROGRESS.
    state = COMPLETE if ok else INVALID_PARTIAL
    write_status(exp_dir, state, force=True)
    return exp_dir


def init_v4_arm_lifecycle(exp_dir: Path,
                          config_path: Path,
                          arm_system: str,
                          *,
                          benchmark_manifest_sha: str,
                          commit_sha: str,
                          provider: str,
                          model: str) -> dict:
    """Convenience wrapper around init_lifecycle for the V4 arm execution path.

    Arm metadata is recorded in the initial status document so the merge/eval
    command and the lifecycle inspector can identify the package as a single-arm
    package and verify it against a single-arm 30-task invariant.
    """
    return init_lifecycle(
        exp_dir,
        config_path=config_path,
        arm_system=arm_system,
        benchmark_manifest_sha=benchmark_manifest_sha,
        commit_sha=commit_sha,
        provider=provider,
        model=model,
    )
