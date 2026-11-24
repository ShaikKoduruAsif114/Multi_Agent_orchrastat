"""
evaluation/hidden_tests/test_eval_task_001.py

INDEPENDENT EVALUATION TESTS — Task 001 (calculator.py)

These tests are written by a human evaluator BEFORE running the benchmark.
They are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_001.

The agent's proposed fix code is injected into this namespace at evaluation time.
"""
import pytest
import sys
import types


# ---------------------------------------------------------------------------
# Test Group A: divide() — ZeroDivisionError fix
# ---------------------------------------------------------------------------

class TestDivide:
    def test_divide_by_zero_raises_value_error(self, fixed_calculator):
        """divide(10, 0) must raise ValueError, not ZeroDivisionError."""
        with pytest.raises((ValueError, ZeroDivisionError)):
            fixed_calculator.divide(10, 0)

    def test_divide_by_zero_raises_value_error_strict(self, fixed_calculator):
        """divide(10, 0) must raise ValueError specifically (not ZeroDivisionError)."""
        with pytest.raises(ValueError):
            fixed_calculator.divide(10, 0)

    def test_divide_normal_positive(self, fixed_calculator):
        """divide(10, 2) must return 5.0."""
        assert fixed_calculator.divide(10, 2) == pytest.approx(5.0)

    def test_divide_normal_negative_divisor(self, fixed_calculator):
        """divide(-9, 3) must return -3.0."""
        assert fixed_calculator.divide(-9, 3) == pytest.approx(-3.0)

    def test_divide_float_result(self, fixed_calculator):
        """divide(7, 2) must return 3.5."""
        assert fixed_calculator.divide(7, 2) == pytest.approx(3.5)

    def test_divide_negative_by_negative(self, fixed_calculator):
        """divide(-6, -2) must return 3.0."""
        assert fixed_calculator.divide(-6, -2) == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Test Group B: percentage() — wrong formula fix
# ---------------------------------------------------------------------------

class TestPercentage:
    def test_percentage_basic(self, fixed_calculator):
        """percentage(200, 10) must return 20.0, not 200.0."""
        result = fixed_calculator.percentage(200, 10)
        assert result == pytest.approx(20.0), f"Expected 20.0, got {result}"

    def test_percentage_100(self, fixed_calculator):
        """percentage(500, 100) must return 500.0."""
        assert fixed_calculator.percentage(500, 100) == pytest.approx(500.0)

    def test_percentage_50(self, fixed_calculator):
        """percentage(200, 50) must return 100.0."""
        assert fixed_calculator.percentage(200, 50) == pytest.approx(100.0)

    def test_percentage_not_divided_by_10(self, fixed_calculator):
        """percentage(100, 10) must return 10.0, NOT 100.0 (old bug)."""
        result = fixed_calculator.percentage(100, 10)
        assert result != pytest.approx(100.0), "Bug still present: divides by 10 instead of 100"
        assert result == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Test Group C: factorial() — missing base case fix
# ---------------------------------------------------------------------------

class TestFactorial:
    def test_factorial_zero(self, fixed_calculator):
        """factorial(0) must return 1, not hit RecursionError."""
        result = fixed_calculator.factorial(0)
        assert result == 1, f"Expected 1, got {result}"

    def test_factorial_one(self, fixed_calculator):
        """factorial(1) must return 1."""
        assert fixed_calculator.factorial(1) == 1

    def test_factorial_five(self, fixed_calculator):
        """factorial(5) must return 120."""
        assert fixed_calculator.factorial(5) == 120

    def test_factorial_ten(self, fixed_calculator):
        """factorial(10) must return 3628800."""
        assert fixed_calculator.factorial(10) == 3628800


# ---------------------------------------------------------------------------
# Regression Group: existing correct functions must still work
# ---------------------------------------------------------------------------

class TestRegressionNoBreakage:
    def test_add_unchanged(self, fixed_calculator):
        assert fixed_calculator.add(2, 3) == 5

    def test_subtract_unchanged(self, fixed_calculator):
        assert fixed_calculator.subtract(10, 4) == 6

    def test_multiply_unchanged(self, fixed_calculator):
        assert fixed_calculator.multiply(3, 4) == 12

    def test_power_unchanged(self, fixed_calculator):
        assert fixed_calculator.power(2, 8) == 256
