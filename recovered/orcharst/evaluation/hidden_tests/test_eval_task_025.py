"""
evaluation/hidden_tests/test_eval_task_025.py

INDEPENDENT EVALUATION TESTS — Task 025 (slugify)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_025.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/slugify.py when
EVAL_FIX_MODULE=src.slugify is set, so `from src.slugify import ...`
resolves against the proposed fix.
"""
from src.slugify import slugify, slugify_upper, truncate_slug

def test_basic():
    assert slugify("Hello World") == "hello-world"

def test_punctuation_stripped():
    assert slugify("Hello, World!") == "hello-world"

def test_multiple_separators_collapsed():
    assert slugify("a   b___c") == "a-b-c"

def test_leading_trailing_no_hyphens():
    assert slugify("  test  ") == "test"
    assert slugify("--deep--value--") == "deep-value"

def test_alnum_preserved():
    assert slugify("Python 3.12") == "python-3-12"

def test_upper_variant_and_truncate():
    assert slugify_upper("Hello World") == "HELLO-WORLD"
    assert truncate_slug("hello-world", 5) == "hello"
    assert truncate_slug("ab-cd", 10) == "ab-cd"
