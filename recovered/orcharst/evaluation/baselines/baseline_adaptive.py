"""
evaluation/baselines/baseline_adaptive.py

ADAPTIVE MULTI-AGENT SYSTEM

Architecture:
  Issue
  ↓
  Fast localization (V2)
  ↓
  Task difficulty / uncertainty assessment
  ↓
  ┌───────────────────────────────┐
  │                               │
  Simple / high-confidence      Hard / uncertain
  │                               │
  ↓                               ↓
  Direct repair                Evidence extraction
  │                            + planning
  │                               ↓
  │                           code generation
  │                               ↓
  └───────────────┬───────────────┘
                  ↓
               tests
                  ↓
          failure analysis
                  ↓
      targeted repair only
        when justified
                  ↓
      deterministic verifier

Paths:
  PATH A — SIMPLE: localization → direct code gen → validation → tests
  PATH B — MEDIUM: localization → compact evidence → code gen → validation → tests
  PATH C — HARD: localization → evidence → explicit plan → code gen → tests
                → failure analysis → targeted repair

The controller decides whether to escalate based on:
  - localization confidence
  - number of candidate files
  - issue complexity
  - number of affected functions
  - ambiguity of requirements
  - repository structure complexity
"""

from __future__ import annotations

import os
import sys
import ast
import json
import time
import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

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
from agent.provider import pricing_note, provider_info, classify_provider_failure

# Fixture routing: the benchmark repos only exist locally.
if str(repo_root / "evaluation") not in sys.path:
    sys.path.insert(0, str(repo_root / "evaluation"))
from fixture_router import (
    resolve_fixture_path, local_repo_files, install_agent_resolver, set_current_task
)

# Install the fixture resolver so the agent hits local fixtures, not GitHub
_RESOLVER_INSTALLED = install_agent_resolver()
if not _RESOLVER_INSTALLED:
    print("[WARN] fixture resolver NOT installed - agent would hit GitHub for fixture repos")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()


# ============================================================================
# DIFFICULTY ESTIMATOR
# ============================================================================

