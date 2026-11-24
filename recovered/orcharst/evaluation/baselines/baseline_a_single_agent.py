"""
evaluation/baselines/baseline_a_single_agent.py

BASELINE A — Single Agent (No Research, No Retry)

Given:
  - issue title
  - issue body
  - repository file listing

A single LLM is asked to:
  1. Identify the file to fix
  2. Generate the fix code

NO multi-agent orchestration, NO retry, NO test generation.

This is the simplest possible baseline.
"""

from __future__ import annotations

import os
import sys
import ast
import difflib
import json
import time
import types
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

# Windows consoles often default to cp1252; force UTF-8 so unicode never crashes.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "github-issue-agent"))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / "github-issue-agent" / ".env")

from langchain_core.messages import SystemMessage, HumanMessage
from github import Github
from agent.provider import get_chat_model, pricing_note


GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()


def get_llm():
    """NaraRouter model, same provider/model as every other evaluated system."""
    return get_chat_model()


def llm_call(messages) -> tuple[str, int, int]:
    """Make an LLM call, return (content, input_tokens, output_tokens)."""
    try:
        llm = get_llm()
        res = llm.invoke(messages)
        content = str(res.content)
        usage = getattr(res, "usage_metadata", None) or getattr(res, "response_metadata", {})
        input_tokens = 0
        output_tokens = 0
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
            output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
        return content, int(input_tokens), int(output_tokens)
    except Exception as e:
        print(f"[BASELINE_A] LLM error: {e}")
        raise


def list_repo_files(repo_name: str) -> list[str]:
    # Local fixture first: benchmark repos only exist locally (identical
    # repository state across all systems; no network dependency).
    try:
        if str(REPO_ROOT / "evaluation") not in sys.path:
            sys.path.insert(0, str(REPO_ROOT / "evaluation"))
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
        print(f"[BASELINE_A] list_repo_files error: {e}")
        return []


def read_file(repo_name: str, file_path: str) -> str:
    try:
        if str(REPO_ROOT / "evaluation") not in sys.path:
            sys.path.insert(0, str(REPO_ROOT / "evaluation"))
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


def run_hidden_tests(task_id: str, fix_code: str, hidden_test_file: str,
                     gold_file: Optional[str] = None) -> tuple[bool, str, int, int]:
    """
    Run the hidden evaluation tests against the agent's proposed fix.
    Returns (passed, output, total_tests, passed_count).
    """
    env = os.environ.copy()
    env["EVAL_FIX_CODE"] = fix_code
    if gold_file:
        # e.g. "src/pagination.py" -> "src.pagination" so the conftest can
        # materialize the fix under its real package path (tasks 006-030).
        env["EVAL_FIX_MODULE"] = gold_file.replace("\\", "/").replace("/", ".").removesuffix(".py")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", hidden_test_file,
         "--disable-warnings", "-v", "--tb=short", "-q"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        cwd=str(Path(__file__).parent.parent.parent)
    )
    passed = result.returncode == 0
    output = result.stdout + "\n" + result.stderr

    # Count total/passed from pytest output
    total = 0
    passed_count = 0
    for line in output.split("\n"):
        if " passed" in line or " failed" in line or " error" in line:
            import re
            m = re.search(r"(\d+) passed", line)
            if m:
                passed_count = int(m.group(1))
            m = re.search(r"(\d+) (?:passed|failed|error)", line)
            if m:
                # rough total from summary
                pass
        if line.strip().endswith("passed") or "passed" in line:
            m = re.search(r"(\d+) passed", line)
            if m:
                passed_count = int(m.group(1))

    return passed, output, total, passed_count


