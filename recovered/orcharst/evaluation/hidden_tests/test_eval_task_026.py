"""
evaluation/hidden_tests/test_eval_task_026.py

INDEPENDENT EVALUATION TESTS — Task 026 (statistics_utils)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_026.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/statistics_utils.py when
EVAL_FIX_MODULE=src.statistics_utils is set, so `from src.statistics_utils import ...`
resolves against the proposed fix.
"""
import pytest
from src.statistics_utils import median, percentile, mean

def test_median_odd():
    assert median([5, 1, 3]) == 3

def test_median_even_averages_middle():
    assert median([1, 2, 3, 4]) == 2.5
    assert median([4, 2]) == 3.0

def test_median_unsorted_input():
    assert median([9, 1, 8, 2]) == 5.0

def test_median_empty_raises():
    with pytest.raises(ValueError):
        median([])

def test_percentile_bounds():
    data = [10, 20, 30, 40]
    assert percentile(data, 0) == 10
    assert percentile(data, 100) == 40

def test_percentile_interpolates():
    data = [10, 20, 30, 40]
    assert percentile(data, 50) == 25.0

def test_percentile_out_of_range_raises():
    with pytest.raises(ValueError):
        percentile([1, 2], 150)

def test_mean():
    assert mean([2, 4, 6]) == 4.0