class DifficultyEstimator:
    """
    V3 Difficulty Estimator - calibrated for genuine adaptivity.
    
    Key changes from V2:
    - Lower weight on localization confidence (always high in V2)
    - Add more discriminative features
    - Adjust thresholds so PATH_A can be selected
    """
    
    def __init__(self, task: dict, repo_files: list, localization_result: dict):
        self.task = task
        self.repo_files = repo_files
        self.localization = localization_result
        
        self.score = 0.0
        self.features = {}
        self.reason = ""
        
    def estimate(self) -> Tuple[float, str, dict]:
        """
        Returns (score, difficulty_class, features_dict)
        
        score: 0-10 continuous score
        difficulty_class: "simple", "medium", "hard"
        """
        features = {}
        
        # 1. Localization confidence (0-1.5 points) - reduced weight
        loc_confidence = self._assess_localization_confidence()
        features["localization_confidence"] = loc_confidence
        self.score += loc_confidence * 0.5  # max 1.5 points
        
        # 2. Candidate file count (0-2 points)
        n_candidates = len(self.localization.get("top_k", self.localization.get("relevant_files", [])))
        features["n_candidates"] = n_candidates
        if n_candidates == 1:
            self.score += 0.5
        elif n_candidates <= 3:
            self.score += 1.0
        else:
            self.score += 2.0
            
        # 3. Issue complexity (0-2.5 points) - more granular
        issue_complexity = self._assess_issue_complexity()
        features["issue_complexity"] = issue_complexity
        self.score += issue_complexity
        
        # 4. Repository complexity (0-1.5 points)
        repo_complexity = self._assess_repo_complexity()
        features["repo_complexity"] = repo_complexity
        self.score += repo_complexity
        
        # 5. Symbol coverage ratio (0-1 point)
        symbol_coverage = self._assess_symbol_coverage()
        features["symbol_coverage"] = symbol_coverage
        self.score += symbol_coverage
        
        # 6. Single-file confidence (0-1.5 points) - NEW for PATH_A
        single_file_confidence = self._assess_single_file_confidence()
        features["single_file_confidence"] = single_file_confidence
        self.score += single_file_confidence
        
        # Normalize to 0-10
        self.score = min(10.0, max(0.0, self.score))
        
        # V3 thresholds - adjusted so PATH_A can be selected
        #   simple:  < 4.0 (clear, confident, simple)
        #   medium:  4.0 - 6.0 (needs evidence)
        #   hard:    >= 6.0 (needs full reasoning)
        if self.score < 4.0:
            difficulty_class = "simple"
        elif self.score < 6.0:
            difficulty_class = "medium"
        else:
            difficulty_class = "hard"
            
        self.features = features
        self.reason = self._generate_reason()
        
        return self.score, difficulty_class, features
    
    def _assess_single_file_confidence(self) -> float:
        """Assess confidence that this is a single-file, straightforward fix (0-1.5)."""
        score = 0.0
        
        evidence = self.localization.get("localization_evidence", {})
        signals = evidence.get("issue_signals", {})
        
        # Single clear target file
        relevant_files = self.localization.get("relevant_files", [])
        if len(relevant_files) == 1:
            score += 0.5
        
        # Explicit path in issue - very strong signal
        explicit_paths = signals.get("explicit_paths", [])
        if explicit_paths and len(explicit_paths) == 1:
            score += 0.5
        
        # Low symbol count - simpler issue
        symbols = signals.get("symbols", [])
        if len(symbols) <= 2:
            score += 0.25
        elif len(symbols) <= 5:
            score += 0.1
            
        # Issue body is short (< 200 words)
        issue_body = self.task.get("issue_body", "")
        if len(issue_body.split()) < 200:
            score += 0.25
            
        return min(1.5, score)
    
    def _assess_localization_confidence(self) -> float:
        """Assess how confident we are in the localization (0-3 raw, scaled to 0-2)."""
        score = 0.0
        
        # Explicit path in issue? (strongest signal)
        evidence = self.localization.get("localization_evidence", {})
        signals = evidence.get("issue_signals", {})
        explicit_paths = signals.get("explicit_paths", [])
        if explicit_paths:
            score += 1.5
            
        # Symbol hits in selected file?
        source_excerpts = evidence.get("source_excerpts", {})
        for f, excerpt in source_excerpts.items():
            if excerpt.get("issue_symbol_hits"):
                score += 1.0
                break
                
        # V2 validation completed?
        if self.localization.get("localization_stage") == "complete":
            score += 0.5
            
        return min(3.0, score)
    
    def _assess_issue_complexity(self) -> float:
        """Assess issue complexity based on text (0-2.5)."""
        issue_title = self.task.get("issue_title", "")
        issue_body = self.task.get("issue_body", "")
        issue_text = f"{issue_title}\n{issue_body}"
        
        score = 0.0
        
        # Word count (more words = more complex description)
        words = len(issue_text.split())
        if words > 500:
            score += 1.5
        elif words > 300:
            score += 1.0
        elif words > 150:
            score += 0.5
            
        # Mentions of edge cases, special conditions, constraints
        edge_case_hits = len(re.findall(r"(edge case|special case|corner case|when.*and.*or|must.*if|only.*if)", issue_text, re.IGNORECASE))
        if edge_case_hits > 3:
            score += 1.0
        elif edge_case_hits > 1:
            score += 0.5
            
        # Multiple requirements
        requirement_count = len(re.findall(r"(must|should|need to|required to|ensure|verify)", issue_text, re.IGNORECASE))
        if requirement_count > 5:
            score += 1.0
        elif requirement_count > 3:
            score += 0.5
            
        return min(2.5, score)
    
    def _assess_repo_complexity(self) -> float:
        """Assess repository structure complexity (0-2)."""
        score = 0.0
        
        # Number of Python files
        py_files = [f for f in self.repo_files if f.endswith(".py")]
        if len(py_files) > 15:
            score += 1.0
        elif len(py_files) > 8:
            score += 0.5
            
        # Nested structure depth
        nested = [f for f in py_files if "/" in f and f.count("/") > 1]
        if len(nested) > 5:
            score += 0.5
        elif len(nested) > 2:
            score += 0.25
            
        # Total non-test files
        code_files = [f for f in self.repo_files if not f.startswith("test") and not f.startswith("conftest")]
        if len(code_files) > 20:
            score += 0.5
            
        return min(2.0, score)
    
    def _assess_symbol_coverage(self) -> float:
        """Assess how well the selected file covers issue-mentioned symbols (0-1)."""
        evidence = self.localization.get("localization_evidence", {})
        signals = evidence.get("issue_signals", {})
        issue_symbols = signals.get("symbols", [])
        
        if not issue_symbols:
            return 0.0  # No symbols to match, neutral
            
        source_excerpts = evidence.get("source_excerpts", {})
        total_hits = 0
        for f, excerpt in source_excerpts.items():
            total_hits += len(excerpt.get("issue_symbol_hits", []))
        
        coverage = total_hits / len(issue_symbols)
        return min(1.0, coverage)
    
    def _generate_reason(self) -> str:
        """Generate human-readable reason for the classification."""
        parts = []
        
        loc_conf = self.features.get("localization_confidence", 0)
        if loc_conf >= 2.5:
            parts.append("high localization confidence")
        elif loc_conf >= 1.5:
            parts.append("moderate localization confidence")
        else:
            parts.append("low localization confidence")
            
        n_cand = self.features.get("n_candidates", 1)
        if n_cand <= 1:
            parts.append("single candidate file")
        elif n_cand <= 3:
            parts.append(f"{n_cand} candidates")
        else:
            parts.append(f"{n_cand} candidates (spread)")
            
        issue_comp = self.features.get("issue_complexity", 0)
        if issue_comp >= 2.0:
            parts.append("complex issue")
        elif issue_comp >= 1.0:
            parts.append("moderate issue complexity")
            
        sym_cov = self.features.get("symbol_coverage", 0)
        if sym_cov >= 0.5:
            parts.append(f"good symbol coverage ({sym_cov:.0%})")
        elif sym_cov > 0:
            parts.append(f"partial symbol coverage ({sym_cov:.0%})")
            
        repo_comp = self.features.get("repo_complexity", 0)
        if repo_comp >= 1.0:
            parts.append("complex repository")
            
        return "; ".join(parts) if parts else "baseline assessment"


# ============================================================================
# ADAPTIVE CONTROLLER
# ============================================================================

