import json
import random
import string
from typing import Dict, Any
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from agent.state import AgentState
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


def get_llm():
    """Initialize Llama 3.2 via Ollama."""
    return ChatOllama(model="llama3.2", temperature=0)


def input_node(state: AgentState) -> Dict[str, Any]:
    """Node 1: Collect and validate user inputs and detect execution mode."""
    repo_url = state.get("repo_url", "").strip()
    issue_number = state.get("issue_number", 0)
    problem_description = state.get("problem_description", "").strip()
    token = state.get("token", "").strip()

    errors = list(state.get("errors", []))

    if not repo_url:
        errors.append("Repository URL is required.")

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
    repo_url = state["repo_url"]
    token = state.get("token", "")
    mode = state.get("mode", "smart")
    issue_number = state.get("issue_number", 0)
    problem_description = state.get("problem_description", "")
    errors = list(state.get("errors", []))

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
    else:  # smart mode
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
    """Node 3: Understand the codebase, find relevant files, and pinpoint changes."""
    repo_url = state["repo_url"]
    token = state.get("token", "")
    issue_title = state.get("issue_title", "")
    issue_body = state.get("issue_body", "")
    llm_calls = state.get("llm_calls", 0)

    # List files in repository
    all_files = list_repo_files.invoke({"repo_url": repo_url, "token": token})
    if not isinstance(all_files, list) or (all_files and all_files[0].startswith("Error")):
        relevant_files = []
    else:
        code_files = [f for f in all_files if f.endswith(('.py', '.js', '.ts', '.java', '.go', '.rs'))]
        relevant_files = code_files[:5] if code_files else all_files[:5]

    # Use LLM to pinpoint target files if files exist
    if all_files and not (isinstance(all_files, list) and all_files[0].startswith("Error")):
        try:
            llm = get_llm()
            prompt = f"""Given the following issue details and list of repository files, select up to 3 most relevant file paths to modify.
Issue Title: {issue_title}
Issue Body: {issue_body}

Files in Repo:
{json.dumps(all_files[:30])}

Return ONLY a valid JSON list of file path strings, e.g. ["path/to/file.py"]. Do not add explanation."""

            response = llm.invoke([HumanMessage(content=prompt)])
            llm_calls += 1
            content = str(response.content).strip()
            if "[" in content and "]" in content:
                json_str = content[content.find("["):content.rfind("]")+1]
                parsed = json.loads(json_str)
                if isinstance(parsed, list) and len(parsed) > 0:
                    relevant_files = parsed
        except Exception:
            pass

    return {
        "relevant_files": relevant_files,
        "llm_calls": llm_calls
    }


def code_writer_node(state: AgentState) -> Dict[str, Any]:
    """Node 4: Write the actual code fix based on code analysis and reviewer feedback."""
    repo_url = state["repo_url"]
    token = state.get("token", "")
    issue_title = state.get("issue_title", "")
    issue_body = state.get("issue_body", "")
    relevant_files = state.get("relevant_files", [])
    messages = list(state.get("messages", []))
    llm_calls = state.get("llm_calls", 0)

    # Read current content of relevant files
    file_contents = {}
    for fpath in relevant_files[:3]:
        content = read_file.invoke({"repo_url": repo_url, "file_path": fpath, "token": token})
        if not content.startswith("Error"):
            file_contents[fpath] = content

    feedback = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and "Feedback:" in msg.content:
            feedback = msg.content
            break

    llm = get_llm()
    system_prompt = "You are an expert software developer fixing a bug in a codebase."
    prompt = f"""Issue Title: {issue_title}
Issue Description: {issue_body}

Relevant File Contents:
{json.dumps(file_contents, indent=2)}

{f"Previous Feedback from Reviewer: {feedback}" if feedback else ""}

Provide the fixed code. Format your response clearly with target file path and the updated code."""

    try:
        response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=prompt)])
        llm_calls += 1
        proposed_fix = response.content
    except Exception as e:
        proposed_fix = f"# Error generating fix via LLM: {str(e)}"

    return {
        "proposed_fix": proposed_fix,
        "llm_calls": llm_calls
    }


def test_writer_node(state: AgentState) -> Dict[str, Any]:
    """Node 5: Write pytest unit tests covering the fix and edge cases."""
    proposed_fix = state.get("proposed_fix", "")
    issue_title = state.get("issue_title", "")
    llm_calls = state.get("llm_calls", 0)

    llm = get_llm()
    system_prompt = "You are an expert QA engineer writing pytest unit tests for Python code changes."
    prompt = f"""Issue: {issue_title}

Proposed Code Fix:
{proposed_fix}

Write a clean pytest test module covering the fix and key edge cases. Provide runnable Python pytest code."""

    try:
        response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=prompt)])
        llm_calls += 1
        tests_written = response.content
    except Exception as e:
        tests_written = f"# Error generating tests via LLM: {str(e)}"

    return {
        "tests_written": tests_written,
        "llm_calls": llm_calls
    }


def human_approval_node(state: AgentState) -> Dict[str, Any]:
    """Node 6: Present work to human and request approval (yes/no)."""
    issue_title = state.get("issue_title", "")
    relevant_files = state.get("relevant_files", [])
    proposed_fix = state.get("proposed_fix", "")
    tests_written = state.get("tests_written", "")
    retry_count = state.get("retry_count", 0)

    print("\n" + "="*60)
    print("HUMAN APPROVAL REQUIRED")
    print("="*60)
    print(f"Issue: {issue_title}")
    print(f"Relevant Files: {', '.join(relevant_files)}")
    print("\n--- PROPOSED FIX ---")
    print(proposed_fix[:1500])
    print("\n--- UNIT TESTS ---")
    print(tests_written[:1000])
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
            feedback = "Please improve code quality and edge case handling."
        retry_count += 1

    messages = list(state.get("messages", []))
    if feedback:
        messages.append(HumanMessage(content=f"Feedback: {feedback}"))

    return {
        "human_approved": human_approved,
        "retry_count": retry_count,
        "messages": messages
    }


def pr_node(state: AgentState) -> Dict[str, Any]:
    """Node 7: Create branch, commit fix + tests, and open pull request on GitHub."""
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

    # Create branch
    res_branch = create_branch.invoke({
        "repo_url": repo_url,
        "branch_name": branch_name,
        "token": token
    })

    if isinstance(res_branch, str) and res_branch.startswith("Error"):
        errors.append(res_branch)
        return {"pr_url": "", "errors": errors}

    # Commit fix and tests
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

    # Open PR
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
