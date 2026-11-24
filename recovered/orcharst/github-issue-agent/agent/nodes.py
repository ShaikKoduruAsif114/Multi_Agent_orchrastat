import os
import sys
import json
import random
import string
import difflib
import ast
import concurrent.futures
import time
import re
from typing import Dict, Any, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from langchain_core.messages import SystemMessage, HumanMessage
from agent.state import AgentState
from agent.workflow_state import log_step
from agent.instrumentation import (
    record_llm_call,
    record_sandbox_run,
    record_retry,
    set_retry_count,
    STAGE_CODE_GEN,
    STAGE_PLAN,
    STAGE_TEST_GEN,
)
from agent.provider import (
    get_chat_model,
    provider_name,
    request_timeout,
    classify_provider_failure,
)
from agent.tools import (
    get_github_issue,
    list_repo_files,
    read_file,
    search_code,
    scan_for_bugs,
    create_branch,
    commit_changes,
    open_pull_request,
)


# ---------------------------------------------------------------------------
# Known placeholder/stub markers: a "fix" containing these was NOT produced
# by the model as a genuine repair. Kept as a hard quality gate.
# ---------------------------------------------------------------------------
_PLACEHOLDER_MARKERS = (
    "def resolve_issue():",
    "Automated code fix applied",
    "# Proposed Fix for",
    "Updated logic for",
)


def _is_placeholder(code: str) -> bool:
    if not code or not code.strip():
        return True
    return any(m in code for m in _PLACEHOLDER_MARKERS)


def get_llm():
    """Initialize the configured provider without automatic fallback."""
    return get_chat_model()


def invoke_llm_with_timeout(messages, timeout_sec=30.0, stage=""):
    """Invoke the configured LLM once with a timeout. Strict failure semantics.

    - Zero client retries. One call, exact errors.
    - On failure: records the call with the classified failure category.
    - Under AGENT_STRICT_LLM=1 (controlled evaluation) the error is re-raised;
      the caller never receives fabricated/empty content that could be
      mistaken for model output.
    - Without strict mode (interactive production use) returns '' so the
      workflow can degrade gracefully; the empty result is never counted as a
      successful generation.
    """
    timeout_sec = request_timeout(timeout_sec)
    started = time.monotonic()
    call_stage = stage or "unlabeled"
    strict = os.getenv("AGENT_STRICT_LLM", "").strip() == "1"
    try:
        llm = get_llm()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(llm.invoke, messages)
            res = future.result(timeout=timeout_sec)
            content = str(res.content)
            usage = getattr(res, "usage_metadata", None) or getattr(res, "response_metadata", {})
            input_tokens = 0
            output_tokens = 0
            if isinstance(usage, dict):
                input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
                output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
            response_metadata = getattr(res, "response_metadata", {})
            served_model = ""
            http_status = None
            if isinstance(response_metadata, dict):
                served_model = str(response_metadata.get("model", "") or response_metadata.get("model_name", ""))
                http_status = response_metadata.get("http_status")
            if not served_model:
                served_model = res.__class__.__name__
            record_llm_call(call_stage, started, time.monotonic(), True, input_tokens, output_tokens,
                            served_model=served_model, http_status=http_status)
            return (content, input_tokens, output_tokens) if stage else content
    except concurrent.futures.TimeoutError:
        elapsed = time.monotonic() - started
        err = f"provider_timeout: LLM call exceeded timeout limit ({elapsed:.1f}s)"
        print(f"\n[LLM TIMEOUT] {err}")
        record_llm_call(call_stage, started, time.monotonic(), False, error=err)
        if strict:
            raise RuntimeError(err)
        return ("", 0, 0) if stage else ""
    except Exception as e:
        err = str(e)
        category, _ = classify_provider_failure(e)
        print(f"\n[LLM ERROR] ({category}) {err}")
        record_llm_call(call_stage, started, time.monotonic(), False, error=err)
        if strict:
            raise
        return ("", 0, 0) if stage else ""