class AdaptiveController:
    """
    Determines execution path based on difficulty assessment.
    
    Paths:
      PATH_A (simple): localization → code gen → validation → tests
      PATH_B (medium): localization → compact evidence → code gen → validation → tests  
      PATH_C (hard): localization → evidence → plan → code gen → tests → failure analysis → repair
    
    V2: Supports dynamic escalation after initial execution if tests fail.
    """
    
    def __init__(self, difficulty_score: float, difficulty_class: str, features: dict):
        self.difficulty_score = difficulty_score
        self.difficulty_class = difficulty_class
        self.features = features
        self.initial_path = self._select_path()
        self.final_path = self.initial_path
        self.escalated = False
        self.escalation_reason = None
        self.reason = self._generate_path_reason()
        
    def _select_path(self) -> str:
        """Select execution path based on difficulty."""
        if self.difficulty_class == "simple":
            return "PATH_A"
        elif self.difficulty_class == "medium":
            return "PATH_B"
        else:
            return "PATH_C"
    
    def _generate_path_reason(self) -> str:
        """Generate reason for path selection."""
        if self.initial_path == "PATH_A":
            return f"Simple task (score={self.difficulty_score:.1f}): direct repair without planning/evidence stages"
        elif self.initial_path == "PATH_B":
            return f"Medium task (score={self.difficulty_score:.1f}): compact evidence, skip explicit planning"
        else:
            return f"Hard task (score={self.difficulty_score:.1f}): full pipeline with planning and targeted repair"
    
    def escalate_to(self, new_path: str, reason: str) -> None:
        """Escalate to a more expensive path after failure analysis."""
        if new_path == self.final_path:
            return
        self.final_path = new_path
        self.escalated = True
        self.escalation_reason = reason
        self.reason = f"{self.reason} -> ESCALATED: {reason}"
    
    def should_run_plan(self) -> bool:
        """Whether to run the planning stage."""
        return self.final_path == "PATH_C"
    
    def should_run_evidence_extraction(self) -> bool:
        """Whether to run full evidence extraction."""
        return self.final_path in ("PATH_B", "PATH_C")
    
    def should_run_test_generation(self) -> bool:
        """Whether to generate diagnostic tests."""
        return self.final_path in ("PATH_B", "PATH_C")
    
    def should_perform_failure_analysis(self) -> bool:
        """Whether to perform detailed failure analysis on test failure."""
        return self.final_path in ("PATH_A", "PATH_B", "PATH_C")  # V2: always analyze failures
    
    def max_repair_attempts(self) -> int:
        """Maximum repair attempts for this path.

        V4 controlled-experiment pin: when AGENT_REPAIR_BUDGET is set, ALL
        paths use that budget so the adaptive arm runs the SAME retry budget
        as baseline_b (which reads AGENT_MAX_RETRIES). Unset (V3 and earlier
        behavior): per-path budgets PATH_A=1, PATH_B=2, PATH_C=env default 3.
        The decision logic (path selection, escalation, failure
        classification) is untouched by this pin.
        """
        pinned = os.getenv("AGENT_REPAIR_BUDGET", "").strip()
        if pinned:
            return int(pinned)
        if self.final_path == "PATH_A":
            return 1
        elif self.final_path == "PATH_B":
            return 2
        else:
            return int(os.getenv("AGENT_MAX_RETRIES", "3"))


# ============================================================================
# TASK EXECUTION
# ============================================================================

def run_hidden_tests(fix_code: str, hidden_test_file: str,
                     gold_file: Optional[str] = None) -> Tuple[bool, str, int, int]:
    """Run hidden evaluation tests against the agent's proposed fix."""
    env = os.environ.copy()
    env["EVAL_FIX_CODE"] = fix_code
    if gold_file:
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


def extract_code(content: str) -> str:
    """Extract code block from LLM response."""
    if "```python" in content:
        return content.split("```python")[1].split("```")[0].strip()
    if "```" in content:
        return content.split("```")[1].split("```")[0].strip()
    return content.strip()


