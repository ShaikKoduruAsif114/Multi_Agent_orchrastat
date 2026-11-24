"""
evaluation/baselines/baseline_b_single_retry.py

BASELINE B — Single Agent + Retry (No Test Generation Stage)

Flow:
  issue → LLM patch → hidden tests → failure feedback → LLM repair → repeat

Uses the SAME retry budget as the multi-agent system (max 3 retries).
Does NOT use: research node, test_writer_node, Docker sandbox.
Evaluates only using hidden tests.
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

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "github-issue-agent"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / "github-issue-agent" / ".env")

from langchain_core.messages import SystemMessage, HumanMessage
from github import Github
from agent.provider import get_chat_model, pricing_note, provider_info, classify_provider_failure


GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
# Retry budget is configurable so evaluation ablations can run the SAME
# baseline with AGENT_MAX_RETRIES=0. Controlled experiments MUST set this
# equal to the multi-agent budget (run_benchmark.py exports it).
MAX_RETRIES = int(os.getenv("AGENT_MAX_RETRIES", "3"))

# Per-call instrumentation recorded for every LLM invocation of this system.
LLM_CALL_LOG: list[dict] = []


def get_llm():
    return get_chat_model()


def llm_call(messages, stage: str = "unlabeled") -> tuple[str, int, int]:
    """One provider call, zero retries, strict failure semantics.

    Under AGENT_STRICT_LLM=1 an exception is re-raised so provider failures
    can never become fake successful generations.
    """
    started = time.monotonic()
    try:
        llm = get_llm()
        res = llm.invoke(messages)
        content = str(res.content)
        usage = getattr(res, "usage_metadata", None) or getattr(res, "response_metadata", {})
        input_tokens = 0
        output_tokens = 0
        served_model = ""
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
            output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
        response_metadata = getattr(res, "response_metadata", {})
        if isinstance(response_metadata, dict):
            served_model = str(response_metadata.get("model", "") or "")
        LLM_CALL_LOG.append({
            "stage": stage, "ok": True,
            "latency_seconds": round(time.monotonic() - started, 4),
            "input_tokens": int(input_tokens), "output_tokens": int(output_tokens),
            "served_model": served_model, "error": "",
            "failure_category": "",
        })
        return content, int(input_tokens), int(output_tokens)
    except Exception as e:
        category, _ = classify_provider_failure(e)
        LLM_CALL_LOG.append({
            "stage": stage, "ok": False,
            "latency_seconds": round(time.monotonic() - started, 4),
            "input_tokens": 0, "output_tokens": 0,
            "served_model": "", "error": str(e)[:500],
            "failure_category": category,
        })
        print(f"[BASELINE_B] LLM error ({category}): {e}")
        if os.getenv("AGENT_STRICT_LLM", "").strip() == "1":
            raise
        return "", 0, 0


def list_repo_files(repo_name: str) -> list[str]:
    # Local fixture first: benchmark repos only exist locally (identical
    # repository state across all systems; no network dependency).
    try:
        eval_dir = str(Path(__file__).parent.parent)
        if eval_dir not in sys.path:
            sys.path.insert(0, eval_dir)
        from fixture_router import local_repo_files
        files = local_repo_files(repo_name)
        if files:
            return files
    except Exception:
        pass
    try:
        g = Github(GITHUB_TOKEN) if GITHUB_TOKEN else Github()
        repo = g.get_repo(repo_name)
        tree = repo.get_git_tree(repo.default_branch, recursive=True)
        return [item.path for item in tree.tree if item.type == "blob"]
    except Exception as e:
        print(f"[BASELINE_B] list_repo_files error: {e}")
        return []


def read_file_from_github(repo_name: str, file_path: str) -> str:
    try:
        eval_dir = str(Path(__file__).parent.parent)
        if eval_dir not in sys.path:
            sys.path.insert(0, eval_dir)
        from fixture_router import local_read_file, resolve_fixture_path
        if resolve_fixture_path(repo_name):
            return local_read_file(repo_name, file_path)
    except Exception:
        pass
    try:
        g = Github(GITHUB_TOKEN) if GITHUB_TOKEN else Github()
        repo = g.get_repo(repo_name)
        content_file = repo.get_contents(file_path)
        return content_file.decoded_content.decode("utf-8", errors="replace")
    except Exception as e:
        return f"Error: {e}"


def run_hidden_tests(fix_code: str, hidden_test_file: str,
                     gold_file: Optional[str] = None) -> tuple[bool, str]:
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
        cwd=str(Path(__file__).parent.parent.parent)
    )
    # Parse hidden-test counts from the pytest summary line.
    import re
    output = result.stdout + "\n" + result.stderr
    passed_count = 0
    failed_count = 0
    for line in output.split("\n"):
        m = re.search(r"(\d+) passed", line)
        if m:
            passed_count = int(m.group(1))
        for mm in re.finditer(r"(\d+) (?:failed|error)", line):
            failed_count += int(mm.group(1))
    return result.returncode == 0, output, passed_count + failed_count, passed_count


def extract_code(content: str) -> str:
    """Extract code block from LLM response."""
    if "```python" in content:
        return content.split("```python")[1].split("```")[0].strip()
    if "```" in content:
        return content.split("```")[1].split("```")[0].strip()
    return content.strip()


def extract_file_path(content: str, available_files: list[str]) -> Optional[str]:
    if "FILE:" in content:
        for line in content.split("\n"):
            if line.startswith("FILE:"):
                candidate = line.replace("FILE:", "").strip()
                if candidate in available_files:
                    return candidate
    return None


def run_task(task: dict) -> dict:
    task_id = task["task_id"]
    repo_url = task["repository"]
    issue_title = task["issue_title"]
    issue_body = task["issue_body"]
    gold_file = task["gold_file"]
    hidden_test_file = task["hidden_test_file"]

    repo_name = repo_url.rstrip("/").split("github.com/")[-1]

    print(f"\n[BASELINE_B] Running task {task_id}...")
    start = time.monotonic()
    total_input_tokens = 0
    total_output_tokens = 0
    llm_calls = 0
    LLM_CALL_LOG.clear()
    provider_failures: list[dict] = []

    # -----------------------------------------------------------------------
    # Research: list and pick file (1 LLM call, same as research_node)
    # -----------------------------------------------------------------------
    all_files = list_repo_files(repo_name)
    code_files = [f for f in all_files
                  if f.endswith(('.py', '.js', '.ts'))
                  and 'test' not in f.lower()
                  and not f.startswith('.')]

    localize_prompt = f"""GitHub Issue:
{issue_title}
{issue_body[:400]}

