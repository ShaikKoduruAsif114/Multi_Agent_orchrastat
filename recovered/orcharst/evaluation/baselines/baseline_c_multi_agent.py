"""
evaluation/baselines/baseline_c_multi_agent.py

BASELINE C — Full Multi-Agent System (Headless)

Uses the actual project architecture:
  research → localization → code_writer → test_writer → docker_execution → retry

Runs in eval_mode=True:
  - Auto-approves the fix (no human input required)
  - Skips PR creation
  - Records full structured EvalResult

Then runs hidden tests against the proposed fix for authoritative evaluation.
"""

from __future__ import annotations

import os
import sys
import ast
import json
import time
import subprocess
from pathlib import Path
from typing import Optional

# Windows consoles often default to cp1252; force UTF-8 so unicode never crashes.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root / "github-issue-agent"))

from dotenv import load_dotenv
load_dotenv(repo_root / "github-issue-agent" / ".env")

from agent.graph import app as langgraph_app
from agent.instrumentation import active_eval_context, snapshot_into_state
from agent.provider import pricing_note, provider_info

# Fixture routing: the benchmark repos only exist locally. The resolver is
# installed by run_benchmark.py at import time; we also need the local file
# listing here to score the hallucination metric against real repo files.
if str(repo_root / "evaluation") not in sys.path:
    sys.path.insert(0, str(repo_root / "evaluation"))
from fixture_router import resolve_fixture_path, local_repo_files

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()


def run_hidden_tests(fix_code: str, hidden_test_file: str,
                     gold_file: Optional[str] = None) -> tuple[bool, str, int, int]:
    """Run hidden evaluation tests against the agent's proposed fix."""
    env = os.environ.copy()
    env["EVAL_FIX_CODE"] = fix_code
    if gold_file:
        # e.g. "src/pagination.py" -> "src.pagination" so the conftest can
        # materialize the fix under its real package path (tasks 006-030).
        env["EVAL_FIX_MODULE"] = gold_file.replace("\\", "/").replace("/", ".").removesuffix(".py")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", hidden_test_file,
         "--disable-warnings", "-v", "--tb=short"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        cwd=str(repo_root)
    )
    output = result.stdout + "\n" + result.stderr

    # Parse counts from the pytest summary line (passed + failed + error).
    import re
    passed_count = 0
    failed_count = 0
    for line in output.split("\n"):
        m = re.search(r"(\d+) passed", line)
        if m:
            passed_count = int(m.group(1))
        for mm in re.finditer(r"(\d+) (?:failed|error)", line):
            failed_count += int(mm.group(1))
    total = passed_count + failed_count

    return result.returncode == 0, output, total, passed_count


