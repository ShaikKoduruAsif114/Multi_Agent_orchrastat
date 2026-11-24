"""
evaluation/hidden_tests/test_eval_task_007.py

INDEPENDENT EVALUATION TESTS — Task 007 (date_utils)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_007.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/date_utils.py when
EVAL_FIX_MODULE=src.date_utils is set, so `from src.date_utils import ...`
resolves against the proposed fix.
"""
from datetime import date
from src.date_utils import days_between, is_weekend, add_days, days_in_month

def test_days_between_reversed_order_absolute():
    a = date(2024, 1, 10)
    b = date(2024, 1, 1)
    assert days_between(a, b) == 9
    assert days_between(b, a) == 9

def test_days_between_same_day():
    d = date(2024, 3, 15)
    assert days_between(d, d) == 0

def test_is_weekend_friday_is_not_weekend():
    friday = date(2024, 3, 15)  # a Friday
    assert is_weekend(friday) is False

def test_is_weekend_saturday_sunday():
    sat = date(2024, 3, 16)
    sun = date(2024, 3, 17)
    assert is_weekend(sat) is True
    assert is_weekend(sun) is True

def test_is_weekend_monday_false():
    mon = date(2024, 3, 18)
    assert is_weekend(mon) is False

def test_add_days_and_days_in_month():
    d = date(2024, 1, 28)
    assert add_days(d, 2) == date(2024, 1, 30)
    assert days_in_month(2024, 2) == 29
