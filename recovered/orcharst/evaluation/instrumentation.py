"""
evaluation/instrumentation.py

Structured instrumentation for per-task evaluation results.
Every benchmark task execution writes a machine-readable JSON result to
evaluation/results/<task_id>_<system>.json.

DO NOT fabricate, estimate, or hard-code any metric.
Use null (None) when a value cannot be measured.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


@dataclass
class LocalizationResult:
    predicted_file: Optional[str] = None
    gold_file: Optional[str] = None
    top1_correct: Optional[bool] = None
    # top3 not applicable when agent returns only 1 file
    top3_correct: Optional[bool] = None
    hallucinated_file: Optional[bool] = None  # predicted file not in repo


@dataclass
class PatchResult:
    generated: Optional[bool] = None
    is_placeholder: Optional[bool] = None   # LLM returned stub/fallback code
    syntax_valid: Optional[bool] = None
    files_changed: Optional[int] = None
    lines_added: Optional[int] = None
    lines_removed: Optional[int] = None
    patch_apply_success: Optional[bool] = None
    diff: Optional[str] = None              # unified diff string


@dataclass
class TestResult:
    generated: Optional[bool] = None
    generated_tests_executed: Optional[bool] = None
    generated_tests_passed: Optional[bool] = None
    generated_test_count: Optional[int] = None
    generated_tests_output: Optional[str] = None


@dataclass
class RegressionResult:
    hidden_tests_executed: Optional[bool] = None
    hidden_tests_passed: Optional[bool] = None
    hidden_tests_total: Optional[int] = None
    hidden_tests_passed_count: Optional[int] = None
    hidden_tests_output: Optional[str] = None
    regression_free: Optional[bool] = None  # hidden tests pass on fixed code


@dataclass
class RepairResult:
    attempts: Optional[int] = None          # total code generation attempts
    first_attempt_success: Optional[bool] = None
    resolved_within_retry_budget: Optional[bool] = None
    retry_budget: int = 3


@dataclass
class ExecutionResult:
    status: Optional[str] = None           # "resolved" | "patch_failed" | "test_failed" | "hidden_test_failed" | "timeout" | "error" | "unevaluable"
    failure_category: Optional[str] = None  # See FAILURE_ANALYSIS for taxonomy
    latency_seconds: Optional[float] = None
    llm_calls: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    sandbox_mode: Optional[str] = None     # "docker" | "subprocess"
    error_message: Optional[str] = None


@dataclass
class CostResult:
    # Cost is estimated from token counts using a fixed reference rate
    # ($0.59/M input, $0.79/M output). The pricing_note field records the
    # actual provider/model that served the request (see agent.provider).
    input_cost_usd: Optional[float] = None
    output_cost_usd: Optional[float] = None
    estimated_usd: Optional[float] = None
    pricing_note: str = "Estimated from token counts ($0.59/M input, $0.79/M output reference rate)"


@dataclass
class PRResult:
    branch_created: Optional[bool] = None
    commit_created: Optional[bool] = None
    pr_created: Optional[bool] = None
    pr_url: Optional[str] = None


@dataclass
class EvalResult:
    # Task identification
    task_id: str = ""
    system: str = ""                        # "multi_agent" | "baseline_a" | "baseline_b" | "ablation_*"
    repository: str = ""
    issue_id: Optional[str] = None
    issue_title: str = ""
    issue_body: str = ""
    timestamp: str = ""

    # Sub-results
    localization: LocalizationResult = field(default_factory=LocalizationResult)
    patch: PatchResult = field(default_factory=PatchResult)
    tests: TestResult = field(default_factory=TestResult)
    regression: RegressionResult = field(default_factory=RegressionResult)
    repair: RepairResult = field(default_factory=RepairResult)
    execution: ExecutionResult = field(default_factory=ExecutionResult)
    cost: CostResult = field(default_factory=CostResult)
    pr: PRResult = field(default_factory=PRResult)

    # Computed end-to-end resolution flag
    end_to_end_resolved: Optional[bool] = None


def compute_end_to_end(result: EvalResult) -> Optional[bool]:
    """
    END_TO_END_RESOLUTION requires ALL of:
    1. Patch was generated
    2. Patch syntax is valid
    3. Hidden tests pass
    4. Regression-free

    Returns None if any required field is None (unevaluable).
    Returns False if any condition fails.
    Returns True only if all conditions hold.
    """
    required = [
        result.patch.generated,
        result.patch.syntax_valid,
        result.regression.hidden_tests_passed,
        result.regression.regression_free,
    ]
    if any(v is None for v in required):
        return None
    return all(required)


def compute_cost(result: EvalResult) -> None:
    """Fill in cost fields from token counts using Groq pricing."""
    input_tokens = result.execution.input_tokens
    output_tokens = result.execution.output_tokens
    if input_tokens is None and output_tokens is None:
        return
    input_cost = ((input_tokens or 0) / 1_000_000) * 0.59
    output_cost = ((output_tokens or 0) / 1_000_000) * 0.79
    result.cost.input_cost_usd = round(input_cost, 6)
    result.cost.output_cost_usd = round(output_cost, 6)
    result.cost.estimated_usd = round(input_cost + output_cost, 6)


def save_result(result: EvalResult, results_dir: Optional[Path] = None) -> Path:
    """
    Serialize EvalResult to JSON and write to the results directory.
    Returns the path written.
    """
    if results_dir is None:
        results_dir = RESULTS_DIR
    results_dir.mkdir(parents=True, exist_ok=True)

    # Compute derived fields
    result.end_to_end_resolved = compute_end_to_end(result)
    compute_cost(result)

    filename = f"{result.task_id}_{result.system}.json"
    out_path = results_dir / filename

    # Convert to dict, preserving None as JSON null
    data = asdict(result)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    print(f"[EVAL] Result saved -> {out_path}")
    return out_path


def load_result(path: Path) -> EvalResult:
    """Load a saved EvalResult from JSON."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = EvalResult(
        task_id=data.get("task_id", ""),
        system=data.get("system", ""),
        repository=data.get("repository", ""),
        issue_id=data.get("issue_id"),
        issue_title=data.get("issue_title", ""),
        issue_body=data.get("issue_body", ""),
        timestamp=data.get("timestamp", ""),
        end_to_end_resolved=data.get("end_to_end_resolved"),
        localization=LocalizationResult(**data.get("localization", {})),
        patch=PatchResult(**data.get("patch", {})),
        tests=TestResult(**data.get("tests", {})),
        regression=RegressionResult(**data.get("regression", {})),
        repair=RepairResult(**data.get("repair", {})),
        execution=ExecutionResult(**data.get("execution", {})),
        cost=CostResult(**data.get("cost", {})),
        pr=PRResult(**data.get("pr", {})),
    )
    return result


def load_all_results(results_dir: Optional[Path] = None) -> list[EvalResult]:
    """Load all JSON result files from the results directory."""
    if results_dir is None:
        results_dir = RESULTS_DIR
    results = []
    if not results_dir.exists():
        return results
    for path in sorted(results_dir.glob("*.json")):
        try:
            results.append(load_result(path))
        except Exception as e:
            print(f"[EVAL] Warning: could not load {path}: {e}")
    return results


def make_timer():
    """Return a callable that gives elapsed seconds since creation."""
    start = time.monotonic()
    return lambda: round(time.monotonic() - start, 3)