def run_task(task: dict) -> dict:
    """Run Baseline A on a single task. Returns a result dict."""
    task_id = task["task_id"]
    repo_url = task["repository"]
    issue_title = task["issue_title"]
    issue_body = task["issue_body"]
    gold_file = task["gold_file"]
    hidden_test_file = task["hidden_test_file"]

    # Extract repo name from URL
    repo_name = repo_url.rstrip("/").split("github.com/")[-1]

    print(f"\n[BASELINE_A] Running task {task_id}...")
    start = time.monotonic()
    total_input_tokens = 0
    total_output_tokens = 0
    llm_calls = 0

    # -----------------------------------------------------------------------
    # Step 1: List repo files
    # -----------------------------------------------------------------------
    all_files = list_repo_files(repo_name)
    code_files = [f for f in all_files
                  if f.endswith(('.py', '.js', '.ts', '.java'))
                  and 'test' not in f.lower()
                  and not f.startswith('.')]

    # -----------------------------------------------------------------------
    # Step 2: Single LLM call — localize + generate fix
    # -----------------------------------------------------------------------
    prompt = f"""You are an expert software developer. Fix the following GitHub issue.

Issue Title: {issue_title}
Issue Body:
{issue_body[:800]}

Repository files available:
{chr(10).join(code_files[:30])}

Instructions:
1. Identify the SINGLE file that needs to be changed.
2. Output the COMPLETE fixed content of that file.

Format your response EXACTLY as:
FILE: <exact file path>
```python
<complete fixed file content here>
```
"""
    content, i_tok, o_tok = llm_call(
        [SystemMessage(content="You are an expert software developer. Fix the bug exactly as described."),
         HumanMessage(content=prompt)]
    )
    total_input_tokens += i_tok
    total_output_tokens += o_tok
    llm_calls += 1

    # Parse response
    predicted_file = None
    proposed_fix = ""
    if "FILE:" in content:
        lines = content.split("\n")
        for line in lines:
            if line.startswith("FILE:"):
                predicted_file = line.replace("FILE:", "").strip()
                break
    if "```python" in content:
        proposed_fix = content.split("```python")[1].split("```")[0].strip()
    elif "```" in content:
        proposed_fix = content.split("```")[1].split("```")[0].strip()
    else:
        # Try to extract anything after the FILE: line
        if predicted_file and predicted_file in content:
            idx = content.find(predicted_file)
            proposed_fix = content[idx + len(predicted_file):].strip()

    latency = round(time.monotonic() - start, 3)

    # -----------------------------------------------------------------------
    # Evaluate localization
    # -----------------------------------------------------------------------
    top1_correct = (predicted_file == gold_file) if predicted_file else False
    # A null prediction is NOT a hallucination; a non-null prediction that is
    # not a real file in the repo IS a hallucination.
    hallucinated = (predicted_file is not None and predicted_file not in all_files)

    # -----------------------------------------------------------------------
    # Syntax check
    # -----------------------------------------------------------------------
    syntax_valid = False
    if proposed_fix:
        try:
            ast.parse(proposed_fix)
            syntax_valid = True
        except SyntaxError:
            syntax_valid = False

    # -----------------------------------------------------------------------
    # Hidden test evaluation
    # -----------------------------------------------------------------------
    hidden_passed = False
    hidden_output = ""
    hidden_total = 0
    hidden_passed_count = 0
    if proposed_fix and syntax_valid:
        try:
            hidden_passed, hidden_output, hidden_total, hidden_passed_count = run_hidden_tests(
                task_id, proposed_fix, hidden_test_file, gold_file
            )
        except Exception as e:
            hidden_output = f"Error running hidden tests: {e}"

    # -----------------------------------------------------------------------
    # Cost
    # -----------------------------------------------------------------------
    cost = round((total_input_tokens / 1_000_000 * 0.59) + (total_output_tokens / 1_000_000 * 0.79), 6)

    result = {
        "task_id": task_id,
        "system": "baseline_a",
        "repository": repo_url,
        "issue_title": issue_title,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "localization": {
            "predicted_file": predicted_file,
            "gold_file": gold_file,
            "top1_correct": top1_correct,
            "top3_correct": top1_correct,  # only 1 file predicted
            "hallucinated_file": hallucinated,
        },
        "patch": {
            "generated": bool(proposed_fix),
            "is_placeholder": False,
            "syntax_valid": syntax_valid,
            "files_changed": 1 if proposed_fix else 0,
            "lines_added": None,
            "lines_removed": None,
            "patch_apply_success": bool(proposed_fix),
        },
        "tests": {
            "generated": False,
            "generated_tests_executed": False,
            "generated_tests_passed": False,
        },
        "regression": {
            "hidden_tests_executed": bool(proposed_fix and syntax_valid),
            "hidden_tests_passed": hidden_passed,
            "hidden_tests_output": hidden_output[:1000] if hidden_output else None,
            "regression_free": hidden_passed,
        },
        "repair": {
            "attempts": 1,
            "first_attempt_success": hidden_passed,
            "resolved_within_retry_budget": hidden_passed,
            "retry_budget": 0,
        },
        "execution": {
            "status": "resolved" if hidden_passed else ("patch_failed" if not proposed_fix else "hidden_test_failed"),
            "latency_seconds": latency,
            "llm_calls": llm_calls,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "sandbox_mode": "none",
        },
        "cost": {
            "estimated_usd": cost,
            "pricing_note": pricing_note(),
        },
        "pr": {"branch_created": False, "commit_created": False, "pr_created": False, "pr_url": None},
        "end_to_end_resolved": (bool(proposed_fix) and syntax_valid and hidden_passed),
    }
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Baseline A — Single Agent")
    parser.add_argument("--task", required=True, help="Path to benchmark task JSON")
    parser.add_argument("--output-dir", default="evaluation/results", help="Results directory")
    args = parser.parse_args()

    with open(args.task) as f:
        task = json.load(f)

    result = run_task(task)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{result['task_id']}_baseline_a.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n[BASELINE_A] Result saved to {out_path}")
    print(f"  Resolved: {result['end_to_end_resolved']}")
    print(f"  Latency: {result['execution']['latency_seconds']}s")
    print(f"  Cost: ${result['cost']['estimated_usd']}")
