"""
evaluation/hidden_tests/test_eval_task_009.py

INDEPENDENT EVALUATION TESTS — Task 009 (matrix_ops)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_009.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/matrix_ops.py when
EVAL_FIX_MODULE=src.matrix_ops is set, so `from src.matrix_ops import ...`
resolves against the proposed fix.
"""
import pytest
from src.matrix_ops import matrix_multiply, transpose

def test_matrix_multiply_correct():
    A = [[1, 2], [3, 4]]
    B = [[5, 6], [7, 8]]
    assert matrix_multiply(A, B) == [[19, 22], [43, 50]]

def test_matrix_multiply_shape_mismatch_raises():
    A = [[1, 2, 3]]
    B = [[1, 2]]
    with pytest.raises(ValueError):
        matrix_multiply(A, B)

def test_matrix_multiply_empty_inputs():
    assert matrix_multiply([], [[1]]) == []

def test_transpose_basic():
    M = [[1, 2, 3], [4, 5, 6]]
    assert transpose(M) == [[1, 4], [2, 5], [3, 6]]

def test_transpose_empty():
    assert transpose([]) == []