def strip_code_block(content: str) -> str:
    """Extract a Python code payload from a model response."""
    if "```python" in content:
        return content.split("```python")[1].split("```")[0].strip() + "\n"
    if "```" in content:
        return content.split("```")[1].split("```")[0].strip() + "\n"
    return content.strip() + "\n"


def compute_patch_metadata(original: str, fixed: str) -> Dict[str, Any]:
    """Compute unified diff + churn for the patch-quality record."""
    if not original or original.startswith("Error"):
        original = ""
    diff = "\n".join(difflib.unified_diff(
        (original or "").splitlines(), (fixed or "").splitlines(),
        fromfile="original", tofile="fixed", lineterm="",
    ))
    added = removed = 0
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return {"patch_diff": diff[:4000], "lines_added": added, "lines_removed": removed}


def input_node(state: AgentState) -> Dict[str, Any]:
    """Node 1: Collect and validate user inputs and detect execution mode."""
    session_id = state.get("session_id", "default")
    repo_url = state.get("repo_url", "").strip()
    issue_number = state.get("issue_number", 0)
    problem_description = state.get("problem_description", "").strip()
    token = state.get("token", "").strip()

    log_step("Step 1/8: Validating execution settings and target repository URL...", "sys", session_id)

    errors = list(state.get("errors", []))

    if not repo_url or "github.com/" not in repo_url.lower():
        raise ValueError("Invalid Repository URL. Please provide a valid GitHub repository link (e.g., https://github.com/owner/repo).")

    # Validate that it has at least owner/repo
    parts = repo_url.rstrip("/").split("github.com/")[-1].split("/")
    if len(parts) < 2:
        raise ValueError("Invalid Repository URL format. Must include owner and repository name.")

    mode = "issue" if (issue_number and int(issue_number) > 0) else "smart"

    return {
        "repo_url": repo_url,
        "issue_number": issue_number,
        "token": token,
        "problem_description": problem_description,
        "mode": mode,
        "errors": errors,
    }


def fetch_node(state: AgentState) -> Dict[str, Any]:
    """Node 2: Get problem details from GitHub issue or description/codebase scan."""
    session_id = state.get("session_id", "default")
    repo_url = state["repo_url"]
    token = state.get("token", "")
    mode = state.get("mode", "smart")
    issue_number = state.get("issue_number", 0)
    problem_description = state.get("problem_description", "")
    errors = list(state.get("errors", []))

    log_step(f"Step 2/8: Fetching problem details in [{mode.upper()} MODE]...", "sys", session_id)

    issue_title = ""
    issue_body = ""

    if mode == "issue":
        res = get_github_issue.invoke({
            "repo_url": repo_url,
            "issue_number": issue_number,
            "token": token
        })
        if isinstance(res, dict) and "error" in res:
            errors.append(res["error"])
            issue_title = f"Issue #{issue_number}"
            issue_body = f"Could not fetch issue content: {res['error']}"
        else:
            issue_title = res.get("title", f"Issue #{issue_number}")
            issue_body = res.get("body", "")
    else:
        if problem_description:
            issue_title = f"Smart Mode Fix: {problem_description[:50]}"
            issue_body = problem_description
        else:
            files = scan_for_bugs.invoke({"repo_url": repo_url, "token": token})
            issue_title = "Smart Mode: Codebase Maintenance & Bug Scan"
            issue_body = f"Scanned codebase. Identified candidate files: {', '.join(files[:5])}"

    return {
        "issue_title": issue_title,
        "issue_body": issue_body,
        "errors": errors,
    }


