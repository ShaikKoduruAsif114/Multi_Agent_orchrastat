"""
evaluation/hidden_tests/test_eval_task_011.py

INDEPENDENT EVALUATION TESTS — Task 011 (temperature)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_011.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/temperature.py when
EVAL_FIX_MODULE=src.temperature is set, so `from src.temperature import ...`
resolves against the proposed fix.
"""
import pytest
from src.temperature import celsius_to_fahrenheit, fahrenheit_to_celsius

def test_celsius_to_fahrenheit_boiling_point():
    assert celsius_to_fahrenheit(100) == pytest.approx(212.0)

def test_celsius_to_fahrenheit_freezing_point():
    assert celsius_to_fahrenheit(0) == pytest.approx(32.0)

def test_fahrenheit_to_celsius_boiling_point():
    assert fahrenheit_to_celsius(212) == pytest.approx(100.0)

def test_fahrenheit_to_celsius_freezing_point():
    assert fahrenheit_to_celsius(32) == pytest.approx(0.0)

def test_round_trip():
    assert fahrenheit_to_celsius(celsius_to_fahrenheit(37)) == pytest.approx(37.0)

def test_negative_fahrenheit():
    assert fahrenheit_to_celsius(-40) == pytest.approx(-40.0)
