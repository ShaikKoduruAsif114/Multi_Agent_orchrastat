"""
evaluation/hidden_tests/test_eval_task_006.py

INDEPENDENT EVALUATION TESTS — Task 006 (inventory_manager)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_006.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/inventory_manager.py when
EVAL_FIX_MODULE=src.inventory_manager is set, so `from src.inventory_manager import ...`
resolves against the proposed fix.
"""
import pytest
from src.inventory_manager import Inventory

def test_restock_new_item_does_not_crash():
    inv = Inventory()
    inv.restock("Widget", 5)
    assert inv.get_stock("Widget") == 5

def test_restock_existing_item_accumulates():
    inv = Inventory()
    inv.restock("Widget", 5)
    inv.restock("Widget", 3)
    assert inv.get_stock("Widget") == 8

def test_sell_and_values():
    inv = Inventory()
    inv.restock("A", 10)
    inv.sell("A", 4)
    assert inv.get_stock("A") == 6

def test_sell_too_much_raises():
    inv = Inventory()
    inv.restock("A", 2)
    with pytest.raises(ValueError):
        inv.sell("A", 5)

def test_low_stock_includes_threshold():
    inv = Inventory()
    inv.restock("A", 10)
    inv.restock("B", 11)
    inv.restock("C", 30)
    low = inv.get_low_stock(10)
    assert low.get("A") == 10
    assert "B" not in low
    assert "C" not in low