def run_task(task: dict) -> dict:
    """
    Run the adaptive multi-agent system on a single task.
    
    The controller determines the execution path based on task difficulty,
    then executes only the stages warranted for that path.
    """
    task_id = task["task_id"]
    repo_url = task["repository"]
    issue_title = task["issue_title"]
    issue_body = task["issue_body"]
    issue_id = task.get("issue_id")
    gold_file = task["gold_file"]
    hidden_test_file = task["hidden_test_file"]

    print(f"\n[ADAPTIVE] Running task {task_id}...")
    overall_start = time.monotonic()

    # ========================================================================
    # PHASE 1: FAST LOCALIZATION (always runs)
    # ========================================================================
    fixture_path = resolve_fixture_path(repo_url)
    
    # Run V2 localization directly (not through the full graph)
    from agent.localization_v2 import research_node_v2
    
    localization_state = {
        "repo_url": repo_url,
        "issue_number": issue_id or 0,
        "token": GITHUB_TOKEN,
        "problem_description": "",
        "mode": "issue" if issue_id else "smart",
        "session_id": f"eval_{task_id}",
        "is_web": False,
        "issue_title": task["issue_title"],
        "issue_body": task["issue_body"],
        "relevant_files": [],
        "llm_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "localization_attempts": 0,
        "localization_revisit": False,
    }
    
    eval_ctx = None
    try:
        with active_eval_context(task_id, system="adaptive_multi_agent", repo_url=repo_url,
                                 fixture_path=fixture_path) as eval_ctx:
            localization_result = research_node_v2(localization_state)
    except Exception as e:
        print(f"[ADAPTIVE] Localization error: {e}")
        localization_result = {
            "relevant_files": ["src/main.py"],
            "localization_evidence": {},
            "localization_stage": "error",
        }
        if eval_ctx is not None:
            localization_result["llm_calls"] = eval_ctx.total_llm_calls()
            localization_result["input_tokens"] = eval_ctx.input_tokens()
            localization_result["output_tokens"] = eval_ctx.output_tokens()

    # Get localization results
    relevant_files = localization_result.get("relevant_files", [])
    localization_evidence = localization_result.get("localization_evidence", {})
    llm_calls_after_loc = localization_result.get("llm_calls", eval_ctx.total_llm_calls() if eval_ctx else 0)
    input_tokens_after_loc = localization_result.get("input_tokens", eval_ctx.input_tokens() if eval_ctx else 0)
    output_tokens_after_loc = localization_result.get("output_tokens", eval_ctx.output_tokens() if eval_ctx else 0)

    # Get repo files for difficulty estimation
    repo_files = local_repo_files(repo_url)

    # ========================================================================
    # PHASE 2: DIFFICULTY ASSESSMENT
    # ========================================================================
    estimator = DifficultyEstimator(task, repo_files, localization_result)
    difficulty_score, difficulty_class, features = estimator.estimate()
    
    print(f"[ADAPTIVE] Difficulty: score={difficulty_score:.1f}, class={difficulty_class}")
    print(f"[ADAPTIVE] Features: {features}")

    # ========================================================================
    # PHASE 3: PATH SELECTION
    # ========================================================================
    controller = AdaptiveController(difficulty_score, difficulty_class, features)
    
    print(f"[ADAPTIVE] Initial path: {controller.initial_path}")
    print(f"[ADAPTIVE] Reason: {controller.reason}")

    # ========================================================================
    # PHASE 4: EXECUTION ACCORDING TO SELECTED PATH
    # ========================================================================
    
    # Track stage usage
    stage_calls = {
        "localization_calls": llm_calls_after_loc,
        "evidence_calls": 0,
        "planning_calls": 0,
        "code_calls": 0,
        "test_calls": 0,
        "failure_analysis_calls": 0,
        "repair_calls": 0,
    }
    
    current_input = input_tokens_after_loc
    current_output = output_tokens_after_loc
    current_llm_calls = llm_calls_after_loc
    
    proposed_fix = ""
    syntax_valid = False
    generated_code_is_model = False
    patch_placeholder = False
    patch_apply_success = False
    patch_target_valid = False
    tests_written = ""
    tests_passed = False
    test_results = ""
    repair_plan = ""
    first_patch_source = ""
    repair_attempts = []
    repair_history = []
    retry_count = 0
    failure_category = ""
    
    target_file = relevant_files[0] if relevant_files else "src/fix.py"
    original_content = _read_file(repo_url, target_file, GITHUB_TOKEN)
    snippet = original_content if not original_content.startswith("Error") else ""
    
    # ---- PATH A: Simple - direct code generation ----
    if controller.initial_path == "PATH_A":
        print("[ADAPTIVE] Executing PATH_A: direct code generation")
        
        # Code generation (single LLM call, no planning, no test gen)
        from agent.nodes import invoke_llm_with_timeout
        from langchain_core.messages import SystemMessage, HumanMessage
        
        prompt = f"""Issue: {issue_title[:150]}
{issue_body[:600]}

Target File: {target_file}

Current file content:
{snippet}

Provide the complete fixed code for this file."""
        
        llm_content, i_tok, o_tok = invoke_llm_with_timeout(
            [SystemMessage(content="You are an expert developer. Output complete fixed code. No explanations."),
             HumanMessage(content=prompt)],
            timeout_sec=30.0,
            stage="code_gen",
        )
        current_llm_calls += 1
        current_input += i_tok
        current_output += o_tok
        stage_calls["code_calls"] = 1
        
        if llm_content:
            proposed_fix = extract_code(llm_content)
            generated_code_is_model = True
            first_patch_source = proposed_fix
            
            # Syntax check
            try:
                ast.parse(proposed_fix)
                syntax_valid = True
            except SyntaxError:
                syntax_valid = False
                
            patch_placeholder = _is_placeholder(proposed_fix)
            patch_apply_success = bool(proposed_fix) and syntax_valid
            patch_target_valid = target_file in repo_files if isinstance(repo_files, list) else False

    # ---- PATH B: Medium - compact evidence + code gen ----
    elif controller.initial_path == "PATH_B":
        print("[ADAPTIVE] Executing PATH_B: compact evidence + code generation")
        
        from agent.nodes import invoke_llm_with_timeout
        from langchain_core.messages import SystemMessage, HumanMessage
        
        evidence_text = json.dumps(localization_evidence, ensure_ascii=True)[:2000]
        
        prompt = f"""Issue: {issue_title[:150]}
{issue_body[:600]}

Target File: {target_file}

Evidence:
{evidence_text}

Current file content:
{snippet}

Provide the complete fixed code for this file."""
        
        llm_content, i_tok, o_tok = invoke_llm_with_timeout(
            [SystemMessage(content="You are an expert developer. Output complete fixed code. No explanations."),
             HumanMessage(content=prompt)],
            timeout_sec=30.0,
            stage="code_gen",
        )
        current_llm_calls += 1
        current_input += i_tok
        current_output += o_tok
        stage_calls["code_calls"] = 1
        
        if llm_content:
            proposed_fix = extract_code(llm_content)
            generated_code_is_model = True
            first_patch_source = proposed_fix
            
            try:
                ast.parse(proposed_fix)
                syntax_valid = True
            except SyntaxError:
                syntax_valid = False
                
            patch_placeholder = _is_placeholder(proposed_fix)
            patch_apply_success = bool(proposed_fix) and syntax_valid
            patch_target_valid = target_file in repo_files if isinstance(repo_files, list) else False

    # ---- PATH C: Hard - full pipeline with planning ----
    elif controller.initial_path == "PATH_C":
        print("[ADAPTIVE] Executing PATH_C: full pipeline with planning and repair")
        
        from agent.graph import app as langgraph_app
        
        execution_state = {
            "repo_url": repo_url,
            "issue_number": issue_id or 0,
            "token": GITHUB_TOKEN,
            "problem_description": "",
            "mode": "issue" if issue_id else "smart",
            "session_id": f"eval_{task_id}",
            "is_web": False,
            "issue_title": task["issue_title"],
            "issue_body": task["issue_body"],
            "relevant_files": relevant_files,
            "proposed_fix": "",
            "tests_written": "",
            "pr_url": "",
            "messages": [],
            "human_approved": False,
            "retry_count": 0,
            "llm_calls": current_llm_calls,
            "errors": [],
            "eval_mode": True,
            "eval_task_id": task_id,
            "eval_gold_file": gold_file,
            "start_time": time.monotonic(),
            "input_tokens": current_input,
            "output_tokens": current_output,
            "original_file_content": "",
            "first_patch_source": "",
            "patch_diff": "",
            "lines_added": 0,
            "lines_removed": 0,
            "syntax_valid": None,
            "repair_plan": "",
            "localization_evidence": localization_evidence,
            "patch_placeholder": False,
            "patch_apply_success": False,
            "patch_target_valid": False,
            "generated_code_is_model": False,
            "repair_attempts": [],
            "repair_history": [],
        }
        
        try:
            with active_eval_context(task_id, system="adaptive_multi_agent", repo_url=repo_url,
                                     fixture_path=fixture_path) as eval_ctx2:
                final_state = langgraph_app.invoke(execution_state)
                snapshot_into_state(final_state)
                
                proposed_fix = final_state.get("proposed_fix", "")
                tests_written = final_state.get("tests_written", "")
                tests_passed = final_state.get("tests_passed", False)
                test_results = final_state.get("test_results", "")
                retry_count = final_state.get("retry_count", 0)
                syntax_valid = final_state.get("syntax_valid", False)
                patch_placeholder = final_state.get("patch_placeholder", False)
                patch_apply_success = final_state.get("patch_apply_success", False)
                patch_target_valid = final_state.get("patch_target_valid", False)
                generated_code_is_model = final_state.get("generated_code_is_model", False)
                first_patch_source = final_state.get("first_patch_source", proposed_fix)
                repair_attempts = final_state.get("repair_attempts", [])
                repair_history = final_state.get("repair_history", [])
                repair_plan = final_state.get("repair_plan", "")
                
                current_llm_calls = eval_ctx2.total_llm_calls()
                current_input = eval_ctx2.input_tokens()
                current_output = eval_ctx2.output_tokens()
                
                llm_calls_by_stage = eval_ctx2.llm_calls_by_stage()
                stage_calls["evidence_calls"] = llm_calls_by_stage.get("research", 0)
                stage_calls["planning_calls"] = llm_calls_by_stage.get("plan", 0)
                stage_calls["code_calls"] = llm_calls_by_stage.get("code_gen", 0)
                stage_calls["test_calls"] = llm_calls_by_stage.get("test_gen", 0)
                stage_calls["repair_calls"] = llm_calls_by_stage.get("repair_gen", 0)
                
        except Exception as e:
            print(f"[ADAPTIVE] Pipeline error: {e}")
            if eval_ctx2 is not None:
                current_llm_calls = eval_ctx2.total_llm_calls()
                current_input = eval_ctx2.input_tokens()
                current_output = eval_ctx2.output_tokens()

    # ========================================================================
    # PHASE 5: VALIDATION & TESTING
    # ========================================================================
    
    # Run hidden tests if we didn't run the full pipeline
    if controller.initial_path in ("PATH_A", "PATH_B"):
        if proposed_fix and syntax_valid:
            try:
                hidden_passed, hidden_output, hidden_total, hidden_passed_count = run_hidden_tests(
                    proposed_fix, hidden_test_file, gold_file
                )
                test_results = hidden_output
            except Exception as e:
                test_results = f"Error: {e}"
                hidden_passed = False
                hidden_total = 0
                hidden_passed_count = 0
        else:
            hidden_passed = False
            hidden_total = 0
            hidden_passed_count = 0
            test_results = "No valid patch to test"
    else:
        # PATH_C: tests already run by the pipeline
        hidden_passed = tests_passed
        hidden_output = test_results
        hidden_total = 0
        hidden_passed_count = 0
    
    initial_hidden_passed = hidden_passed
    
    # ========================================================================
    # PHASE 6: FAILURE-AWARE ESCALATION
    # ========================================================================
    
    repair_eligible = False
    repair_recovered = False
    
    if not hidden_passed and proposed_fix and syntax_valid:
        # Classify the failure and decide on action
        action, category, reason = _classify_and_decide_repair(
            test_results, proposed_fix, target_file, repair_history,
            repo_files, localization_evidence, controller.final_path
        )
        
        failure_category = category
        print(f"[ADAPTIVE] Failure classified: {category}, action: {action}")
        
        if action == "DIRECT_REPAIR":
            repair_eligible = True
            # V4 budget control: up to controller.max_repair_attempts() targeted
            # repair attempts. With the pin unset this is exactly the V3 single
            # repair for PATH_A/B (budget 1); with AGENT_REPAIR_BUDGET=2 it
            # matches baseline_b's retry budget. Decision logic is unchanged:
            # each attempt re-feeds the latest failure output; escalation is
            # still only decided by the initial classification above.
            repair_budget = controller.max_repair_attempts()
            direct_repair_attempts_made = 0
            for _repair_attempt in range(1, repair_budget + 1):
                if hidden_passed:
                    break
                direct_repair_attempts_made += 1
                print(f"[ADAPTIVE] Attempting targeted repair "
                      f"(attempt {direct_repair_attempts_made}/{repair_budget}): {reason}")
                
                # Attempt one targeted repair
                from agent.nodes import invoke_llm_with_timeout
                from langchain_core.messages import SystemMessage, HumanMessage
                
                # Build repair prompt with failure context
                repair_prompt = f"""Issue: {issue_title[:150]}
{issue_body[:600]}

Target File: {target_file}

Previous patch failed with this test output:
{test_results[:1000]}

Current file content:
{snippet}

Provide a FIXED version addressing the failure above."""
                
                llm_content, i_tok, o_tok = invoke_llm_with_timeout(
                    [SystemMessage(content="You are an expert developer. Analyze the failure and provide corrected code."),
                     HumanMessage(content=repair_prompt)],
                    timeout_sec=30.0,
                    stage="repair_gen",
                )
                current_llm_calls += 1
                current_input += i_tok
                current_output += o_tok
                stage_calls["repair_calls"] += 1
                
                if llm_content:
                    new_fix = extract_code(llm_content)
                    if new_fix and new_fix != proposed_fix:
                        proposed_fix = new_fix
                        first_patch_source = new_fix if not first_patch_source else first_patch_source
                        
                        try:
                            ast.parse(proposed_fix)
                            syntax_valid = True
                        except SyntaxError:
                            syntax_valid = False
                        
                        patch_placeholder = _is_placeholder(proposed_fix)
                        patch_apply_success = bool(proposed_fix) and syntax_valid
                        
                        # Re-run hidden tests
                        if syntax_valid:
                            try:
                                hidden_passed, hidden_output, hidden_total, hidden_passed_count = run_hidden_tests(
                                    proposed_fix, hidden_test_file, gold_file
                                )
                                test_results = hidden_output
                            except Exception as e:
                                test_results = f"Error: {e}"
                                hidden_passed = False
                        
                        if hidden_passed:
                            repair_recovered = True
                            print(f"[ADAPTIVE] Repair succeeded!")
                        else:
                            repair_history.append({"attempt": direct_repair_attempts_made, "result": "failed"})
                    else:
                        # Model returned no usable new patch: counts as a failed attempt
                        repair_history.append({"attempt": direct_repair_attempts_made, "result": "failed"})
                else:
                    repair_history.append({"attempt": direct_repair_attempts_made, "result": "failed"})
                        
        elif action == "ESCALATE":
            # Escalate to more expensive path
            if "PATH_C" in reason:
                controller.escalate_to("PATH_C", reason)
                print(f"[ADAPTIVE] Escalating to PATH_C: {reason}")
                
                # Run full pipeline with planning
                from agent.graph import app as langgraph_app
                
                execution_state = {
                    "repo_url": repo_url,
                    "issue_number": issue_id or 0,
                    "token": GITHUB_TOKEN,
                    "problem_description": "",
                    "mode": "issue" if issue_id else "smart",
                    "session_id": f"eval_{task_id}",
                    "is_web": False,
                    "issue_title": task["issue_title"],
                    "issue_body": task["issue_body"],
                    "relevant_files": relevant_files,
                    "proposed_fix": proposed_fix,
                    "tests_written": "",
                    "pr_url": "",
                    "messages": [],
                    "human_approved": False,
                    "retry_count": 0,
                    "llm_calls": current_llm_calls,
                    "errors": [],
                    "eval_mode": True,
                    "eval_task_id": task_id,
                    "eval_gold_file": gold_file,
                    "start_time": time.monotonic(),
                    "input_tokens": current_input,
                    "output_tokens": current_output,
                    "original_file_content": snippet,
                    "first_patch_source": first_patch_source or proposed_fix,
                    "patch_diff": "",
                    "lines_added": 0,
                    "lines_removed": 0,
                    "syntax_valid": syntax_valid,
                    "repair_plan": "",
                    "localization_evidence": localization_evidence,
                    "patch_placeholder": patch_placeholder,
                    "patch_apply_success": patch_apply_success,
                    "patch_target_valid": patch_target_valid,
                    "generated_code_is_model": generated_code_is_model,
                    "repair_attempts": repair_attempts,
                    "repair_history": repair_history,
                }
                
                try:
                    with active_eval_context(task_id, system="adaptive_multi_agent", repo_url=repo_url,
                                             fixture_path=fixture_path) as eval_ctx2:
                        final_state = langgraph_app.invoke(execution_state)
                        snapshot_into_state(final_state)
                        
                        proposed_fix = final_state.get("proposed_fix", proposed_fix)
                        tests_written = final_state.get("tests_written", "")
                        tests_passed = final_state.get("tests_passed", False)
                        test_results = final_state.get("test_results", test_results)
                        retry_count = final_state.get("retry_count", 0)
                        syntax_valid = final_state.get("syntax_valid", syntax_valid)
                        patch_placeholder = final_state.get("patch_placeholder", patch_placeholder)
                        patch_apply_success = final_state.get("patch_apply_success", patch_apply_success)
                        patch_target_valid = final_state.get("patch_target_valid", patch_target_valid)
                        generated_code_is_model = final_state.get("generated_code_is_model", generated_code_is_model)
                        first_patch_source = final_state.get("first_patch_source", first_patch_source or proposed_fix)
                        repair_attempts = final_state.get("repair_attempts", repair_attempts)
                        repair_history = final_state.get("repair_history", repair_history)
                        repair_plan = final_state.get("repair_plan", "")
                        
                        current_llm_calls = eval_ctx2.total_llm_calls()
                        current_input = eval_ctx2.input_tokens()
                        current_output = eval_ctx2.output_tokens()
                        
                        llm_calls_by_stage = eval_ctx2.llm_calls_by_stage()
                        stage_calls["evidence_calls"] += llm_calls_by_stage.get("research", 0)
                        stage_calls["planning_calls"] = llm_calls_by_stage.get("plan", 0)
                        stage_calls["code_calls"] += llm_calls_by_stage.get("code_gen", 0)
                        stage_calls["test_calls"] = llm_calls_by_stage.get("test_gen", 0)
                        stage_calls["repair_calls"] += llm_calls_by_stage.get("repair_gen", 0)
                        
                        if final_state.get("tests_passed", False):
                            hidden_passed = True
                            repair_recovered = True
                            print(f"[ADAPTIVE] Escalated repair succeeded!")
                
                except Exception as e:
                    print(f"[ADAPTIVE] Escalation pipeline error: {e}")
                    if eval_ctx2 is not None:
                        current_llm_calls = eval_ctx2.total_llm_calls()
                        current_input = eval_ctx2.input_tokens()
                        current_output = eval_ctx2.output_tokens()
            
            elif "PATH_B" in reason:
                controller.escalate_to("PATH_B", reason)
                print(f"[ADAPTIVE] Escalating to PATH_B: {reason}")
                # PATH_B is already being used, no further action needed
                # The repair attempt above handles it
    
    # ========================================================================
    # PHASE 7: FINAL RESOLUTION
    # ========================================================================
    
    latency = round(time.monotonic() - overall_start, 3)
    
    if hidden_passed and proposed_fix and syntax_valid and not patch_placeholder:
        final_resolved = True
    else:
        final_resolved = False
    
    # Top-1 localization
    predicted_file = relevant_files[0] if relevant_files else None
    top1_correct = (predicted_file == gold_file) if predicted_file else False
    hallucinated = (predicted_file is not None and predicted_file not in repo_files) if isinstance(repo_files, list) else False
    
    # Cost calculation
    cost = round((current_input / 1_000_000 * 0.59) + (current_output / 1_000_000 * 0.79), 6)
    
    # Provider failures
    provider_failures = eval_ctx.provider_failures() if eval_ctx else []
    contamination_detected = bool(provider_failures)
    
    result = {
        "task_id": task_id,
        "system": "adaptive_multi_agent",
        "repository": repo_url,
        "issue_id": str(issue_id) if issue_id else None,
        "issue_title": issue_title,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": {
            **provider_info(),
            "served_models": sorted({c.served_model for c in (eval_ctx.llm_calls if eval_ctx else []) if c.served_model}),
            "contamination_detected": contamination_detected,
            "contamination": [
                {"stage": c.stage, "error": c.error[:500], "failure_category": c.failure_category, "latency_seconds": c.latency}
                for c in provider_failures
            ],
        },
        "localization": {
            "predicted_file": predicted_file,
            "gold_file": gold_file,
            "top1_correct": top1_correct,
            "top3_correct": top1_correct,
            "hallucinated_file": hallucinated,
            "valid": predicted_file in repo_files if isinstance(repo_files, list) else bool(relevant_files),
        },
        "patch": {
            "generated": bool(proposed_fix),
            "is_placeholder": patch_placeholder,
            "generated_by_model": generated_code_is_model,
            "syntax_valid": syntax_valid,
            "files_changed": 1 if proposed_fix else 0,
            "lines_added": 0,
            "lines_removed": 0,
            "patch_apply_success": patch_apply_success,
            "patch_target_valid": patch_target_valid,
            "diff": "",
        },
        "tests": {
            "generated": bool(tests_written),
            "generated_tests_executed": True,
            "generated_tests_passed": tests_passed if controller.final_path == "PATH_C" else False,
            "generated_test_count": None,
            "generated_tests_output": test_results[:500] if test_results else None,
        },
        "regression": {
            "hidden_tests_executed": bool(proposed_fix and syntax_valid),
            "hidden_tests_passed": hidden_passed,
            "hidden_tests_total": 0,
            "hidden_tests_passed_count": 0,
            "hidden_tests_output": test_results[:1000] if test_results else None,
            "regression_free": hidden_passed,
        },
        "repair": {
            "attempts": (retry_count + 1 if controller.final_path == "PATH_C"
                         else direct_repair_attempts_made + 1),
            "repair_attempt_count": (retry_count if controller.final_path == "PATH_C"
                                     else direct_repair_attempts_made),
            # V4 artifact fix: record the TRUE first-pass outcome (before any
            # repair), not the final result. This removes the V3-class
            # first_pass_resolved contradiction at the source; the adaptive
            # controller decision logic is unchanged.
            "first_pass_resolved_hidden": initial_hidden_passed,
            "first_pass_failure_category": None if hidden_passed else "first_patch_failed_hidden_tests",
            "repair_eligible": repair_eligible,
            "repair_recovered": repair_recovered,
            "resolved_within_retry_budget": final_resolved,
            "retry_budget": controller.max_repair_attempts(),
            "repair_attempts": repair_attempts,
            "first_pass_output": test_results[:1000] if not hidden_passed else None,
        },
        "execution": {
            "status": "resolved" if final_resolved else ("hidden_test_failed" if proposed_fix else "patch_failed"),
            "failure_category": None,
            "latency_seconds": latency,
            "llm_calls": current_llm_calls,
            "input_tokens": current_input,
            "output_tokens": current_output,
            "total_tokens": current_input + current_output,
            "sandbox_mode": "subprocess",
        },
        "cost": {
            "estimated_usd": cost,
            "pricing_note": pricing_note(),
        },
        "pr": {
            "branch_created": False,
            "commit_created": False,
            "pr_created": False,
            "pr_url": None,
        },
        # Adaptive-specific fields
        "adaptive": {
            "difficulty_score": difficulty_score,
            "difficulty_class": difficulty_class,
            "initial_path": controller.initial_path,
            "final_path": controller.final_path,
            "escalated": controller.escalated,
            "escalation_reason": controller.escalation_reason,
            "path_reason": controller.reason,
            "stage_calls": stage_calls,
            "first_pass_resolved": initial_hidden_passed,
            "repair_eligible": repair_eligible,
            "repair_attempts": (retry_count if controller.final_path == "PATH_C"
                                else direct_repair_attempts_made),
            "repair_recovered": repair_recovered,
            "failure_category": failure_category,
            "final_resolved": final_resolved,
        },
        "end_to_end_resolved": final_resolved,
        "provider_contamination": contamination_detected,
    }
    
    return result