def research_node(state: AgentState) -> Dict[str, Any]:
    """Node 3: Fast codebase research — dispatch to the staged V2 pipeline when enabled."""
    if os.getenv("AGENT_LOCALIZATION_V2", "").strip() == "1":
        from agent.localization_v2 import research_node_v2
        return research_node_v2(state)

    session_id = state.get("session_id", "default")
    repo_url = state["repo_url"]
    token = state.get("token", "")

    log_step("Step 3/8: Researching repository tree to locate target source files...", "sys", session_id)

    all_files = list_repo_files.invoke({"repo_url": repo_url, "token": token})
    if not isinstance(all_files, list) or (all_files and all_files[0].startswith("Error")):
        relevant_files = ["src/main.py"]
        evidence = {"issue": "", "target_file": relevant_files[0], "repository_candidates": []}
    else:
        code_files = [
            f for f in all_files
            if f.endswith(('.py', '.js', '.ts', '.java'))
            and not f.startswith('.')
            and 'test' not in f.lower()
        ]

        issue_text = state.get("issue_title", "") + "\n" + state.get("issue_body", "")

        prompt = f"""Given this GitHub Issue:
{issue_text[:500]}

And these repository files:
{chr(10).join(code_files)}

Which SINGLE file path is the most likely file that needs to be edited to fix this issue?
Return ONLY the exact file path from the list, nothing else."""

        llm_result = invoke_llm_with_timeout(
            [SystemMessage(content="You are an expert developer. Return only the exact file path. Do not include markdown or explanations."),
             HumanMessage(content=prompt)],
            timeout_sec=10.0
        )

        selected = llm_result.strip() if isinstance(llm_result, str) and llm_result else ""
        if "```" in selected:
            selected = selected.replace("```", "").strip()

        if selected in all_files:
            relevant_files = [selected]
            source = "llm_exact_match"
        else:
            # Deterministic fallback ranked by issue-token overlap with the
            # filename (alphabetical-first was arbitrary and picked __init__.py).
            issue_tokens = set(re.findall(r"[a-z0-9]+", issue_text.lower()))
            ranked = sorted(
                code_files,
                key=lambda f: -len(issue_tokens & set(re.findall(r"[a-z0-9]+", f.rsplit("/", 1)[-1].lower()))),
            )
            relevant_files = ranked[:3] if ranked else (code_files[:3] if code_files else all_files[:3])
            source = "deterministic_fallback"

        target = relevant_files[0] if relevant_files else ""
        target_content = read_file.invoke({"repo_url": repo_url, "file_path": target, "token": token})
        evidence = {
            "issue": issue_text[:1500],
            "target_file": target,
            "selection_source": source,
            "target_source_excerpt": (target_content or "")[:1500] if not target_content.startswith("Error") else "",
        }

    log_step(f"Target files selected for fix: {', '.join(relevant_files)}", "info", session_id)

    return {
        "relevant_files": relevant_files,
        "localization_evidence": evidence,
        "llm_calls": state.get("llm_calls", 0)
    }


def _extract_repair_context(state: AgentState, test_results: str) -> Dict[str, Any]:
    """Extract the exact failure signal for a targeted repair.

    Pulls the failing test ids, the assertion message with expected/actual,
    and a generic error line out of pytest output.
    """
    failing = re.findall(r"FAILED ([^\s:]+)::([^\s]+)", test_results or "")
    if not failing:
        failing = [(name, "") for name in re.findall(r"(test_[^\s:]+)[^\s]*\s+FAILED", test_results or "")]
    assert_m = re.search(r"AssertionError: (.+)", test_results or "")
    expected = actual = ""
    if assert_m:
        m = re.search(r"assert (.+?) == (.+?)(?:\s|$)", assert_m.group(1))
        if m:
            expected, actual = m.group(2), m.group(1)
    error_line = re.search(r"[Ee]rror: (.+)", test_results or "")

    failing_ids = [f"{a}::{b}" if b else str(a) for a, b in failing[:6]]

    return {
        "failing_tests": failing_ids,
        "assertion_message": assert_m.group(1)[:300] if assert_m else "",
        "expected": expected[:120],
        "actual": actual[:120],
        "error_line": error_line.group(1)[:300] if error_line else "",
        "output_excerpt": (test_results or "")[:1200],
        "attempt_number": state.get("retry_count", 0) + 1,
        "previous_repairs": state.get("repair_history", []),
    }


