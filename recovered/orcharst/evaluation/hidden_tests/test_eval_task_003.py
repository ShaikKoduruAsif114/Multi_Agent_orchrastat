"""
evaluation/hidden_tests/test_eval_task_003.py

INDEPENDENT EVALUATION TESTS — Task 003 (shopping_cart.py)

These tests are written by a human evaluator BEFORE running the benchmark.
They are NEVER shown to the agent or used in any LLM prompt.

Key subtlety: apply_discount bug is ONLY exposed when total != discount_percent.
E.g., 10% of $100 = $90 = $100 - 10 (accidentally correct), but
      10% of $200 = $180 ≠ $200 - 10 = $190 (bug exposed).
"""
import pytest


class TestGetTotal:
    def test_get_total_with_quantity(self, fixed_shopping_cart):
        """get_total() must multiply price by quantity."""
        cart = fixed_shopping_cart.ShoppingCart()
        cart.add_item("Book", 10.0, quantity=3)
        result = cart.get_total()
        assert result == pytest.approx(30.0), f"Expected 30.0, got {result} (quantity ignored?)"

    def test_get_total_default_quantity_one(self, fixed_shopping_cart):
        """get_total() with default quantity=1 must still work."""
        cart = fixed_shopping_cart.ShoppingCart()
        cart.add_item("Pen", 5.0)
        assert cart.get_total() == pytest.approx(5.0)

    def test_get_total_multiple_items_with_quantities(self, fixed_shopping_cart):
        """get_total() must sum price*qty across multiple items."""
        cart = fixed_shopping_cart.ShoppingCart()
        cart.add_item("A", 10.0, quantity=2)   # 20
        cart.add_item("B", 3.0, quantity=5)    # 15
        assert cart.get_total() == pytest.approx(35.0)

    def test_get_total_empty_cart(self, fixed_shopping_cart):
        """get_total() on empty cart must return 0."""
        cart = fixed_shopping_cart.ShoppingCart()
        assert cart.get_total() == pytest.approx(0.0)

    def test_get_total_single_item_qty_1_not_multiplied_bug(self, fixed_shopping_cart):
        """Regression: ensure quantity=1 gives same result as no-quantity (not doubled)."""
        cart = fixed_shopping_cart.ShoppingCart()
        cart.add_item("Item", 7.5, quantity=1)
        assert cart.get_total() == pytest.approx(7.5)


class TestApplyDiscount:
    def test_apply_discount_10_percent_on_200(self, fixed_shopping_cart):
        """apply_discount(10) on $200 total must give $180.0, not $190.0."""
        cart = fixed_shopping_cart.ShoppingCart()
        cart.add_item("Item", 200.0, quantity=1)
        result = cart.apply_discount(10)
        assert result == pytest.approx(180.0), f"Expected 180.0, got {result}"

    def test_apply_discount_50_percent(self, fixed_shopping_cart):
        """apply_discount(50) must halve the total."""
        cart = fixed_shopping_cart.ShoppingCart()
        cart.add_item("Item", 100.0, quantity=1)
        result = cart.apply_discount(50)
        assert result == pytest.approx(50.0)

    def test_apply_discount_0_percent(self, fixed_shopping_cart):
        """apply_discount(0) must return the full total."""
        cart = fixed_shopping_cart.ShoppingCart()
        cart.add_item("Item", 80.0)
        result = cart.apply_discount(0)
        assert result == pytest.approx(80.0)

    def test_apply_discount_20_percent_on_300(self, fixed_shopping_cart):
        """apply_discount(20) on $300 must give $240.0."""
        cart = fixed_shopping_cart.ShoppingCart()
        cart.add_item("Item", 300.0, quantity=1)
        result = cart.apply_discount(20)
        assert result == pytest.approx(240.0)


class TestRemoveItem:
    def test_remove_nonexistent_does_not_raise(self, fixed_shopping_cart):
        """remove_item() must not raise when item not in cart."""
        cart = fixed_shopping_cart.ShoppingCart()
        # Should not raise StopIteration or any other exception
        try:
            cart.remove_item("Laptop")
        except StopIteration:
            pytest.fail("remove_item() raised StopIteration — bug not fixed")

    def test_remove_existing_item(self, fixed_shopping_cart):
        """remove_item() must successfully remove an existing item."""
        cart = fixed_shopping_cart.ShoppingCart()
        cart.add_item("Book", 10.0)
        cart.remove_item("Book")
        assert cart.item_count() == 0

    def test_remove_nonexistent_leaves_cart_intact(self, fixed_shopping_cart):
        """remove_item('nonexistent') must leave the cart unchanged."""
        cart = fixed_shopping_cart.ShoppingCart()
        cart.add_item("Book", 10.0)
        cart.remove_item("Laptop")  # not in cart
        assert cart.item_count() == 1


class TestRegressionNoBreakage:
    def test_add_item_still_works(self, fixed_shopping_cart):
        cart = fixed_shopping_cart.ShoppingCart()
        cart.add_item("Item", 5.0)
        assert cart.item_count() == 1

    def test_clear_still_works(self, fixed_shopping_cart):
        cart = fixed_shopping_cart.ShoppingCart()
        cart.add_item("Item", 5.0)
        cart.clear()
        assert cart.item_count() == 0
