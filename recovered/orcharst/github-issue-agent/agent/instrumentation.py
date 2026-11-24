"""
agent/instrumentation.py

Central instrumentation for the GitHub Issue Agent.

Every real LLM invocation, GitHub/local-repo tool call, node execution, and
sandbox run is recorded into an EvalContext. When no context is active every
hook is a no-op, so production behavior is unchanged.

The evaluation harness installs one EvalContext per benchmark run. Contexts are
thread-local so concurrent runs (multi-tenant web server, parallel benchmark
workers) do not interfere.

On purpose: LLM call counting happens ONLY at the single choke point
``agent.nodes.invoke_llm_with_timeout`` via ``record_llm_call``. No node
increments counters manually anymore (that was inconsistent).
"""

from __future__ import annotations

import functools
import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
from typing import List, Optional

# Canonical LLM stage labels
STAGE_RESEARCH = "research"
STAGE_PLAN = "plan"
STAGE_CODE_GEN = "code_gen"
STAGE_TEST_GEN = "test_gen"

# Requested model identity recorded on the context at creation time.
def _requested_model() -> str:
    try:
        from agent.provider import model_name, provider_name
        provider_name()
        return model_name()
    except Exception:
        return os.getenv("NARAROUTER_MODEL", "laguna-s-2.1") or ""


@dataclass
class LlmCallRecord:
    stage: str = "unlabeled"
    start: float = 0.0
    end: float = 0.0
    latency: float = 0.0
    ok: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""
    served_model: str = ""
    http_status: Optional[int] = None
    failure_category: str = ""      # populated when ok=False (taxonomy)


@dataclass
class ToolCallRecord:
    tool: str = ""
    start: float = 0.0
    end: float = 0.0
    latency: float = 0.0
    ok: bool = False


@dataclass
class NodeRunRecord:
    node: str = ""
    start: float = 0.0
    end: float = 0.0
    latency: float = 0.0
    ok: bool = True
    error: str = ""


@dataclass
class SandboxRunRecord:
    attempt: int = 0
    mode: str = ""          # "docker" | "subprocess"
    start: float = 0.0
    end: float = 0.0
    latency: float = 0.0
    passed: bool = False
    output_len: int = 0
    tests_total: int = 0
    tests_passed_count: int = 0
    tests_failed: int = 0
    collection_error: bool = False
    failure_category: str = ""


@dataclass
class RetryRecord:
    attempt: int = 0
    reason: str = ""
    fixed: bool = False
    feedback_tokens: int = 0
    failure_category: str = ""      # taxonomy value from provider.classify
    triggered_by: str = ""           # "generated_tests" | "hidden_tests" | "human_feedback"
