"""
evaluation/hidden_tests/test_eval_task_005.py

INDEPENDENT EVALUATION TESTS — Task 005 (bank_account.py)

These tests are written by a human evaluator BEFORE running the benchmark.
They are NEVER shown to the agent or used in any LLM prompt.

Key subtlety: apply_interest
  - Simple interest: 1000 + (1000 * 0.1 * 3) = 1300.0
  - Compound interest: 1000 * (1.1)^3 = 1331.0
"""
import pytest


class TestWithdraw:
    def test_withdraw_insufficient_raises(self, fixed_bank_account):
        """withdraw(500) when balance=50 must raise ValueError."""
        acc = fixed_bank_account.BankAccount("Alice", 50.0)
        with pytest.raises(ValueError):
            acc.withdraw(500)

    def test_withdraw_exact_balance_allowed(self, fixed_bank_account):
        """withdraw(50) when balance=50 must be allowed."""
        acc = fixed_bank_account.BankAccount("Alice", 50.0)
        result = acc.withdraw(50.0)
        assert acc.get_balance() == pytest.approx(0.0)

    def test_withdraw_normal_reduces_balance(self, fixed_bank_account):
        """withdraw(30) from balance=100 must leave 70."""
        acc = fixed_bank_account.BankAccount("Bob", 100.0)
        acc.withdraw(30.0)
        assert acc.get_balance() == pytest.approx(70.0)

    def test_withdraw_does_not_allow_negative_balance(self, fixed_bank_account):
        """After failed withdraw, balance must not go negative."""
        acc = fixed_bank_account.BankAccount("Carol", 50.0)
        try:
            acc.withdraw(200.0)
        except ValueError:
            pass
        assert acc.get_balance() >= 0, "Balance must not go negative after rejected withdraw"

    def test_withdraw_zero_raises(self, fixed_bank_account):
        """withdraw(0) must still raise ValueError (not positive)."""
        acc = fixed_bank_account.BankAccount("Dave", 100.0)
        with pytest.raises(ValueError):
            acc.withdraw(0)


class TestTransfer:
    def test_transfer_insufficient_sender_raises(self, fixed_bank_account):
        """transfer(1000) from balance=0 must raise ValueError."""
        sender = fixed_bank_account.BankAccount("Bob", 0.0)
        receiver = fixed_bank_account.BankAccount("Carol", 100.0)
        with pytest.raises(ValueError):
            sender.transfer(receiver, 1000.0)

    def test_transfer_leaves_receiver_unchanged_on_failure(self, fixed_bank_account):
        """On failed transfer, receiver balance must not change."""
        sender = fixed_bank_account.BankAccount("Bob", 0.0)
        receiver = fixed_bank_account.BankAccount("Carol", 100.0)
        try:
            sender.transfer(receiver, 1000.0)
        except ValueError:
            pass
        assert receiver.get_balance() == pytest.approx(100.0)

    def test_transfer_valid_moves_funds(self, fixed_bank_account):
        """transfer(50) from balance=100 must work correctly."""
        sender = fixed_bank_account.BankAccount("Eve", 100.0)
        receiver = fixed_bank_account.BankAccount("Frank", 50.0)
        sender.transfer(receiver, 50.0)
        assert sender.get_balance() == pytest.approx(50.0)
        assert receiver.get_balance() == pytest.approx(100.0)


class TestApplyInterest:
    def test_apply_interest_compound_1000_10pct_3yr(self, fixed_bank_account):
        """apply_interest(0.1, 3) on 1000 must give 1331.0 (compound), not 1300.0 (simple)."""
        acc = fixed_bank_account.BankAccount("Dave", 1000.0)
        result = acc.apply_interest(0.1, 3)
        assert result == pytest.approx(1331.0, rel=1e-3), (
            f"Expected 1331.0 (compound interest), got {result}. "
            f"Simple interest (wrong) would give 1300.0"
        )

    def test_apply_interest_not_simple(self, fixed_bank_account):
        """apply_interest result must NOT equal simple interest result."""
        acc = fixed_bank_account.BankAccount("Dave", 1000.0)
        result = acc.apply_interest(0.1, 3)
        simple_interest_result = 1300.0
        assert result != pytest.approx(simple_interest_result, rel=1e-3), (
            "Bug still present: using simple interest formula instead of compound"
        )

    def test_apply_interest_one_year(self, fixed_bank_account):
        """apply_interest(0.1, 1) on 1000 must give 1100.0."""
        acc = fixed_bank_account.BankAccount("Grace", 1000.0)
        result = acc.apply_interest(0.1, 1)
        assert result == pytest.approx(1100.0, rel=1e-3)

    def test_apply_interest_updates_balance(self, fixed_bank_account):
        """apply_interest must update self.balance in place."""
        acc = fixed_bank_account.BankAccount("Heidi", 1000.0)
        acc.apply_interest(0.1, 3)
        assert acc.get_balance() == pytest.approx(1331.0, rel=1e-3)


class TestRegressionNoBreakage:
    def test_deposit_still_works(self, fixed_bank_account):
        acc = fixed_bank_account.BankAccount("Ivan", 100.0)
        acc.deposit(50.0)
        assert acc.get_balance() == pytest.approx(150.0)

    def test_transaction_count_tracked(self, fixed_bank_account):
        acc = fixed_bank_account.BankAccount("Jack", 100.0)
        acc.deposit(10.0)
        acc.withdraw(5.0)
        assert acc.transaction_count() == 2
