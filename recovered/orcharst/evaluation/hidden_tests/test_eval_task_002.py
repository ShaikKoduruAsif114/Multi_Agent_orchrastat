"""
evaluation/hidden_tests/test_eval_task_002.py

INDEPENDENT EVALUATION TESTS — Task 002 (user_manager.py)

These tests are written by a human evaluator BEFORE running the benchmark.
They are NEVER shown to the agent or used in any LLM prompt.
"""
import pytest


class TestGetUser:
    def test_get_user_returns_name_key(self, fixed_user_manager, clean_db):
        """get_user() must return dict with key 'name', not 'username'."""
        fixed_user_manager.create_user(10, "Alice", "alice@example.com")
        user = fixed_user_manager.get_user(10)
        assert user is not None
        assert "name" in user, f"Key 'name' missing. Keys found: {list(user.keys())}"

    def test_get_user_name_value_correct(self, fixed_user_manager, clean_db):
        """get_user() must return the correct name value."""
        fixed_user_manager.create_user(11, "Bob", "bob@example.com")
        user = fixed_user_manager.get_user(11)
        assert user["name"] == "Bob"

    def test_get_user_no_username_key(self, fixed_user_manager, clean_db):
        """get_user() must NOT return 'username' key (old bug)."""
        fixed_user_manager.create_user(12, "Carol", "carol@example.com")
        user = fixed_user_manager.get_user(12)
        assert "username" not in user, "Old bug still present: key 'username' should be 'name'"

    def test_get_user_returns_correct_id(self, fixed_user_manager, clean_db):
        """get_user() must return correct id."""
        fixed_user_manager.create_user(13, "Dave", "dave@example.com")
        user = fixed_user_manager.get_user(13)
        assert user["id"] == 13

    def test_get_user_returns_email(self, fixed_user_manager, clean_db):
        """get_user() must include email field."""
        fixed_user_manager.create_user(14, "Eve", "eve@example.com")
        user = fixed_user_manager.get_user(14)
        assert user["email"] == "eve@example.com"

    def test_get_user_nonexistent_returns_none(self, fixed_user_manager, clean_db):
        """get_user() for unknown id must return None."""
        result = fixed_user_manager.get_user(9999)
        assert result is None


class TestUpdateEmail:
    def test_update_email_invalid_no_at_raises(self, fixed_user_manager, clean_db):
        """update_email() must reject email without '@'."""
        fixed_user_manager.create_user(20, "Frank", "frank@example.com")
        with pytest.raises((ValueError, Exception)):
            fixed_user_manager.update_email(20, "notanemail")

    def test_update_email_valid_accepted(self, fixed_user_manager, clean_db):
        """update_email() must accept valid email with '@'."""
        fixed_user_manager.create_user(21, "Grace", "grace@example.com")
        result = fixed_user_manager.update_email(21, "new@domain.com")
        assert result is True or result is not False

    def test_update_email_empty_raises(self, fixed_user_manager, clean_db):
        """update_email() must reject empty string as email."""
        fixed_user_manager.create_user(22, "Heidi", "heidi@example.com")
        with pytest.raises((ValueError, Exception)):
            fixed_user_manager.update_email(22, "")

    def test_update_email_missing_at_raises(self, fixed_user_manager, clean_db):
        """update_email() must reject 'plainaddress' (no @)."""
        fixed_user_manager.create_user(23, "Ivan", "ivan@example.com")
        with pytest.raises((ValueError, Exception)):
            fixed_user_manager.update_email(23, "plainaddress")


class TestRegressionNoBreakage:
    def test_create_user_still_works(self, fixed_user_manager, clean_db):
        fixed_user_manager.create_user(30, "Jack", "jack@test.com")
        assert fixed_user_manager.get_user(30) is not None

    def test_delete_user_still_works(self, fixed_user_manager, clean_db):
        fixed_user_manager.create_user(31, "Kate", "kate@test.com")
        result = fixed_user_manager.delete_user(31)
        assert result is True
        assert fixed_user_manager.get_user(31) is None
