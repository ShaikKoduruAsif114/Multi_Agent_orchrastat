from typing import TypedDict, Annotated, List, Any, Optional
import operator
from langchain_core.messages import AnyMessage


class AgentState(TypedDict):
    # User inputs
    repo_url: str
    session_id: str
    issue_number: int
    token: str
    problem_description: str
    mode: str                    # "issue" or "smart"
    is_web: bool                 # Web UI session flag

    # Fetched from GitHub
    issue_title: str
    issue_body: str

    # Agent outputs
    relevant_files: list[str]
    proposed_fix: str
    tests_written: str
    pr_url: str

    # Local subprocess verification
    tests_passed: bool
    test_results: str

    # Control
    messages: Annotated[list[AnyMessage], operator.add]
    human_approved: bool
    retry_count: int
    llm_calls: int
    errors: list[str]

    # -----------------------------------------------------------------------
    # Evaluation / Instrumentation fields (added for benchmark system)
    # -----------------------------------------------------------------------

    # Timing
    start_time: float            # monotonic time at workflow start (set by input_node)

    # Token tracking (aggregated across all LLM calls)
    input_tokens: int
    output_tokens: int

    # Patch provenance
    first_patch_source: str      # FIRST generated patch (pre-repair), for first-pass scoring

    # Patch quality
    original_file_content: str   # content of target file BEFORE fix
    patch_diff: str              # unified diff (original vs proposed_fix)
    lines_added: int
    lines_removed: int
    syntax_valid: bool           # True if proposed_fix passes ast.parse
    repair_plan: str
    localization_evidence: dict

    # Patch-quality gates (eval + production)
    patch_placeholder: bool      # True when generated patch matches known stub patterns
    patch_apply_success: bool    # True when the patch parses and targets a real file
    patch_target_valid: bool     # True when target file exists in the repository
    generated_code_is_model: bool  # True only when code came from a real LLM response

    # Targeted repair-loop tracking
    repair_attempts: list        # per-attempt structured records (failure extraction, fix strategy)
    repair_history: list         # summary of prior repair attempts fed to the repair prompt

    # Evaluation mode
    eval_mode: bool              # If True: auto-approve, skip PR, record results
    eval_task_id: str            # Benchmark task ID
    eval_gold_file: str          # Ground-truth target file for localization scoring
    eval_metrics: dict           # Instrumentation snapshot (EvalContext.to_dict) at end of run
    eval_approval_policy: str    # "auto" | "strict" (scripted human proxy)

    # -----------------------------------------------------------------------
    # V2 localization fields (staged Top-K research + adaptive retry)
    # -----------------------------------------------------------------------
    localization_candidates: list[dict]   # ranked candidate files with scores/reasons
    localization_stage: str              # which stage produced the final selection
    localization_revisit: bool           # True when a retry re-enters research_node
    localization_attempts: int           # how many times research_node has run