@dataclass
class EvalContext:
    """Per-run instrumentation container."""

    def __init__(self, task_id: str = "", system: str = "", repo_url: str = "",
                 fixture_path: str = ""):
        self.task_id = task_id
        self.system = system
        self.repo_url = repo_url
        self.fixture_path = fixture_path      # "" => GitHub backend
        self.start = time.monotonic()
        self.provider: dict = {"provider": "nara",
                               "requested_model": _requested_model(),
                               "client_retries": 0}
        self.llm_calls: List[LlmCallRecord] = []
        self.tool_calls: List[ToolCallRecord] = []
        self.node_runs: List[NodeRunRecord] = []
        self.sandbox_runs: List[SandboxRunRecord] = []
        self.retries: List[RetryRecord] = []
        self.retry_count_state: int = 0
        self.extra: dict = {}

    # ---- derived metrics -------------------------------------------------
    def total_llm_calls(self) -> int:
        return len(self.llm_calls)

    def llm_calls_by_stage(self) -> dict:
        out: dict = {}
        for c in self.llm_calls:
            out[c.stage] = out.get(c.stage, 0) + 1
        return out

    def input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.llm_calls)

    def output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.llm_calls)

    def total_tokens(self) -> int:
        return self.input_tokens() + self.output_tokens()

    def llm_latency_total(self) -> float:
        return sum(c.latency for c in self.llm_calls)

    def tool_call_count(self) -> int:
        return len(self.tool_calls)

    def tool_calls_by_name(self) -> dict:
        out: dict = {}
        for t in self.tool_calls:
            out[t.tool] = out.get(t.tool, 0) + 1
        return out

    def node_latency(self, node: str) -> float:
        return sum(n.latency for n in self.node_runs if n.node == node)

    def sandbox_latency_total(self) -> float:
        return sum(s.latency for s in self.sandbox_runs)

    def workflow_latency(self) -> float:
        return time.monotonic() - self.start

    def provider_failures(self) -> List[LlmCallRecord]:
        """LLM calls that failed with a classified provider failure."""
        from agent.provider import classify_provider_failure
        out = []
        for c in self.llm_calls:
            if c.ok:
                continue
            if c.failure_category:
                is_provider = c.failure_category.startswith("provider_")
            else:
                cat, is_provider = classify_provider_failure(c.error or "llm call failed")
            if is_provider:
                out.append(c)
        return out

    # ---- serialization ---------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "system": self.system,
            "repo_url": self.repo_url,
            "fixture_path": self.fixture_path,
            "provider": self.provider,
            "workflow_latency": round(self.workflow_latency(), 4),
            "llm_calls_total": self.total_llm_calls(),
            "llm_calls_by_stage": self.llm_calls_by_stage(),
            "input_tokens": self.input_tokens(),
            "output_tokens": self.output_tokens(),
            "total_tokens": self.total_tokens(),
            "llm_latency_total": round(self.llm_latency_total(), 4),
            "llm_calls": [asdict(c) for c in self.llm_calls],
            "tool_calls_total": self.tool_call_count(),
            "tool_calls_by_name": self.tool_calls_by_name(),
            "tool_calls": [asdict(t) for t in self.tool_calls],
            "node_runs": [asdict(n) for n in self.node_runs],
            "sandbox_runs": [asdict(s) for s in self.sandbox_runs],
            "sandbox_latency_total": round(self.sandbox_latency_total(), 4),
            "retries": [asdict(r) for r in self.retries],
            "retry_count": self.retry_count_state,
            "extra": self.extra,
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
# ---------------------------------------------------------------------------
# Thread-local context management
# ---------------------------------------------------------------------------

_local = threading.local()


def get_active_context() -> Optional[EvalContext]:
    return getattr(_local, "context", None)


def set_active_context(ctx: Optional[EvalContext]) -> None:
    _local.context = ctx


@contextmanager
def active_eval_context(task_id: str = "", system: str = "", repo_url: str = "",
                        fixture_path: str = ""):
    """Install a fresh EvalContext for the duration of the with-block."""
    ctx = EvalContext(task_id, system, repo_url, fixture_path)
    prev = getattr(_local, "context", None)
    _local.context = ctx
    try:
        yield ctx
    finally:
        _local.context = prev


# ---------------------------------------------------------------------------
# Recording helpers (no-ops when no context is active)
# ---------------------------------------------------------------------------

def record_llm_call(stage: str, start: float, end: float, ok: bool,
                    input_tokens: int = 0, output_tokens: int = 0,
                    error: str = "", served_model: str = "",
                    http_status: Optional[int] = None) -> None:
    ctx = get_active_context()
    if ctx is None:
        return
    failure_category = ""
    if not ok:
        from agent.provider import classify_provider_failure
        failure_category, _ = classify_provider_failure(error or "llm call failed")
    ctx.llm_calls.append(LlmCallRecord(
        stage=stage, start=start, end=end, latency=round(end - start, 4),
        ok=ok, input_tokens=input_tokens, output_tokens=output_tokens,
        error=error, served_model=served_model,
        http_status=http_status, failure_category=failure_category,
    ))


def record_tool_call(tool: str, start: float, end: float, ok: bool) -> None:
    ctx = get_active_context()
    if ctx is None:
        return
    ctx.tool_calls.append(ToolCallRecord(
        tool=tool, start=start, end=end, latency=round(end - start, 4), ok=ok,
    ))