def _read_file(repo_url: str, file_path: str, token: str) -> str:
    """Read a file from the repository (local fixture first)."""
    try:
        from fixture_router import local_read_file, resolve_fixture_path
        if resolve_fixture_path(repo_url):
            return local_read_file(repo_url, file_path)
    except Exception:
        pass
    
    # Fallback to GitHub API
    try:
        from github import Github
        g = Github(token) if token else Github()
        repo = g.get_repo(repo_url.rstrip("/").split("github.com/")[-1])
        content_file = repo.get_contents(file_path)
        return content_file.decoded_content.decode("utf-8", errors="replace")
    except Exception as e:
        return f"Error: {e}"


def _is_placeholder(code: str) -> bool:
    """Check if code is a placeholder/stub."""
    if not code or not code.strip():
        return True
    markers = (
        "def resolve_issue():",
        "Automated code fix applied",
        "# Proposed Fix for",
        "Updated logic for",
    )
    return any(m in code for m in markers)


class FailureClassifier:
    """
    Classify test failures to determine repair strategy.
    
    Returns:
        category: str - one of the failure categories
        action: str - STOP, DIRECT_REPAIR, or ESCALATE
        reason: str - explanation for the action
    """
    
    def __init__(self, test_output: str, proposed_fix: str, 
                 target_file: str, repair_history: list, 
                 repo_files: list, localization_evidence: dict):
        self.test_output = test_output
        self.proposed_fix = proposed_fix
        self.target_file = target_file
        self.repair_history = repair_history
        self.repo_files = repo_files
        self.localization_evidence = localization_evidence
        
    def classify(self) -> Tuple[str, str, str]:
        """Classify the failure and recommend an action."""
        # Extract key failure signals
        failing_tests = self._extract_failing_tests()
        assertion_info = self._extract_assertion()
        error_type = self._detect_error_type()
        
        # Check for syntax errors
        if error_type == "syntax":
            return ("syntax_error", "DIRECT_REPAIR", 
                    "Syntax error detected - can fix directly")
        
        # Check for localization issues (wrong file)
        if self._suspect_wrong_file():
            return ("localization_error", "ESCALATE", 
                    "Failure pattern suggests wrong file - escalate to evidence/plan")
        
        # Check for edge case failures
        if self._detect_edge_case_failure():
            # If we've already tried repair, escalate
            if len(self.repair_history) >= 1:
                return ("edge_case", "ESCALATE", 
                        "Edge case failure after repair attempt - need planning")
            return ("edge_case", "DIRECT_REPAIR", 
                    "Edge case failure - attempt targeted repair")
        
        # Check for assertion-specific failures (actionable)
        if assertion_info and failing_tests:
            if len(self.repair_history) >= 2:
                return ("repeated_failure", "ESCALATE", 
                        "Multiple repair attempts failed - need full reasoning")
            return ("assertion_failure", "DIRECT_REPAIR", 
                    f"Specific assertion failure on {failing_tests[0]} - targeted repair possible")
        
        # Generic test failure
        if failing_tests:
            if len(self.repair_history) >= 2:
                return ("test_failure", "ESCALATE", 
                        "Repeated test failures - escalate for deeper analysis")
            return ("test_failure", "DIRECT_REPAIR", 
                    f"Test failure on {failing_tests[0]} - attempt repair")
        
        # Unknown failure
        return ("unknown", "STOP", 
                "Cannot classify failure - stop to avoid wasting resources")
    
    def _extract_failing_tests(self) -> list:
        """Extract names of failing tests from output."""
        import re
        failing = re.findall(r"(test_[^\s:]+)[^\s]*\s+FAILED", self.test_output or "")
        if not failing:
            failing = re.findall(r"FAILED ([^\s:]+)::([^\s]+)", self.test_output or "")
        return failing[:5] if failing else []
    
    def _extract_assertion(self) -> dict:
        """Extract assertion details if present."""
        import re
        assert_match = re.search(r"AssertionError: (.+)", self.test_output or "")
        if assert_match:
            assertion_text = assert_match.group(1)
            expected_match = re.search(r"assert (.+?) == (.+?)(?:\s|$)", assertion_text)
            if expected_match:
                return {
                    "expected": expected_match.group(2)[:100],
                    "actual": expected_match.group(1)[:100],
                    "full": assertion_text[:300]
                }
        return {}
    
    def _detect_error_type(self) -> str:
        """Detect the type of error from test output."""
        output = self.test_output or ""
        
        if "SyntaxError" in output or "syntaxerror" in output.lower():
            return "syntax"
        if "IndentationError" in output:
            return "syntax"
        if "NameError" in output or "undefined" in output.lower():
            return "name_error"
        if "TypeError" in output:
            return "type_error"
        if "AttributeError" in output:
            return "attribute_error"
        if "IndexError" in output or "out of range" in output.lower():
            return "index_error"
        if "KeyError" in output:
            return "key_error"
        if "ValueError" in output:
            return "value_error"
        if "ZeroDivisionError" in output:
            return "zero_division"
        
        return "unknown"
    
    def _suspect_wrong_file(self) -> bool:
        """Check if failure pattern suggests we're working on the wrong file."""
        # If the test output mentions symbols/functions not in our target file
        output = self.test_output or ""
        evidence = self.localization_evidence
        signals = evidence.get("issue_signals", {})
        issue_symbols = signals.get("symbols", [])
        
        if not issue_symbols:
            return False
            
        # Check if test mentions symbols that should be in a different file
        source_excerpts = evidence.get("source_excerpts", {})
        selected_symbols = set()
        for f, excerpt in source_excerpts.items():
            selected_symbols.update(excerpt.get("issue_symbol_hits", []))
        
        # If test mentions issue symbols that aren't in selected file
        for symbol in issue_symbols[:3]:
            if symbol.lower() not in output.lower():
                continue
            if symbol not in selected_symbols:
                # Test mentions a symbol that should be defined elsewhere
                return True
        
        return False
    
    def _detect_edge_case_failure(self) -> bool:
        """Check if the failure appears to be an edge case."""
        output = self.test_output or ""
        
        # Look for edge case patterns in test names
        edge_patterns = ["empty", "none", "null", "zero", "border", "boundary",
                         "large", "small", "max", "min", "overflow", "special"]
        
        for test_name in self._extract_failing_tests():
            for pattern in edge_patterns:
                if pattern in test_name.lower():
                    return True
        
        # Look for edge case mentions in assertion
        assertion = self._extract_assertion()
        if assertion:
            for pattern in edge_patterns:
                if pattern in assertion.get("expected", "").lower() or \
                   pattern in assertion.get("actual", "").lower():
                    return True
        
        return False


