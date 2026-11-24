"""
evaluation/hidden_tests/test_eval_task_029.py

INDEPENDENT EVALUATION TESTS — Task 029 (interval_merger)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_029.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/interval_merger.py when
EVAL_FIX_MODULE=src.interval_merger is set, so `from src.interval_merger import ...`
resolves against the proposed fix.
"""
from src.interval_merger import merge_intervals, insert_interval, total_coverage

def test_overlapping_merge():
    assert merge_intervals([(1, 4), (2, 5)]) == [(1, 5)]

def test_touching_intervals_merge():
    assert merge_intervals([(1, 3), (3, 5)]) == [(1, 5)]

def test_disjoint_stay_separate():
    assert merge_intervals([(1, 2), (4, 5)]) == [(1, 2), (4, 5)]

def test_unsorted_input():
    assert merge_intervals([(5, 7), (1, 3), (2, 4)]) == [(1, 4), (5, 7)]

def test_containment():
    assert merge_intervals([(1, 10), (2, 3)]) == [(1, 10)]

def test_insert_keeps_sorted():
    result = insert_interval([(1, 2), (7, 8)], (4, 5))
    assert result == [(1, 2), (4, 5), (7, 8)]

def test_insert_empty():
    assert insert_interval([], (0, 1)) == [(0, 1)]

def test_total_coverage_no_double_count():
    assert total_coverage([(1, 4), (3, 6), (8, 10)]) == 7