def record_node_run(node: str, start: float, end: float, ok: bool = True,
                    error: str = "") -> None:
    ctx = get_active_context()
    if ctx is None:
        return
    ctx.node_runs.append(NodeRunRecord(
        node=node, start=start, end=end, latency=round(end - start, 4),
        ok=ok, error=error,
    ))


def record_sandbox_run(attempt: int, mode: str, start: float, end: float,
                       passed: bool, output_len: int, tests_total: int = 0,
                       tests_passed_count: int = 0, tests_failed: int = 0,
                       collection_error: bool = False,
                       failure_category: str = "") -> None:
    ctx = get_active_context()
    if ctx is None:
        return
    ctx.sandbox_runs.append(SandboxRunRecord(
        attempt=attempt, mode=mode, start=start, end=end,
        latency=round(end - start, 4), passed=passed, output_len=output_len,
        tests_total=tests_total, tests_passed_count=tests_passed_count,
        tests_failed=tests_failed, collection_error=collection_error,
        failure_category=failure_category,
    ))


def record_retry(attempt: int, reason: str, fixed: bool,
                 feedback_tokens: int = 0, failure_category: str = "",
                 triggered_by: str = "") -> None:
    ctx = get_active_context()
    if ctx is None:
        return
    ctx.retries.append(RetryRecord(
        attempt=attempt, reason=reason, fixed=fixed,
        feedback_tokens=feedback_tokens,
        failure_category=failure_category, triggered_by=triggered_by,
    ))


def set_retry_count(count: int) -> None:
    ctx = get_active_context()
    if ctx is None:
        return
    ctx.retry_count_state = count
# ---------------------------------------------------------------------------
# Decorators / context managers used by nodes and tools
# ---------------------------------------------------------------------------

class _NoopTimer:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _ToolTimer:
    def __init__(self, name: str):
        self.name = name
        self.start = 0.0

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb):
        record_tool_call(self.name, self.start, time.monotonic(), ok=(exc_type is None))
        return False


def tool_timer(name: str):
    """Context manager recording a tool call to the active context."""
    if get_active_context() is None:
        return _NoopTimer()
    return _ToolTimer(name)


def timed_node(fn):
    """Decorator that records node entry/exit timings in the active context."""
    @functools.wraps(fn)
    def wrapper(state, *args, **kwargs):
        ctx = get_active_context()
        if ctx is None:
            return fn(state, *args, **kwargs)
        start = time.monotonic()
        try:
            out = fn(state, *args, **kwargs)
            record_node_run(fn.__name__, start, time.monotonic(), ok=True)
        except Exception as e:  # record then re-raise
            record_node_run(fn.__name__, start, time.monotonic(), ok=False, error=str(e))
            raise
        return out
    return wrapper


def wrap_tool(fn, name: str):
    """Wrap a plain python function so calls are recorded as tool calls."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        ctx = get_active_context()
        if ctx is None:
            return fn(*args, **kwargs)
        start = time.monotonic()
        try:
            out = fn(*args, **kwargs)
            record_tool_call(name, start, time.monotonic(), ok=True)
            return out
        except Exception:
            record_tool_call(name, start, time.monotonic(), ok=False)
            raise
    return wrapper


def snapshot_into_state(state: dict) -> dict:
    """Copy authoritative instrumentation numbers into the agent state dict.

    Called at the end of a run so ``state['llm_calls']`` and token fields
    always reflect what was really observed (never a drifting manual counter).
    Kept lenient because AgentState is a TypedDict, not a runtime schema.
    """
    ctx = get_active_context()
    if ctx is not None:
        state["llm_calls"] = ctx.total_llm_calls()
        state["input_tokens"] = ctx.input_tokens()
        state["output_tokens"] = ctx.output_tokens()
        state["retry_count"] = ctx.retry_count_state
        # Full authoritative instrumentation snapshot for the eval harness.
        state["eval_metrics"] = ctx.to_dict()
    return state