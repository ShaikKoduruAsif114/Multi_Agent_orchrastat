"""
evaluation/hidden_tests/test_eval_task_019.py

INDEPENDENT EVALUATION TESTS — Task 019 (data_transform)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_019.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/data_transform.py when
EVAL_FIX_MODULE=src.data_transform is set, so `from src.data_transform import ...`
resolves against the proposed fix.
"""
from src.data_transform import group_by, flatten, dedupe

def test_group_by_appends_all():
    rows = [{"t": "a", "v": 1}, {"t": "b", "v": 2}, {"t": "a", "v": 3}]
    grouped = group_by(rows, lambda r: r["t"])
    assert grouped["a"] == [{"t": "a", "v": 1}, {"t": "a", "v": 3}]
    assert grouped["b"] == [{"t": "b", "v": 2}]

def test_group_by_empty():
    assert group_by([], lambda x: x) == {}

def test_flatten_deep_nesting():
    assert flatten([1, [2, [3, [4]], 5]]) == [1, 2, 3, 4, 5]

def test_flatten_empty_lists():
    assert flatten([[], [1, []], 2]) == [1, 2]
    assert flatten([]) == []

def test_dedupe_keeps_first():
    assert dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]

def test_dedupe_preserves_order():
    assert dedupe(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]
