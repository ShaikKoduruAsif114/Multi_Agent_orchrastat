"""
evaluation/hidden_tests/test_eval_task_024.py

INDEPENDENT EVALUATION TESTS — Task 024 (lru_cache)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_024.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/lru_cache.py when
EVAL_FIX_MODULE=src.lru_cache is set, so `from src.lru_cache import ...`
resolves against the proposed fix.
"""
from src.lru_cache import LRUCache

def test_put_and_get():
    cache = LRUCache(2)
    cache.put("a", 1)
    assert cache.get("a") == 1

def test_evicts_least_recently_used():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3

def test_get_refreshes_recency():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1

def test_update_existing_key_no_eviction():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 10)
    assert len(cache) == 2
    assert cache.get("a") == 10

def test_capacity_never_exceeded():
    cache = LRUCache(3)
    for i in range(10):
        cache.put(f"k{i}", i)
    assert len(cache) == 3

def test_order_snapshot_reflects_recency():
    cache = LRUCache(2)
    cache.put("x", 1)
    cache.put("y", 2)
    cache.get("x")
    assert cache.keys_snapshot() == ["y", "x"]