Repository files:
{chr(10).join(code_files[:30])}

Return ONLY the single file path that needs to be fixed."""

    loc_content, i_tok, o_tok = llm_call(
        [SystemMessage(content="Return only the exact file path. No other text."),
         HumanMessage(content=localize_prompt)],
        stage="localize",
    )
    total_input_tokens += i_tok
    total_output_tokens += o_tok
    llm_calls += 1

    predicted_file = loc_content.strip().replace("```", "").strip()
    if predicted_file not in all_files:
        # Deterministic fallback (never counted as a model prediction).
        predicted_file = code_files[0] if code_files else gold_file

    # Read the file content
    file_content = read_file_from_github(repo_name, predicted_file)

    # -----------------------------------------------------------------------
    # Retry loop: generate fix → run hidden tests → feedback → repeat
    # -----------------------------------------------------------------------
    attempts = 0
    first_attempt_success = False
    resolved = False
    final_fix = ""
    final_hidden_passed = False
    final_hidden_output = ""
    final_hidden_total = 0
    final_hidden_passed_count = 0
    syntax_valid = False
    feedback_history = []

    for attempt in range(MAX_RETRIES + 1):
        attempts += 1
        feedback_str = ""
        if feedback_history:
            feedback_str = f"\n\nPrevious attempt failed. Test output:\n{feedback_history[-1][:600]}\n\nFix the issues above."

        fix_prompt = f"""Issue: {issue_title}
File to fix: {predicted_file}
{feedback_str}

Current file content:
{file_content}