def code_writer_node(state: AgentState) -> Dict[str, Any]:
    """Node 4: Evidence-grounded code fix writer with patch-quality gates.

    Strict semantics:
    - The ONLY source of a patch is a real LLM response. There is no stub,
      no placeholder, and no synthetic fallback. If the model call fails or
      returns unusable content, the node raises (strict mode) so the run is
      classified by its true cause.
    - Patch-quality gates: non-empty, non-placeholder, syntax-valid,
      target file exists in the repository listing.
    """
    session_id = state.get("session_id", "default")
    repo_url = state["repo_url"]
    token = state.get("token", "")
    issue_title = state.get("issue_title", "")
    issue_body = state.get("issue_body", "")
    relevant_files = state.get("relevant_files", ["src/fix.py"])
    messages = list(state.get("messages", []))
    llm_calls = state.get("llm_calls", 0)
    strict = os.getenv("AGENT_STRICT_LLM", "").strip() == "1"

    target_file = relevant_files[0] if relevant_files else "src/fix.py"
    is_repair = state.get("retry_count", 0) > 0
    log_step(f"Step 4/8: Generating {'targeted repair' if is_repair else 'code fix'} for `{target_file}` (attempt {state.get('retry_count', 0) + 1})...",
             "info", session_id)

    original_content = read_file.invoke({"repo_url": repo_url, "file_path": target_file, "token": token})
    snippet = original_content if not original_content.startswith("Error") else ""

    # ---- Gather repair context -------------------------------------------
    repair_context: Dict[str, Any] = {}
    last_test_results = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and "Feedback:" in msg.content:
            feedback = msg.content
            if "Test Failure" in feedback:
                last_test_results = feedback.split("Feedback:", 1)[-1]
            break
    if is_repair and last_test_results:
        repair_context = _extract_repair_context(state, last_test_results)

    plan = state.get("repair_plan", "")
    evidence = state.get("localization_evidence", {})

    # ---- Prompt -----------------------------------------------------------
    if is_repair and repair_context:
        prior = json.dumps(repair_context.get("previous_repairs", [])[-3:], ensure_ascii=True)
        system_prompt = (
            "You are an expert software engineer performing a TARGETED repair. "
            "The previous patch failed the shown tests. Diagnose the exact failing "
            "behavior from the traceback/assertion and change ONLY what is needed "
            "to fix it, preserving the rest of the file and its public interface. "
            "Output the complete fixed Python file. No explanations."
        )
        prompt = f"""Issue: {issue_title[:150]}
Target File: {target_file}

Current file content:
{snippet}

Previous patch failed with this exact test output:
{repair_context.get('output_excerpt', '')[:1200]}

Failing tests: {repair_context.get('failing_tests', [])}
Assertion: {repair_context.get('assertion_message', '')}
Expected: {repair_context.get('expected', '')}  Actual: {repair_context.get('actual', '')}

Previous repair attempts (do not repeat failed strategies):
{prior[:1500]}

Repair plan:
{plan[:1500]}

Provide the COMPLETE fixed code for this file, applying the targeted change."""
        stage = "repair_gen"
    else:
        system_prompt = (
            "You are an expert software developer fixing a bug. Make the minimal "
            "change that implements the intended behavior described in the issue. "
            "Preserve existing interfaces, naming, and project style. Do not "
            "refactor unrelated code. Output concise Python code only. No explanations."
        )
        prompt = f"""Issue: {issue_title[:150]}
{issue_body[:600]}

Target File: {target_file}

Evidence:
{json.dumps(evidence, ensure_ascii=True)[:3000]}

Repair plan:
{plan[:3000]}

Current file content:
{snippet}

Provide the complete fixed code for this file."""
        stage = STAGE_CODE_GEN

    llm_content, _, _ = invoke_llm_with_timeout(
        [SystemMessage(content=system_prompt), HumanMessage(content=prompt)],
        timeout_sec=request_timeout(18.0),
        stage=stage,
    )
    if llm_content:
        llm_calls += 1

    # ---- Patch-quality gates ----------------------------------------------
    if not llm_content or not llm_content.strip():
        msg = f"{stage}_empty: model returned no content"
        if strict:
            raise RuntimeError(msg)
        proposed_fix = ""
        generated_by_model = False
    else:
        proposed_fix = strip_code_block(llm_content)
        generated_by_model = True

    syntax_valid = False
    if proposed_fix:
        try:
            ast.parse(proposed_fix)
            syntax_valid = True
        except SyntaxError as e:
            log_step(f"[PATCH GATE] Syntax invalid: {e}", "warn", session_id)

    placeholder = _is_placeholder(proposed_fix)

    # Target validity: the file we claim to fix must exist in the repo listing.
    all_files = list_repo_files.invoke({"repo_url": repo_url, "token": token})
    target_valid = target_file in all_files if isinstance(all_files, list) else False

    patch_meta = compute_patch_metadata(snippet, proposed_fix) if proposed_fix else {}

    gates = {
        "generated_by_model": generated_by_model,
        "non_empty": bool(proposed_fix.strip()),
        "non_placeholder": not placeholder,
        "syntax_valid": syntax_valid,
        "target_file_exists": target_valid,
    }
    if strict and not all(gates.values()):
        failed = [k for k, v in gates.items() if not v]
        raise RuntimeError(f"patch_quality_gate_failed: {failed}")

    repair_attempts = list(state.get("repair_attempts", []))
    if is_repair and repair_context:
        repair_attempts.append({
            "attempt": state.get("retry_count", 0) + 1,
            "failure": repair_context,
            "stage": stage,
        })

    # Record the FIRST generated patch separately so the evaluation harness
    # can re-run hidden tests on it for true first-pass resolution (repair
    # may later replace this patch).
    first_patch_source = state.get("first_patch_source", "") or proposed_fix

    return {
        "proposed_fix": proposed_fix,
        "original_file_content": snippet,
        "first_patch_source": first_patch_source,
        "patch_placeholder": placeholder,
        "patch_apply_success": bool(proposed_fix) and syntax_valid and target_valid,
        "patch_target_valid": target_valid,
        "generated_code_is_model": generated_by_model,
        "syntax_valid": syntax_valid,
        "repair_attempts": repair_attempts,
        **patch_meta,
        "llm_calls": llm_calls,
    }


