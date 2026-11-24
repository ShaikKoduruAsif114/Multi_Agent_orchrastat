"""
evaluation/hidden_tests/test_eval_task_012.py

INDEPENDENT EVALUATION TESTS — Task 012 (config_loader)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_012.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/config_loader.py when
EVAL_FIX_MODULE=src.config_loader is set, so `from src.config_loader import ...`
resolves against the proposed fix.
"""
import pytest
from src.config_loader import Config, DEFAULTS

def test_get_missing_key_returns_default():
    cfg = Config()
    assert cfg.get("nonexistent", "fallback") == "fallback"

def test_set_is_instance_local():
    cfg_a = Config()
    cfg_b = Config()
    cfg_a.set("timeout", 99)
    assert cfg_b.get("timeout") == 30

def test_defaults_dict_not_polluted():
    before = dict(DEFAULTS)
    cfg = Config()
    cfg.set("brand_new_key", 123)
    assert "brand_new_key" not in DEFAULTS
    assert set(DEFAULTS) == set(before)

def test_overrides_applied():
    cfg = Config(timeout=5)
    assert cfg.get("timeout") == 5
    assert cfg.get("retries") == 3

def test_as_dict_snapshot():
    cfg = Config()
    cfg.set("x", 1)
    d = cfg.as_dict()
    d["x"] = 999
    assert cfg.get("x") == 1
