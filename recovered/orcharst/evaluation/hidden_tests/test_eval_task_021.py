"""
evaluation/hidden_tests/test_eval_task_021.py

INDEPENDENT EVALUATION TESTS — Task 021 (ledger)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_021.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/ledger.py when
EVAL_FIX_MODULE=src.ledger is set, so `from src.ledger import ...`
resolves against the proposed fix.
"""
import pytest
from src.ledger import Ledger

def test_batch_all_succeed():
    led = Ledger()
    led.open_account("a", 100)
    led.open_account("b", 0)
    n = led.commit_batch([("a", "b", 30), ("b", "a", 10)])
    assert n == 2
    assert led.balance("a") == 80
    assert led.balance("b") == 20

def test_batch_is_atomic_on_failure():
    led = Ledger()
    led.open_account("a", 100)
    led.open_account("b", 0)
    led.open_account("c", 0)
    with pytest.raises(ValueError):
        led.commit_batch([("a", "b", 60), ("a", "c", 60)])
    assert led.balance("a") == 100
    assert led.balance("b") == 0
    assert led.balance("c") == 0

def test_single_transfer_rolls_back():
    led = Ledger()
    led.open_account("x", 10)
    with pytest.raises(ValueError):
        led.commit_batch([("x", "y", 50)])
    assert led.balance("x") == 10

def test_open_account_duplicate_raises():
    led = Ledger()
    led.open_account("d", 5)
    with pytest.raises(ValueError):
        led.open_account("d", 5)
