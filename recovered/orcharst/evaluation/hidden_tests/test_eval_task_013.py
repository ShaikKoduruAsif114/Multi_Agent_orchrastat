"""
evaluation/hidden_tests/test_eval_task_013.py

INDEPENDENT EVALUATION TESTS — Task 013 (text_stats)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_013.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/text_stats.py when
EVAL_FIX_MODULE=src.text_stats is set, so `from src.text_stats import ...`
resolves against the proposed fix.
"""
from src.text_stats import word_frequencies, top_words, letter_frequency

def test_word_frequencies_case_insensitive():
    freq = word_frequencies("The cat and the dog")
    assert freq["the"] == 2
    assert "The" not in freq

def test_top_words_tie_break_alphabetical():
    result = top_words("b a c a b c d", 3)
    assert result[0] == ("a", 2)
    assert result[1][0] == "b"
    assert result[2][0] == "c"

def test_top_words_respects_n():
    result = top_words("one two one two one three", 2)
    assert result == [("one", 3), ("two", 2)]

def test_letter_frequency_ignores_non_alpha():
    freq = letter_frequency("a a! b?")
    assert freq == {"a": 2, "b": 1}