def plan_node(state: AgentState) -> Dict[str, Any]:
    """Create an evidence-grounded implementation plan before code generation.

    Plan sections: root cause, intended behavior, target functions/classes,
    implementation strategy, edge cases, validation strategy.
    """
    target_file = (state.get("relevant_files") or ["src/fix.py"])[0]
    issue = f"{state.get('issue_title', '')}\n{state.get('issue_body', '')}"
    evidence = state.get("localization_evidence", {})
    target_source = evidence.get("target_source_excerpt", "")

    # On a repair pass, include the exact failure so the plan targets the bug.
    feedback = ""
    for msg in reversed(state.get("messages", []) or []):
        if isinstance(msg, HumanMessage) and "Feedback:" in msg.content:
            feedback = msg.content
            break

    feedback_block = f"\nFailure feedback from previous attempt:\n{feedback[:800]}" if feedback else ""
    prompt = f"""Create a concise repair plan for this issue.

Issue:
{issue[:1200]}

Target file: {target_file}

Evidence:
{json.dumps(evidence, ensure_ascii=True)[:3000]}

Target file source (excerpt):
{target_source[:1500]}
{feedback_block}

Return sections: root cause, intended behavior, target functions/classes,
implementation strategy, edge cases, validation strategy. Use only evidence
supported by the issue and repository evidence."""
    plan, _, _ = invoke_llm_with_timeout(
        [SystemMessage(content="You are a senior engineer writing a precise repair plan."),
         HumanMessage(content=prompt)],
        timeout_sec=request_timeout(18.0),
        stage=STAGE_PLAN,
    )
    return {"repair_plan": plan}


