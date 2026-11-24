"""
evaluation/hidden_tests/test_eval_task_004.py

INDEPENDENT EVALUATION TESTS — Task 004 (string_utils.py)

These tests are written by a human evaluator BEFORE running the benchmark.
They are NEVER shown to the agent or used in any LLM prompt.
"""
import pytest


class TestIsPalindrome:
    def test_palindrome_mixed_case_racecar(self, fixed_string_utils):
        """is_palindrome('Racecar') must return True."""
        result = fixed_string_utils.is_palindrome("Racecar")
        assert result is True, f"Expected True, got {result}"

    def test_palindrome_all_caps(self, fixed_string_utils):
        """is_palindrome('RACECAR') must return True."""
        assert fixed_string_utils.is_palindrome("RACECAR") is True

    def test_palindrome_lowercase(self, fixed_string_utils):
        """is_palindrome('racecar') must return True."""
        assert fixed_string_utils.is_palindrome("racecar") is True

    def test_palindrome_not_palindrome(self, fixed_string_utils):
        """is_palindrome('hello') must return False."""
        assert fixed_string_utils.is_palindrome("hello") is False

    def test_palindrome_single_char(self, fixed_string_utils):
        """is_palindrome('A') must return True."""
        assert fixed_string_utils.is_palindrome("A") is True

    def test_palindrome_level(self, fixed_string_utils):
        """is_palindrome('Level') must return True."""
        assert fixed_string_utils.is_palindrome("Level") is True


class TestCountWords:
    def test_count_words_double_space(self, fixed_string_utils):
        """count_words('hello  world') must return 2, not 3."""
        result = fixed_string_utils.count_words("hello  world")
        assert result == 2, f"Expected 2, got {result} (double-space bug?)"

    def test_count_words_single_space(self, fixed_string_utils):
        """count_words('one two three') must return 3."""
        assert fixed_string_utils.count_words("one two three") == 3

    def test_count_words_leading_trailing_spaces(self, fixed_string_utils):
        """count_words('  hello  ') must return 1."""
        assert fixed_string_utils.count_words("  hello  ") == 1

    def test_count_words_triple_space(self, fixed_string_utils):
        """count_words('a   b') must return 2."""
        assert fixed_string_utils.count_words("a   b") == 2

    def test_count_words_single_word(self, fixed_string_utils):
        """count_words('hello') must return 1."""
        assert fixed_string_utils.count_words("hello") == 1


class TestTruncate:
    def test_truncate_short_string_no_ellipsis(self, fixed_string_utils):
        """truncate('Hi there', 100) must return 'Hi there' without '...'."""
        result = fixed_string_utils.truncate("Hi there", 100)
        assert result == "Hi there", f"Expected 'Hi there', got '{result}'"

    def test_truncate_long_string_adds_ellipsis(self, fixed_string_utils):
        """truncate('Hello World', 5) must truncate and add '...'."""
        result = fixed_string_utils.truncate("Hello World", 5)
        assert "..." in result, f"Expected ellipsis for long string, got '{result}'"
        assert result.startswith("Hello"), f"Should start with 'Hello', got '{result}'"

    def test_truncate_exact_length_no_ellipsis(self, fixed_string_utils):
        """truncate('Hello', 5) must return 'Hello' (exact fit, no ellipsis)."""
        result = fixed_string_utils.truncate("Hello", 5)
        assert "..." not in result, f"Should not add ellipsis for exact fit, got '{result}'"

    def test_truncate_one_over_no_ellipsis_bug(self, fixed_string_utils):
        """truncate('Hi', 100) should NOT add '...' — was the main bug."""
        result = fixed_string_utils.truncate("Hi", 100)
        assert result == "Hi", f"Short string should not get '...', got '{result}'"


class TestRegressionNoBreakage:
    def test_reverse_string_unchanged(self, fixed_string_utils):
        assert fixed_string_utils.reverse_string("hello") == "olleh"

    def test_capitalize_words_unchanged(self, fixed_string_utils):
        assert fixed_string_utils.capitalize_words("hello world") == "Hello World"

    def test_count_vowels_unchanged(self, fixed_string_utils):
        assert fixed_string_utils.count_vowels("hello") == 2
