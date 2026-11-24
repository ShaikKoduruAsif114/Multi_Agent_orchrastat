"""
evaluation/hidden_tests/test_eval_task_022.py

INDEPENDENT EVALUATION TESTS — Task 022 (feature_flags)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_022.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/feature_flags.py when
EVAL_FIX_MODULE=src.feature_flags is set, so `from src.feature_flags import ...`
resolves against the proposed fix.
"""
from src.feature_flags import FeatureFlags

def test_override_beats_everything():
    ff = FeatureFlags(
        overrides={"telemetry": False},
        environ={"FLAG_TELEMETRY": "true"},
    )
    assert ff.is_enabled("telemetry") is False

def test_env_beats_defaults():
    ff = FeatureFlags(environ={"FLAG_DARK_MODE": "yes"})
    assert ff.is_enabled("dark_mode") is True

def test_defaults_used_when_no_env():
    ff = FeatureFlags(environ={})
    assert ff.is_enabled("dark_mode") is False
    assert ff.is_enabled("telemetry") is True

def test_env_false_disables_flag():
    ff = FeatureFlags(environ={"FLAG_TELEMETRY": "0"})
    assert ff.is_enabled("telemetry") is False

def test_unknown_flag_returns_default():
    ff = FeatureFlags(environ={})
    assert ff.is_enabled("nope") is False
    assert ff.is_enabled("nope", default_for_unknown=True) is True

def test_all_flags_merges_layers():
    ff = FeatureFlags(
        overrides={"beta_api": True},
        environ={"FLAG_DARK_MODE": "true"},
    )
    flags = ff.all_flags()
    assert flags["beta_api"] is True
    assert flags["dark_mode"] is True
    assert flags["telemetry"] is True
