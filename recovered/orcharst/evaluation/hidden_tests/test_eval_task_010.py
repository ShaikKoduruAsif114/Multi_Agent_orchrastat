"""
evaluation/hidden_tests/test_eval_task_010.py

INDEPENDENT EVALUATION TESTS — Task 010 (email_validator)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_010.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/email_validator.py when
EVAL_FIX_MODULE=src.email_validator is set, so `from src.email_validator import ...`
resolves against the proposed fix.
"""
import pytest
from src.email_validator import is_valid_email, normalize, extract_domain

def test_valid_simple():
    assert is_valid_email("user@example.com") is True

def test_missing_tld_rejected():
    assert is_valid_email("user@localhost") is False
    assert is_valid_email("user@internal") is False

def test_no_at_rejected():
    assert is_valid_email("user.example.com") is False
    assert is_valid_email("") is False

def test_empty_local_part_rejected():
    assert is_valid_email("@example.com") is False

def test_normalize_preserves_local_case():
    assert normalize("John.Doe@Example.COM") == "John.Doe@example.com"

def test_extract_domain():
    assert extract_domain("a@Mail.Example.org") == "mail.example.org"
