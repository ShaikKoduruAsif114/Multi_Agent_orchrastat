"""
evaluation/hidden_tests/test_eval_task_015.py

INDEPENDENT EVALUATION TESTS — Task 015 (pagination)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_015.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/pagination.py when
EVAL_FIX_MODULE=src.pagination is set, so `from src.pagination import ...`
resolves against the proposed fix.
"""
import pytest
from src.pagination import paginate, total_pages, page_bounds

def test_paginate_first_page():
    items = list(range(10))
    assert paginate(items, 1, 4) == [0, 1, 2, 3]

def test_paginate_middle_page():
    items = list(range(10))
    assert paginate(items, 2, 4) == [4, 5, 6, 7]

def test_paginate_last_partial_page():
    items = list(range(10))
    assert paginate(items, 3, 4) == [8, 9]

def test_paginate_beyond_end():
    items = list(range(5))
    assert paginate(items, 9, 4) == []

def test_total_pages_ceil():
    assert total_pages(10, 4) == 3
    assert total_pages(8, 4) == 2
    assert total_pages(1, 4) == 1
    assert total_pages(0, 4) == 0

def test_page_bounds():
    assert page_bounds(2, 4, 10) == (4, 8)
    assert page_bounds(3, 4, 10) == (8, 10)