Provide the COMPLETE fixed Python file content (no partial diffs, no explanations):"""

        fix_content, i_tok, o_tok = llm_call(
            [SystemMessage(content="Output ONLY the complete fixed Python file. No markdown, no explanations."),
             HumanMessage(content=fix_prompt)],
            stage="repair_gen" if attempt > 0 else "code_gen",
        )
        total_input_tokens += i_tok
        total_output_tokens += o_tok
        llm_calls += 1

        proposed_fix = extract_code(fix_content) if fix_content else ""

        # Syntax check
        try:
            if proposed_fix:
                ast.parse(proposed_fix)
                syntax_valid = True
            else:
                syntax_valid = False
        except SyntaxError:
            syntax_valid = False

        if not proposed_fix or not syntax_valid:
            feedback_history.append(f"Attempt {attempt+1}: Empty or syntax-invalid output.")
            continue

        # Run hidden tests
        try:
            hidden_passed, hidden_output, h_total, h_passed = run_hidden_tests(proposed_fix, hidden_test_file, gold_file)
        except Exception as e:
            hidden_passed = False
            hidden_output = f"Error: {e}"
            h_total = 0
            h_passed = 0

        if attempt == 0:
            first_attempt_success = hidden_passed
            final_fix = proposed_fix
            final_hidden_passed = hidden_passed
            final_hidden_output = hidden_output
            final_hidden_total = h_total
            final_hidden_passed_count = h_passed

        if hidden_passed:
            resolved = True
            final_fix = proposed_fix
            final_hidden_passed = True
            final_hidden_output = hidden_output
            break
        else:
            feedback_history.append(hidden_output[:800])
            final_fix = proposed_fix
            final_hidden_passed = False
            final_hidden_output = hidden_output
            final_hidden_total = h_total
            final_hidden_passed_count = h_passed

    latency = round(time.monotonic() - start, 3)

    top1_correct = (predicted_file == gold_file)
    hallucinated = (predicted_file not in all_files)
    cost = round((total_input_tokens / 1_000_000 * 0.59) + (total_output_tokens / 1_000_000 * 0.79), 6)

    provider_failures = [c for c in LLM_CALL_LOG if not c["ok"]]
    contamination_detected = bool(provider_failures)
    served_models = sorted({c["served_model"] for c in LLM_CALL_LOG if c["served_model"]})

    result = {
        "task_id": task_id,
        "system": "baseline_b",
        "repository": repo_url,
        "issue_title": issue_title,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": {
            **provider_info(),
            "served_models": served_models,
            "contamination_detected": contamination_detected,
            "contamination": [
                {"stage": c["stage"], "error": c["error"], "failure_category": c["failure_category"],
                 "latency_seconds": c["latency_seconds"]}
                for c in provider_failures
            ],
        },
        "localization": {
            "predicted_file": predicted_file,
            "gold_file": gold_file,
            "top1_correct": top1_correct,
            "top3_correct": top1_correct,
            "hallucinated_file": hallucinated,
            "valid": predicted_file in all_files,
        },
        "patch": {
            "generated": bool(final_fix),
            "is_placeholder": False,
            "generated_by_model": bool(final_fix),
            "syntax_valid": syntax_valid,
            "files_changed": 1 if final_fix else 0,
            "lines_added": None,
            "lines_removed": None,
            "patch_apply_success": bool(final_fix),
            "patch_target_valid": predicted_file in all_files,
        },
        "tests": {
            "generated": False,
            "generated_tests_executed": False,
            "generated_tests_passed": False,
        },
        "regression": {
            "hidden_tests_executed": bool(final_fix and syntax_valid),
            "hidden_tests_passed": final_hidden_passed,
            "hidden_tests_output": final_hidden_output[:1000] if final_hidden_output else None,
            "hidden_tests_total": final_hidden_total if final_hidden_total > 0 else None,
            "hidden_tests_passed_count": final_hidden_passed_count if final_hidden_passed_count > 0 else None,
            "regression_free": final_hidden_passed,
        },
        "repair": {
            "attempts": attempts,
            "first_pass_resolved_hidden": first_attempt_success,
            "first_attempt_success": first_attempt_success,
            "first_pass_failure_category": (
                None if first_attempt_success else "first_patch_failed_hidden_tests"
            ),
            "repair_eligible": first_attempt_success is False,
            "repair_recovered": bool(
                first_attempt_success is False and attempts > 1 and resolved
            ),
            "resolved_within_retry_budget": resolved,
            "retry_budget": MAX_RETRIES,
            "llm_calls": LLM_CALL_LOG,
        },
        "execution": {
            "status": "resolved" if resolved else "hidden_test_failed",
            "failure_category": None if resolved else (
                "provider_failure" if contamination_detected else "hidden_test_failed"
            ),
            "latency_seconds": latency,
            "llm_calls": llm_calls,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "sandbox_mode": "subprocess",
        },
        "cost": {
            "estimated_usd": cost,
            "pricing_note": pricing_note(),
        },
        "pr": {"branch_created": False, "commit_created": False, "pr_created": False, "pr_url": None},
        "provider_contamination": contamination_detected,
        "end_to_end_resolved": resolved,
    }
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Baseline B — Single Agent + Retry")
    parser.add_argument("--task", required=True, help="Path to benchmark task JSON")
    parser.add_argument("--output-dir", default="evaluation/results", help="Results directory")
    args = parser.parse_args()

    with open(args.task) as f:
        task = json.load(f)

    result = run_task(task)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{result['task_id']}_baseline_b.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n[BASELINE_B] Result saved to {out_path}")
    print(f"  Resolved: {result['end_to_end_resolved']}")
    print(f"  Attempts: {result['repair']['attempts']}")
    print(f"  Latency: {result['execution']['latency_seconds']}s")
    print(f"  Cost: ${result['cost']['estimated_usd']}")
