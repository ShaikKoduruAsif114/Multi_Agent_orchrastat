"""
evaluation/hidden_tests/test_eval_task_023.py

INDEPENDENT EVALUATION TESTS — Task 023 (json_flattener)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_023.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/json_flattener.py when
EVAL_FIX_MODULE=src.json_flattener is set, so `from src.json_flattener import ...`
resolves against the proposed fix.
"""
from src.json_flattener import flatten_json, unflatten

def test_depth_three_nesting():
    flat = flatten_json({"a": {"b": {"c": 1}}})
    assert flat == {"a.b.c": 1}

def test_list_indices_zero_based():
    flat = flatten_json({"items": ["x", "y"]})
    assert flat == {"items.0": "x", "items.1": "y"}

def test_mixed_nesting():
    flat = flatten_json({"a": {"list": [1, {"deep": 2}]}, "b": 3})
    assert flat == {"a.list.0": 1, "a.list.1.deep": 2, "b": 3}

def test_scalars():
    assert flatten_json({"x": 5}) == {"x": 5}
    assert flatten_json({}) == {}
    assert flatten_json([]) == {}

def test_values_preserved():
    flat = flatten_json({"n": None, "f": 1.5, "s": "hi", "b": False})
    assert flat == {"n": None, "f": 1.5, "s": "hi", "b": False}

def test_unflatten_round_trip():
    original = {"a": {"b": 1}, "c": 2}
    assert unflatten(flatten_json(original)) == original