def _classify_and_decide_repair(test_output: str, proposed_fix: str,
                                  target_file: str, repair_history: list,
                                  repo_files: list, localization_evidence: dict,
                                  current_path: str) -> Tuple[str, str, str]:
    """
    Classify failure and decide whether to stop, repair, or escalate.
    
    Returns (action, category, reason)
    """
    classifier = FailureClassifier(test_output, proposed_fix, target_file,
                                     repair_history, repo_files, localization_evidence)
    category, action, reason = classifier.classify()
    
    # If action is ESCALATE, determine target path
    if action == "ESCALATE":
        if current_path == "PATH_A":
            target_path = "PATH_B"
        else:
            target_path = "PATH_C"
        return (action, category, f"{reason} -> escalate to {target_path}")
    
    return (action, category, reason)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Adaptive Multi-Agent System")
    parser.add_argument("--task", required=True, help="Path to benchmark task JSON")
    parser.add_argument("--output-dir", default="evaluation/results", help="Results directory")
    args = parser.parse_args()

    with open(args.task) as f:
        task = json.load(f)

    result = run_task(task)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{result['task_id']}_adaptive_multi_agent.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n[ADAPTIVE] Result saved to {out_path}")
    print(f"  Status: {result['execution']['status']}")
    print(f"  Resolved: {result['end_to_end_resolved']}")
    print(f"  Initial path: {result['adaptive']['initial_path']}")
    print(f"  Final path: {result['adaptive']['final_path']}")
    print(f"  Escalated: {result['adaptive']['escalated']}")
    print(f"  Difficulty: {result['adaptive']['difficulty_class']} (score={result['adaptive']['difficulty_score']:.1f})")
    print(f"  LLM calls: {result['execution']['llm_calls']}")
    print(f"  Latency: {result['execution']['latency_seconds']}s")
    print(f"  Cost: ${result['cost']['estimated_usd']}")
