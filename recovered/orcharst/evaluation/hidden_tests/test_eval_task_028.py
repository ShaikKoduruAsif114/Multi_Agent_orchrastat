"""
evaluation/hidden_tests/test_eval_task_028.py

INDEPENDENT EVALUATION TESTS — Task 028 (retry_policy)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_028.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/retry_policy.py when
EVAL_FIX_MODULE=src.retry_policy is set, so `from src.retry_policy import ...`
resolves against the proposed fix.
"""
import pytest
from src.retry_policy import backoff_delay, retry_call, parse_retry_after

def test_backoff_growth_is_capped():
    delays = [backoff_delay(a, base=0.5, max_delay=2.0) for a in range(6)]
    assert delays == [0.5, 1.0, 2.0, 2.0, 2.0, 2.0]

def test_backoff_default_cap():
    assert backoff_delay(20) == 30.0

def test_retry_call_forwards_args():
    calls = []
    def flaky(a, b):
        calls.append((a, b))
        if len(calls) < 3:
            raise IOError("transient")
        return a + b
    result = retry_call(flaky, 2, 3)
    assert result == 5
    assert calls == [(2, 3), (2, 3), (2, 3)]

def test_retry_call_eventual_failure_reraises():
    def always_fail(x):
        raise ValueError(f"bad {x}")
    with pytest.raises(ValueError):
        retry_call(always_fail, 7, retries=2)

def test_retry_call_zero_retries():
    def ok():
        return "done"
    assert retry_call(ok, retries=0) == "done"

def test_parse_retry_after():
    assert parse_retry_after("5") == 5.0