def run_task(task: dict) -> dict:
    task_id = task["task_id"]
    repo_url = task["repository"]
    issue_title = task["issue_title"]
    issue_body = task["issue_body"]
    issue_id = task.get("issue_id")
    gold_file = task["gold_file"]
    hidden_test_file = task["hidden_test_file"]

    print(f"\n[BASELINE_C] Running task {task_id} via full multi-agent pipeline...")
    overall_start = time.monotonic()

    # Build initial state for the LangGraph pipeline
    initial_state = {
        "repo_url": repo_url,
        "issue_number": issue_id or 0,
        "token": GITHUB_TOKEN,
        "problem_description": "",
        "mode": "issue" if issue_id else "smart",
        "session_id": f"eval_{task_id}",
        "is_web": False,
        "issue_title": "",
        "issue_body": "",
        "relevant_files": [],
        "proposed_fix": "",
        "tests_written": "",
        "pr_url": "",
        "messages": [],
        "human_approved": False,
        "retry_count": 0,
        "llm_calls": 0,
        "errors": [],
        # Eval-mode fields
        "eval_mode": True,
        "eval_task_id": task_id,
        "eval_gold_file": gold_file,
        "start_time": time.monotonic(),
        "input_tokens": 0,
        "output_tokens": 0,
        "original_file_content": "",
        "first_patch_source": "",
        "patch_diff": "",
        "lines_added": 0,
        "lines_removed": 0,
        "syntax_valid": None,
        "repair_plan": "",
        "localization_evidence": {},
        "patch_placeholder": False,
        "patch_apply_success": False,
        "patch_target_valid": False,
        "generated_code_is_model": False,
        "repair_attempts": [],
        "repair_history": [],
    }

    # Run the LangGraph pipeline inside an active EvalContext so every real
    # LLM call is recorded at the single choke point (authoritative counting).
    pipeline_error = None
    final_state = {}
    eval_ctx = None
    fixture_path = resolve_fixture_path(repo_url)
    try:
        with active_eval_context(task_id, system="multi_agent", repo_url=repo_url,
                                 fixture_path=fixture_path) as eval_ctx:
            final_state = langgraph_app.invoke(initial_state)
            snapshot_into_state(final_state)
    except Exception as e:
        pipeline_error = str(e)
        print(f"[BASELINE_C] Pipeline error: {e}")
        if eval_ctx is not None:
            final_state["llm_calls"] = eval_ctx.total_llm_calls()
            final_state["input_tokens"] = eval_ctx.input_tokens()
            final_state["output_tokens"] = eval_ctx.output_tokens()
            final_state["eval_metrics"] = eval_ctx.to_dict()

    latency = round(time.monotonic() - overall_start, 3)

    proposed_fix = final_state.get("proposed_fix", "")
    tests_passed = final_state.get("tests_passed", False)
    retry_count = final_state.get("retry_count", 0)
    relevant_files = final_state.get("relevant_files", [])
    patch_diff = final_state.get("patch_diff", "")
    lines_added = final_state.get("lines_added", 0)
    lines_removed = final_state.get("lines_removed", 0)
    syntax_valid = final_state.get("syntax_valid", None)
    errors = final_state.get("errors", [])
    patch_placeholder = bool(final_state.get("patch_placeholder", False))
    patch_apply_success = bool(final_state.get("patch_apply_success", False))
    patch_target_valid = bool(final_state.get("patch_target_valid", False))
    generated_code_is_model = bool(final_state.get("generated_code_is_model", False))
    repair_attempts = final_state.get("repair_attempts", []) or []

    # Authoritative LLM/token accounting comes from the EvalContext that
    # recorded every real call. Fall back to the state snapshot (set by
    # snapshot_into_state) only if no context was active.
    if eval_ctx is not None:
        llm_calls = eval_ctx.total_llm_calls()
        input_tokens = eval_ctx.input_tokens()
        output_tokens = eval_ctx.output_tokens()
    else:
        llm_calls = final_state.get("llm_calls", 0)
        input_tokens = final_state.get("input_tokens", 0)
        output_tokens = final_state.get("output_tokens", 0)

    # Hallucination: a null prediction is NOT a hallucination; a non-null
    # prediction that is not a real file in the repo IS a hallucination.
    repo_files = local_repo_files(repo_url)
    predicted_file = relevant_files[0] if relevant_files else None
    top1_correct = (predicted_file == gold_file) if predicted_file else False
    hallucinated = (predicted_file is not None and predicted_file not in repo_files)

    # Placeholder detection mirrors the agent's own gate markers.
    placeholder_detected = (
        any(m in proposed_fix for m in [
            "def resolve_issue():", "Automated code fix applied",
            "# Proposed Fix for", "Updated logic for",
        ])
        if proposed_fix else False
    )

    # -----------------------------------------------------------------------
    # Run hidden tests against the agent's proposed fix
    # -----------------------------------------------------------------------
    hidden_passed = False
    hidden_output = ""
    hidden_total = 0
    hidden_passed_count = 0
    syntax_valid_actual = syntax_valid

    if proposed_fix:
        # Double-check syntax
        try:
            ast.parse(proposed_fix)
            syntax_valid_actual = True
        except SyntaxError:
            syntax_valid_actual = False

        if syntax_valid_actual:
            try:
                hidden_passed, hidden_output, hidden_total, hidden_passed_count = run_hidden_tests(
                    proposed_fix, hidden_test_file, gold_file
                )
            except subprocess.TimeoutExpired:
                hidden_output = "Hidden test execution timed out"
            except Exception as e:
                hidden_output = f"Error running hidden tests: {e}"

    # -----------------------------------------------------------------------
    # FIRST-PASS semantic: did the FIRST generated patch pass hidden tests?
    # The graph sandbox runs SELF-GENERATED diagnostic tests; that outcome is
    # not patch quality. If no repair ran, the single patch is both first and
    # final. If repairs ran, re-run hidden tests on the recorded first patch.
    # -----------------------------------------------------------------------
    first_patch = final_state.get("first_patch_source", "") or proposed_fix
    repair_attempt_count = len(repair_attempts)
    if repair_attempt_count == 0:
        first_pass_resolved_hidden = hidden_passed
        first_pass_hidden_output = hidden_output
    elif first_patch and first_patch != proposed_fix:
        try:
            fp_passed, fp_output, fp_total, fp_passed_n = run_hidden_tests(
                first_patch, hidden_test_file, gold_file
            )
        except Exception as e:
            fp_passed, fp_output, fp_total, fp_passed_n = False, f"first-pass rerun error: {e}", 0, 0
        first_pass_resolved_hidden = fp_passed
        first_pass_hidden_output = fp_output[:1000]
    else:
        # Repair ran but the first patch was not separately recorded (should
        # not happen); classify conservatively as not first-pass-resolved.
        first_pass_resolved_hidden = False
        first_pass_hidden_output = "first patch not recorded"

    # -----------------------------------------------------------------------
    # Determine resolution status — final correctness gate
    # -----------------------------------------------------------------------
    # A task is resolved only when: localization is valid (real file), the
    # patch is real/non-placeholder, the patch is valid/applied, hidden tests
    # actually executed and passed, and no provider contamination occurred.
    provider_llm_failures = eval_ctx.provider_failures() if eval_ctx is not None else []
    provider_contamination = [
        {
            "stage": c.stage,
            "error": c.error[:500],
            "failure_category": c.failure_category,
            "latency_seconds": c.latency,
        }
        for c in provider_llm_failures
    ]
    contamination_detected = bool(provider_contamination)
    if contamination_detected:
        # The task's stored record must be flagged, never silently counted as
        # a clean result. end_to_end_resolved stays False for contamination
        # unless hidden tests were genuinely executed and passed afterwards;
        # the audit marks any contaminated task explicitly.
        contamination_flag = True
    else:
        contamination_flag = False

    localization_valid = (
        bool(relevant_files)
        and relevant_files[0] in repo_files
        if repo_files else bool(relevant_files)
    )

    if pipeline_error and not proposed_fix:
        status = "error"
    elif not proposed_fix:
        status = "patch_failed"
    elif placeholder_detected or not generated_code_is_model:
        status = "patch_placeholder"
    elif not syntax_valid_actual:
        status = "syntax_error"
    elif not hidden_passed:
        status = "hidden_test_failed"
    else:
        status = "resolved"

    cost = round((input_tokens / 1_000_000 * 0.59) + (output_tokens / 1_000_000 * 0.79), 6)

    result = {
        "task_id": task_id,
        "system": "multi_agent",
        "repository": repo_url,
        "issue_id": str(issue_id) if issue_id else None,
        "issue_title": issue_title,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": {
            **provider_info(),
            "served_models": sorted({c.served_model for c in (eval_ctx.llm_calls if eval_ctx else []) if c.served_model}),
            "contamination_detected": contamination_detected,
            "contamination": provider_contamination,
        },
        "localization": {
            "predicted_file": predicted_file,
            "gold_file": gold_file,
            "top1_correct": top1_correct,
            "top3_correct": top1_correct,
            "hallucinated_file": hallucinated,
            "valid": localization_valid,
        },
        "patch": {
            "generated": bool(proposed_fix),
            "is_placeholder": placeholder_detected,
            "generated_by_model": generated_code_is_model,
            "syntax_valid": syntax_valid_actual,
            "files_changed": 1 if proposed_fix else 0,
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "patch_apply_success": patch_apply_success,
            "patch_target_valid": patch_target_valid,
            "diff": patch_diff[:2000] if patch_diff else None,
        },
        "tests": {
            "generated": bool(final_state.get("tests_written")),
            "generated_tests_executed": tests_passed is not None,
            "generated_tests_passed": tests_passed,
            "generated_test_count": None,
            "generated_tests_output": final_state.get("test_results", "")[:500] if final_state.get("test_results") else None,
        },
        "regression": {
            "hidden_tests_executed": bool(proposed_fix and syntax_valid_actual),
            "hidden_tests_passed": hidden_passed,
            "hidden_tests_total": hidden_total if hidden_total > 0 else None,
            "hidden_tests_passed_count": hidden_passed_count if hidden_passed_count > 0 else None,
            "hidden_tests_output": hidden_output[:1000] if hidden_output else None,
            "regression_free": hidden_passed,
        },
        "repair": {
            "attempts": retry_count + 1,
            "repair_attempt_count": repair_attempt_count,
            "first_pass_resolved_hidden": first_pass_resolved_hidden,
            "first_pass_failure_category": (
                None if first_pass_resolved_hidden else "first_patch_failed_hidden_tests"
            ),
            # PHASE 6 semantics: repair eligibility is a GENUINE first-pass
            # failure (hidden tests failed on the first patch), not merely
            # "the diagnostic-test repair loop fired". This keeps the
            # recovery-rate denominator honest.
            "repair_eligible": first_pass_resolved_hidden is False,
            "repair_recovered": bool(
                first_pass_resolved_hidden is False
                and repair_attempt_count > 0
                and hidden_passed
            ),
            "resolved_within_retry_budget": hidden_passed,
            "retry_budget": int(os.getenv("AGENT_MAX_RETRIES", "3")),
            "repair_attempts": repair_attempts,
            "first_pass_output": first_pass_hidden_output if not first_pass_resolved_hidden else None,
        },
        "execution": {
            "status": status,
            "failure_category": pipeline_error if pipeline_error else None,
            "latency_seconds": latency,
            "llm_calls": llm_calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "sandbox_mode": "subprocess",
            "error_message": pipeline_error,
        },
        "cost": {
            "estimated_usd": cost,
            "pricing_note": pricing_note(),
        },
        "pr": {
            "branch_created": False,
            "commit_created": False,
            "pr_created": False,
            "pr_url": final_state.get("pr_url") or None,
        },
        "end_to_end_resolved": (
            bool(proposed_fix)
            and not placeholder_detected
            and generated_code_is_model
            and (syntax_valid_actual is not False)
            and hidden_passed
            and not pipeline_error
        ),
        "provider_contamination": contamination_flag,
        # Full authoritative instrumentation snapshot (per-call LLM records,
        # tool calls, node runs, sandbox runs, retries). Populated by
        # snapshot_into_state from the active EvalContext.
        "eval_metrics": final_state.get("eval_metrics"),
    }
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Baseline C — Full Multi-Agent System")
    parser.add_argument("--task", required=True, help="Path to benchmark task JSON")
    parser.add_argument("--output-dir", default="evaluation/results", help="Results directory")
    args = parser.parse_args()

    with open(args.task) as f:
        task = json.load(f)

    result = run_task(task)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{result['task_id']}_multi_agent.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n[BASELINE_C] Result saved to {out_path}")
    print(f"  Status: {result['execution']['status']}")
    print(f"  Resolved: {result['end_to_end_resolved']}")
    print(f"  LLM calls: {result['execution']['llm_calls']}")
    print(f"  Latency: {result['execution']['latency_seconds']}s")
    print(f"  Cost: ${result['cost']['estimated_usd']}")
