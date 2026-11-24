"""
evaluation/hidden_tests/test_eval_task_020.py

INDEPENDENT EVALUATION TESTS — Task 020 (rate_limiter)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_020.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/rate_limiter.py when
EVAL_FIX_MODULE=src.rate_limiter is set, so `from src.rate_limiter import ...`
resolves against the proposed fix.
"""
from src.rate_limiter import RateLimiter

def test_allows_up_to_limit():
    rl = RateLimiter(3, window_sec=10)
    assert rl.allow_request(1.0) is True
    assert rl.allow_request(2.0) is True
    assert rl.allow_request(3.0) is True

def test_blocks_beyond_limit():
    rl = RateLimiter(2, window_sec=10)
    rl.allow_request(1.0)
    rl.allow_request(2.0)
    assert rl.allow_request(3.0) is False

def test_window_expiry_frees_capacity():
    rl = RateLimiter(2, window_sec=5)
    assert rl.allow_request(1.0) is True
    assert rl.allow_request(2.0) is True
    assert rl.allow_request(6.5) is True
    assert rl.allow_request(7.0) is True

def test_old_hits_do_not_accumulate_forever():
    rl = RateLimiter(3, window_sec=4)
    for t in (0.5, 1.0, 1.5):
        rl.allow_request(t)
    assert rl.allow_request(10.0) is True
    assert rl.allow_request(10.5) is True
    assert rl.allow_request(11.0) is True
    assert rl.allow_request(11.5) is False

def test_hits_in_window_counts_correctly():
    rl = RateLimiter(5, window_sec=10)
    rl.allow_request(1.0)
    rl.allow_request(8.0)
    assert rl.hits_in_window(12.0) == 1
