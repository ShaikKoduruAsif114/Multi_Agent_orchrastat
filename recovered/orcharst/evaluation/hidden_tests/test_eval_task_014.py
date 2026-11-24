"""
evaluation/hidden_tests/test_eval_task_014.py

INDEPENDENT EVALUATION TESTS — Task 014 (queue_manager)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_014.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/queue_manager.py when
EVAL_FIX_MODULE=src.queue_manager is set, so `from src.queue_manager import ...`
resolves against the proposed fix.
"""
from src.queue_manager import TaskQueue

def test_fifo_order():
    q = TaskQueue()
    q.push("first")
    q.push("second")
    q.push("third")
    assert q.pop() == "first"
    assert q.pop() == "second"

def test_peek_returns_oldest():
    q = TaskQueue()
    q.push("a")
    q.push("b")
    assert q.peek() == "a"
    assert len(q) == 2

def test_pop_empty_returns_none():
    q = TaskQueue()
    assert q.pop() is None

def test_peek_empty_returns_none():
    q = TaskQueue()
    assert q.peek() is None

def test_mixed_usage():
    q = TaskQueue()
    assert q.pop() is None
    q.push(1)
    q.push(2)
    assert q.pop() == 1
    q.push(3)
    assert q.pop() == 2
    assert q.pop() == 3
    assert q.pop() is None
