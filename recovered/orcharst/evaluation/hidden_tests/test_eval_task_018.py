"""
evaluation/hidden_tests/test_eval_task_018.py

INDEPENDENT EVALUATION TESTS — Task 018 (session_store)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_018.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/session_store.py when
EVAL_FIX_MODULE=src.session_store is set, so `from src.session_store import ...`
resolves against the proposed fix.
"""
from src.session_store import SessionStore

def test_stores_are_independent():
    a = SessionStore()
    b = SessionStore()
    a.create("tok-a")
    a.create("tok-b")
    b.create("tok-c")
    assert a.get("tok-c") is None
    assert b.get("tok-a") is None
    assert len(b.sessions) == 1

def test_get_valid_session():
    store = SessionStore()
    store.create("tok", ttl=100)
    assert store.get("tok", now=50) is not None

def test_get_expired_session_returns_none():
    store = SessionStore()
    store.sessions["old"] = {"expires_at": 10, "data": {}}
    assert store.get("old", now=20) is None

def test_purge_expired_removes_only_expired():
    store = SessionStore()
    store.sessions["dead"] = {"expires_at": 5, "data": {}}
    store.sessions["alive"] = {"expires_at": 500, "data": {}}
    removed = store.purge_expired(now=100)
    assert removed == ["dead"]
    assert "alive" in store.sessions
    assert "dead" not in store.sessions

def test_purge_empty_returns_empty():
    assert SessionStore().purge_expired(now=1) == []