def test_writer_node(state: AgentState) -> Dict[str, Any]:
    """Node 5: Generate real pytest tests as DIAGNOSTIC AIDS for the repair loop.

    Generated tests never create benchmark success: they only decide whether
    the workflow iterates (repair) or proceeds. Hidden tests are the sole
    success signal, applied outside the graph by the evaluation harness.
    """
    session_id = state.get("session_id", "default")
    issue_title = state.get("issue_title", "Fix")
    proposed_fix = state.get("proposed_fix", "")
    relevant_files = state.get("relevant_files", ["src/fix.py"])
    target_file = relevant_files[0] if relevant_files else "fix.py"

    log_step(f"Step 5/8: Writing Pytest diagnostic tests for `{target_file}`...", "info", session_id)

    ext = os.path.splitext(target_file)[1].lower()
    # Convert 'src/bank_account.py' to 'src.bank_account' for correct absolute imports
    import_path = target_file.replace(".py", "").replace("/", ".").replace("\\", ".")

    if ext == ".py":
        system_prompt = """You are an expert Python test engineer. 
        Write real pytest tests that actually verify the code works.
        Never write assert True alone.
        Always test real behavior."""

        prompt = f"""Write a pytest test file for this code fix.

Issue being fixed: {issue_title}
Target file: {target_file}
Module name for imports: {import_path}

Code fix:
{proposed_fix[:1500]}

Requirements:
- Write at minimum 2 real test functions
- Use real assertions that can actually fail
- Do NOT write assert True as the only assertion
"""

        llm_content, _, _ = invoke_llm_with_timeout(
            [SystemMessage(content=system_prompt),
             HumanMessage(content=prompt)],
            timeout_sec=request_timeout(18.0),
            stage=STAGE_TEST_GEN,
        )
        llm_result = str(llm_content or "")

        if not llm_result or len(llm_result.strip()) <= 50:
            if os.getenv("AGENT_STRICT_LLM", "").strip() == "1":
                raise RuntimeError("test_gen_empty: LLM returned no usable generated tests")

        if isinstance(llm_result, str) and len(llm_result.strip()) > 50:
            tests_written = strip_code_block(llm_result)
        else:
            # No fabricated fallback tests: empty means the sandbox runs the
            # syntax smoke suite only (see subprocess_execution_node).
            tests_written = ""
    else:
        # Non-Python target: no meaningful pytest diagnostics can be written.
        tests_written = ""

    return {
        "tests_written": tests_written,
        "llm_calls": state.get("llm_calls", 0)
    }


def _run_pytest_suite(temp_dir: str, test_file: str = "test_auto_fix.py") -> Dict[str, Any]:
    """Run one pytest suite in a local subprocess and parse the outcome."""
    import subprocess

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "--disable-warnings", "-v", "--tb=short"],
            cwd=temp_dir, capture_output=True, text=True, timeout=60,
        )
        output_logs = (result.stdout or "") + "\n" + (result.stderr or "")
        passed = result.returncode == 0

        tests_total = tests_passed_count = tests_failed = 0
        summary = re.findall(r"(\d+) (passed|failed|error)", output_logs)
        for n, kind in summary:
            n = int(n)
            if kind == "passed":
                tests_passed_count = n
            elif kind in ("failed", "error"):
                tests_failed += n
        tests_total = tests_passed_count + tests_failed

        collection_error = "collected 0 items" in output_logs or "ERROR collecting" in output_logs
        category = "" if passed else ("test_collection_error" if collection_error else "generated_test_failure")
        return {
            "passed": passed, "output": output_logs,
            "tests_total": tests_total, "tests_passed_count": tests_passed_count,
            "tests_failed": tests_failed, "collection_error": collection_error,
            "failure_category": category, "timeout": False,
        }
    except subprocess.TimeoutExpired:
        out = "Local subprocess test execution timed out after 60 seconds"
        return {"passed": False, "output": out, "tests_total": 0, "tests_passed_count": 0,
                "tests_failed": 0, "collection_error": False,
                "failure_category": "test_execution_timeout", "timeout": True}
    except Exception as error:
        out = f"Local subprocess execution error: {error}"
        return {"passed": False, "output": out, "tests_total": 0, "tests_passed_count": 0,
                "tests_failed": 0, "collection_error": True,
                "failure_category": "test_execution_error", "timeout": False}


def subprocess_execution_node(state: AgentState) -> Dict[str, Any]:
    """Run generated diagnostic tests in the deterministic local subprocess sandbox."""
    import tempfile
    import shutil

    session_id = state.get("session_id", "default")
    proposed_fix = state.get("proposed_fix", "")
    tests_written = state.get("tests_written", "")
    target_file = (state.get("relevant_files") or ["src/fix.py"])[0]
    retry_count = state.get("retry_count", 0)
    temp_dir = tempfile.mkdtemp(prefix="agent_subprocess_")
    start = time.monotonic()
    outcome: Dict[str, Any] = {}
    try:
        target_path = os.path.join(temp_dir, *target_file.replace("\\", "/").split("/"))
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as handle:
            handle.write(proposed_fix)
        curr = temp_dir
        for part in target_file.replace("\\", "/").split("/")[:-1]:
            curr = os.path.join(curr, part)
            open(os.path.join(curr, "__init__.py"), "a", encoding="utf-8").close()
        if tests_written.strip():
            with open(os.path.join(temp_dir, "test_auto_fix.py"), "w", encoding="utf-8") as handle:
                handle.write(tests_written)
        else:
            # Syntax smoke suite: still executes the patch in a subprocess.
            with open(os.path.join(temp_dir, "test_auto_fix.py"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import ast\n\n"
                    "def test_fix_has_valid_syntax():\n"
                    f"    code = {repr(proposed_fix[:2000])}\n"
                    "    ast.parse(code)\n"
                )

        outcome = _run_pytest_suite(temp_dir, "test_auto_fix.py")
        tests_passed = outcome["passed"]
        output_logs = outcome["output"]
        record_sandbox_run(retry_count, "subprocess", start, time.monotonic(), tests_passed,
                           len(output_logs), tests_total=outcome["tests_total"],
                           tests_passed_count=outcome["tests_passed_count"],
                           tests_failed=outcome["tests_failed"],
                           collection_error=outcome["collection_error"],
                           failure_category=outcome["failure_category"])
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    messages = list(state.get("messages", []))
    if not tests_passed:
        retry_count += 1
        set_retry_count(retry_count)
        failure_category = outcome.get("failure_category", "generated_test_failure")
        record_retry(retry_count, reason=output_logs[:200], fixed=False,
                     failure_category=failure_category, triggered_by="generated_tests")
        messages.append(HumanMessage(content=f"Test Failure - Feedback: Analyze and repair using this output:\n{output_logs[:1200]}"))
    return {"tests_passed": tests_passed, "test_results": output_logs,
            "retry_count": retry_count, "messages": messages}


def human_approval_node(state: AgentState) -> Dict[str, Any]:
    """Node 7: Present work to human and request approval."""
    session_id = state.get("session_id", "default")
    issue_title = state.get("issue_title", "")
    relevant_files = state.get("relevant_files", [])
    proposed_fix = state.get("proposed_fix", "")
    tests_written = state.get("tests_written", "")
    retry_count = state.get("retry_count", 0)
    eval_mode = bool(state.get("eval_mode", False))

    from agent.workflow_state import get_session_state
    session_state = get_session_state(session_id)

    if eval_mode:
        print(f"\n[EVAL MODE] Auto-approving fix for {session_id} without interactive input.")
        human_approved = True
        feedback = ""
    else:
        is_web = state.get("is_web", False) or (session_state.get("status") in ["running", "waiting_approval"])

        if is_web:
            session_state["status"] = "waiting_approval"
            session_state["state"] = state
            session_state["user_decision"] = None

            print(f"\n[{session_id}] [WEB UI] Workflow paused at human_approval_node. Waiting for user approval on web interface...")

            while session_state.get("user_decision") is None:
                time.sleep(0.3)

            decision = session_state["user_decision"]
            human_approved = decision.get("approved", False)
            feedback = decision.get("feedback", "").strip()
            session_state["status"] = "running"

        else:
            print("\n" + "="*60)
            print("HUMAN APPROVAL REQUIRED")
            print("="*60)
            print(f"Issue: {issue_title}")
            print(f"Relevant Files: {', '.join(relevant_files)}")
            print("="*60)

            try:
                user_input = input("\nDo you approve this fix? (yes/no): ").strip().lower()
            except Exception:
                user_input = "yes"

            if user_input in ["yes", "y"]:
                human_approved = True
                feedback = ""
            else:
                human_approved = False
                try:
                    feedback = input("What should be changed / feedback for retry? ").strip()
                except Exception:
                    feedback = "Please improve code quality."

    if not human_approved:
        retry_count += 1
        set_retry_count(retry_count)
        record_retry(retry_count, reason=str(feedback)[:200], fixed=False,
                     failure_category="human_rejected", triggered_by="human_feedback")

    messages = list(state.get("messages", []))
    if feedback:
        messages.append(HumanMessage(content=f"Feedback: {feedback}"))

    return {
        "human_approved": human_approved,
        "retry_count": retry_count,
        "messages": messages
    }


def pr_node(state: AgentState) -> Dict[str, Any]:
    """Node 8: Create branch, commit fix + tests, and open pull request on GitHub."""
    repo_url = state["repo_url"]
    token = state.get("token", "")
    issue_title = state.get("issue_title", "Fix issue")
    issue_body = state.get("issue_body", "")
    proposed_fix = state.get("proposed_fix", "")
    tests_written = state.get("tests_written", "")
    relevant_files = state.get("relevant_files", ["fix.py"])
    errors = list(state.get("errors", []))

    if not token:
        errors.append("GitHub token required to open a pull request.")
        return {"pr_url": "", "errors": errors}

    rand_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    branch_name = f"fix/auto-issue-{rand_suffix}"

    res_branch = create_branch.invoke({
        "repo_url": repo_url,
        "branch_name": branch_name,
        "token": token
    })

    if isinstance(res_branch, str) and res_branch.startswith("Error"):
        errors.append(res_branch)
        return {"pr_url": "", "errors": errors}

    target_file = relevant_files[0] if relevant_files else "src/fix.py"
    files_to_commit = {
        target_file: proposed_fix,
        "tests/test_auto_fix.py": tests_written
    }

    commit_changes.invoke({
        "repo_url": repo_url,
        "branch": branch_name,
        "files": files_to_commit,
        "token": token
    })

    pr_body = f"""## Automated Fix by Autonomous GitHub Issue Agent

### Issue
{issue_title}

### Problem Description
{issue_body}

### Changes Made
- Proposed fix applied to `{target_file}`
- Pytest unit tests added to `tests/test_auto_fix.py`

---
*Generated by Autonomous GitHub Issue Agent powered by LangGraph & Llama 3.2*
"""

    pr_url = open_pull_request.invoke({
        "repo_url": repo_url,
        "branch": branch_name,
        "title": f"fix: {issue_title}",
        "body": pr_body,
        "token": token
    })

    return {
        "pr_url": str(pr_url),
        "errors": errors
    }