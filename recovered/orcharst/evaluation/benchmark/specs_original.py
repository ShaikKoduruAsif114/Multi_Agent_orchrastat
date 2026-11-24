"""
evaluation/benchmark/specs_original.py

The 5 seed benchmark tasks (tasks 001-005) sourced from
ShaikKoduruAsif114/agent-bug-testground (local clone present at
./test-buggy-app). Buggy sources are verbatim from that repo; fixed sources are
the ground-truth corrections; hidden tests are authored independently of the
agent and verified to fail on buggy and pass on fixed by the benchmark builder.
"""
from __future__ import annotations

_CALC_BUGGY = '''"""Calculator module - performs basic arithmetic operations."""
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    # BUG: No check for b == 0 -> raises ZeroDivisionError
    return a / b

def percentage(value, percent):
    # BUG: Wrong formula -> divides by 10 instead of 100
    return (value * percent) / 10

def power(base, exp):
    return base ** exp

def factorial(n):
    # BUG: Missing base case for n == 0
    if n == 1:
        return 1
    return n * factorial(n - 1)
'''

_CALC_FIXED = '''"""Calculator module - performs basic arithmetic operations."""
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

def percentage(value, percent):
    return (value * percent) / 100

def power(base, exp):
    return base ** exp

def factorial(n):
    if n < 0:
        raise ValueError("factorial not defined for negative numbers")
    if n in (0, 1):
        return 1
    return n * factorial(n - 1)
'''

_CALC_HIDDEN = '''import pytest
from src.calculator import add, subtract, multiply, divide, percentage, power, factorial

def test_divide_by_zero_raises_value_error():
    with pytest.raises((ValueError, ZeroDivisionError)):
        divide(10, 0)

def test_divide_by_zero_specifically_value_error():
    with pytest.raises(ValueError):
        divide(10, 0)

def test_divide_normal():
    assert divide(10, 2) == pytest.approx(5.0)
    assert divide(-9, 3) == pytest.approx(-3.0)
    assert divide(7, 2) == pytest.approx(3.5)
    assert divide(-6, -2) == pytest.approx(3.0)

def test_percentage_correct_formula():
    assert percentage(200, 10) == pytest.approx(20.0)
    assert percentage(500, 100) == pytest.approx(500.0)
    assert percentage(200, 50) == pytest.approx(100.0)

def test_percentage_not_divided_by_10():
    assert percentage(100, 10) != pytest.approx(100.0)
    assert percentage(100, 10) == pytest.approx(10.0)

def test_factorial_base_cases():
    assert factorial(0) == 1
    assert factorial(1) == 1

def test_factorial_small():
    assert factorial(5) == 120
    assert factorial(6) == 720

def test_factorial_negative_raises():
    with pytest.raises(ValueError):
        factorial(-3)

def test_power_and_basic_ops_regression():
    assert power(2, 10) == 1024
    assert add(2, 3) == 5
    assert subtract(10, 4) == 6
    assert multiply(6, 7) == 42
'''

_CALC_PUBLIC = '''import pytest
from src.calculator import add, subtract, multiply, divide

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(9, 4) == 5

def test_multiply():
    assert multiply(3, 4) == 12

def test_divide_works():
    assert divide(8, 2) == 4.0
'''

_CALC_ISSUE = {
    "issue_title": "Bug: Calculator.divide() raises ZeroDivisionError instead of ValueError; percentage() and factorial() are wrong",
    "issue_body": (
        "## Bug Report\n\n**File:** `src/calculator.py`\n\n### Description\n"
        "`divide()` raises a raw `ZeroDivisionError` when dividing by zero; the public API contract "
        "requires a `ValueError` with the message 'Cannot divide by zero'.\n"
        "`percentage(value, percent)` multiplies by `percent / 10` instead of `/ 100`.\n"
        "`factorial(0)` recurses forever (missing base case for 0).\n\n"
        "### Expected Behavior\n"
        "- `divide(10, 0)` raises `ValueError('Cannot divide by zero')`\n"
        "- `percentage(200, 10)` returns `20.0`\n"
        "- `factorial(0)` returns `1`"
    ),
}

_UM_BUGGY = '''"""User management module."""
users_db = []

def create_user(user_id: int, name: str, email: str) -> dict:
    user = {"id": user_id, "name": name, "email": email, "active": True}
    users_db.append(user)
    return user

def get_user(user_id: int):
    for user in users_db:
        if user["id"] == user_id:
            # BUG: returns wrong key name
            return {"id": user["id"], "username": user["name"], "email": user["email"]}
    return None

def update_email(user_id: int, new_email: str) -> bool:
    # BUG: No validation - accepts emails without '@'
    for user in users_db:
        if user["id"] == user_id:
            user["email"] = new_email
            return True
    return False

def delete_user(user_id: int) -> bool:
    for user in users_db:
        if user["id"] == user_id:
            users_db.remove(user)
            return True
    return False

def list_active_users() -> list:
    return [u for u in users_db if u["active"]]

def deactivate_user(user_id: int) -> bool:
    for user in users_db:
        if user["id"] == user_id:
            user["active"] = False
            return True
    return False
'''

_UM_FIXED = '''"""User management module."""
users_db = []

def create_user(user_id: int, name: str, email: str) -> dict:
    user = {"id": user_id, "name": name, "email": email, "active": True}
    users_db.append(user)
    return user

def get_user(user_id: int):
    for user in users_db:
        if user["id"] == user_id:
            return {"id": user["id"], "name": user["name"], "email": user["email"]}
    return None

def update_email(user_id: int, new_email: str) -> bool:
    if not isinstance(new_email, str) or "@" not in new_email:
        raise ValueError("Email must contain an '@' symbol")
    for user in users_db:
        if user["id"] == user_id:
            user["email"] = new_email
            return True
    return False

def delete_user(user_id: int) -> bool:
    for user in users_db:
        if user["id"] == user_id:
            users_db.remove(user)
            return True
    return False

def list_active_users() -> list:
    return [u for u in users_db if u["active"]]

def deactivate_user(user_id: int) -> bool:
    for user in users_db:
        if user["id"] == user_id:
            user["active"] = False
            return True
    return False
'''

_UM_HIDDEN = '''import pytest
from src.user_manager import users_db, create_user, get_user, update_email, delete_user

@pytest.fixture(autouse=True)
def clean_db():
    users_db.clear()
    yield
    users_db.clear()

def test_get_user_returns_name_key():
    create_user(10, "Alice", "alice@example.com")
    user = get_user(10)
    assert user is not None
    assert "name" in user
    assert "username" not in user
    assert user["name"] == "Alice"
    assert user["id"] == 10
    assert user["email"] == "alice@example.com"

def test_get_user_nonexistent_returns_none():
    assert get_user(9999) is None

def test_update_email_invalid_raises():
    create_user(20, "Frank", "frank@example.com")
    with pytest.raises((ValueError, Exception)):
        update_email(20, "notanemail")
    with pytest.raises((ValueError, Exception)):
        update_email(20, "")

def test_update_email_valid_accepted():
    create_user(21, "Grace", "grace@example.com")
    assert update_email(21, "new@domain.com") is True

def test_regression_create_delete():
    create_user(30, "Jack", "jack@test.com")
    assert get_user(30) is not None
    assert delete_user(30) is True
    assert get_user(30) is None
'''

_UM_PUBLIC = '''from src.user_manager import users_db, create_user, list_active_users, deactivate_user

def test_list_active_users():
    users_db.clear()
    create_user(1, "A", "a@x.com")
    create_user(2, "B", "b@x.com")
    assert len(list_active_users()) == 2
    deactivate_user(1)
    assert len(list_active_users()) == 1
    users_db.clear()

def test_deactivate_unknown_returns_false():
    users_db.clear()
    assert deactivate_user(42) is False
    users_db.clear()
'''

_UM_ISSUE = {
    "issue_title": "Bug: get_user() returns wrong key name causing KeyError in API consumers",
    "issue_body": (
        "## Bug Report\n\n**File:** `src/user_manager.py`\n\n### Description\n"
        "The `get_user()` function returns a dictionary with the key `username` but the user object "
        "is stored with the key `name`. This inconsistency breaks callers that access "
        "`result['name']`.\n\n"
        "Additionally, `update_email()` accepts any string as an email without validating that it "
        "contains an `@` symbol.\n\n"
        "### Expected Behavior\n"
        "- `get_user()` should return a dict with the key `name` (not `username`)\n"
        "- `update_email()` should raise `ValueError` if the email does not contain `@`"
    ),
}
_SC_BUGGY = '''class ShoppingCart:
    def __init__(self):
        self.items = []

    def add_item(self, name: str, price: float, quantity: int = 1):
        self.items.append({"name": name, "price": price, "quantity": quantity})

    def remove_item(self, name: str):
        # BUG: crashes with StopIteration if item is not present
        item = next(i for i in self.items if i["name"] == name)
        self.items.remove(item)

    def get_total(self) -> float:
        # BUG: ignores quantity
        return sum(item["price"] for item in self.items)

    def apply_discount(self, discount_percent: float) -> float:
        total = self.get_total()
        # BUG: subtracts the raw percent number instead of applying a percentage
        return total - discount_percent

    def item_count(self) -> int:
        return len(self.items)

    def clear(self):
        self.items = []
'''

_SC_FIXED = '''class ShoppingCart:
    def __init__(self):
        self.items = []

    def add_item(self, name: str, price: float, quantity: int = 1):
        self.items.append({"name": name, "price": price, "quantity": quantity})

    def remove_item(self, name: str):
        for item in self.items:
            if item["name"] == name:
                self.items.remove(item)
                return True
        return False

    def get_total(self) -> float:
        return sum(item["price"] * item["quantity"] for item in self.items)

    def apply_discount(self, discount_percent: float) -> float:
        total = self.get_total()
        return total * (1 - discount_percent / 100)

    def item_count(self) -> int:
        return len(self.items)

    def clear(self):
        self.items = []
'''

_SC_HIDDEN = '''import pytest
from src.shopping_cart import ShoppingCart

def test_get_total_with_quantity():
    cart = ShoppingCart()
    cart.add_item("Book", 10.0, quantity=3)
    assert cart.get_total() == pytest.approx(30.0)

def test_get_total_default_quantity_one():
    cart = ShoppingCart()
    cart.add_item("Pen", 5.0)
    assert cart.get_total() == pytest.approx(5.0)

def test_get_total_multiple_items():
    cart = ShoppingCart()
    cart.add_item("A", 10.0, quantity=2)
    cart.add_item("B", 3.0, quantity=5)
    assert cart.get_total() == pytest.approx(35.0)

def test_get_total_empty_cart():
    assert ShoppingCart().get_total() == pytest.approx(0.0)

def test_apply_discount_10_percent_on_200():
    cart = ShoppingCart()
    cart.add_item("Item", 200.0, quantity=1)
    assert cart.apply_discount(10) == pytest.approx(180.0)

def test_apply_discount_other_percents():
    cart = ShoppingCart()
    cart.add_item("Item", 100.0, quantity=1)
    assert cart.apply_discount(50) == pytest.approx(50.0)
    cart2 = ShoppingCart()
    cart2.add_item("Item", 80.0)
    assert cart2.apply_discount(0) == pytest.approx(80.0)

def test_remove_nonexistent_does_not_raise():
    cart = ShoppingCart()
    try:
        cart.remove_item("Laptop")
    except StopIteration:
        pytest.fail("remove_item() raised StopIteration - bug not fixed")

def test_remove_existing_and_missing():
    cart = ShoppingCart()
    cart.add_item("Book", 10.0)
    assert cart.remove_item("Book") is not False
    assert cart.item_count() == 0

def test_regression():
    cart = ShoppingCart()
    cart.add_item("Item", 5.0)
    assert cart.item_count() == 1
    cart.clear()
    assert cart.item_count() == 0
'''

_SC_PUBLIC = '''from src.shopping_cart import ShoppingCart

def test_add_and_count():
    cart = ShoppingCart()
    cart.add_item("Item", 1.0)
    assert cart.item_count() == 1

def test_clear():
    cart = ShoppingCart()
    cart.add_item("Item", 1.0)
    cart.clear()
    assert cart.item_count() == 0
'''

_SC_ISSUE = {
    "issue_title": "Bug: ShoppingCart.get_total() ignores item quantity",
    "issue_body": (
        "## Bug Report\n\n**File:** `src/shopping_cart.py`\n\n### Description\n"
        "The `get_total()` method sums only `item['price']` but ignores `item['quantity']`. "
        "Adding 3 units of a $10 item returns $10 instead of $30.\n\n"
        "`apply_discount()` subtracts the raw percentage number from the total instead of applying "
        "it as a percentage (10% of $200 should be $180, the code gives $190).\n\n"
        "`remove_item()` crashes with `StopIteration` when the item name does not exist.\n\n"
        "### Expected Behavior\n"
        "- `get_total()` must compute `price * quantity`\n"
        "- `apply_discount(percent)` must compute `total * (1 - percent/100)`\n"
        "- `remove_item()` must not raise when the item is absent"
    ),
}
_SU_BUGGY = '''def reverse_string(s: str) -> str:
    return s[::-1]

def is_palindrome(s: str) -> bool:
    # BUG: does not normalize case - 'Racecar' returns False
    return s == s[::-1]

def count_words(text: str) -> int:
    # BUG: split(' ') creates empty tokens for multiple spaces
    return len(text.split(' '))

def capitalize_words(text: str) -> str:
    return ' '.join(word.capitalize() for word in text.split())

def truncate(text: str, max_length: int) -> str:
    # BUG: always appends '...' even when the string fits
    return text[:max_length] + '...'

def count_vowels(text: str) -> int:
    vowels = 'aeiou'
    return sum(1 for char in text.lower() if char in vowels)
'''

_SU_FIXED = '''def reverse_string(s: str) -> str:
    return s[::-1]

def is_palindrome(s: str) -> bool:
    normalized = str(s).lower()
    return normalized == normalized[::-1]

def count_words(text: str) -> int:
    return len(text.split())

def capitalize_words(text: str) -> str:
    return ' '.join(word.capitalize() for word in text.split())

def truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length] + '...'

def count_vowels(text: str) -> int:
    vowels = 'aeiou'
    return sum(1 for char in text.lower() if char in vowels)
'''

_SU_HIDDEN = '''import pytest
from src.string_utils import (reverse_string, is_palindrome, count_words,
                              capitalize_words, truncate, count_vowels)

def test_palindrome_mixed_case():
    assert is_palindrome("Racecar") is True
    assert is_palindrome("RACECAR") is True
    assert is_palindrome("Level") is True
    assert is_palindrome("A") is True

def test_palindrome_negative():
    assert is_palindrome("hello") is False

def test_count_words_multiple_spaces():
    assert count_words("hello  world") == 2
    assert count_words("a   b") == 2
    assert count_words("  hello  ") == 1

def test_count_words_normal():
    assert count_words("one two three") == 3
    assert count_words("hello") == 1

def test_truncate_short_no_ellipsis():
    assert truncate("Hi there", 100) == "Hi there"
    assert truncate("Hello", 5) == "Hello"
    assert truncate("Hi", 100) == "Hi"

def test_truncate_long_adds_ellipsis():
    result = truncate("Hello World", 5)
    assert "..." in result
    assert result.startswith("Hello")

def test_regression():
    assert reverse_string("hello") == "olleh"
    assert capitalize_words("hello world") == "Hello World"
    assert count_vowels("hello") == 2
'''

_SU_PUBLIC = '''from src.string_utils import reverse_string, capitalize_words, count_vowels

def test_reverse_works():
    assert reverse_string("abc") == "cba"

def test_capitalize_works():
    assert capitalize_words("hello world") == "Hello World"

def test_vowels_works():
    assert count_vowels("hello") == 2
'''

_SU_ISSUE = {
    "issue_title": "Bug: is_palindrome() fails on mixed-case strings and truncate() always adds ellipsis",
    "issue_body": (
        "## Bug Report\n\n**File:** `src/string_utils.py`\n\n### Description\n"
        "`is_palindrome()` does not normalize case before checking, so 'Racecar' returns False.\n"
        "`count_words()` uses `text.split(' ')` which counts multiple consecutive spaces as extra "
        "empty words ('hello  world' counts as 3 instead of 2).\n"
        "`truncate()` always appends '...' even when the string fits within `max_length`.\n\n"
        "### Expected Behavior\n"
        "- `is_palindrome('Racecar')` should be True\n"
        "- `count_words('hello  world')` should be 2\n"
        "- `truncate('Hi there', 100)` should be 'Hi there' (no ellipsis)"
    ),
}
_BA_BUGGY = '''class BankAccount:
    def __init__(self, owner: str, initial_balance: float = 0.0):
        self.owner = owner
        self.balance = initial_balance
        self.transactions = []

    def deposit(self, amount: float) -> float:
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        self.balance += amount
        self.transactions.append(("deposit", amount))
        return self.balance

    def withdraw(self, amount: float) -> float:
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        # BUG: no check for sufficient funds - balance can go negative
        self.balance -= amount
        self.transactions.append(("withdraw", amount))
        return self.balance

    def get_balance(self) -> float:
        return self.balance

    def transfer(self, target_account: "BankAccount", amount: float) -> bool:
        # BUG: does not check sender has sufficient funds
        self.balance -= amount
        target_account.balance += amount
        return True

    def apply_interest(self, rate: float, years: int) -> float:
        # BUG: applies simple interest instead of compound interest
        original = self.balance
        self.balance = original + (original * rate * years)
        return self.balance

    def transaction_count(self) -> int:
        return len(self.transactions)
'''

_BA_FIXED = '''class BankAccount:
    def __init__(self, owner: str, initial_balance: float = 0.0):
        self.owner = owner
        self.balance = initial_balance
        self.transactions = []

    def deposit(self, amount: float) -> float:
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        self.balance += amount
        self.transactions.append(("deposit", amount))
        return self.balance

    def withdraw(self, amount: float) -> float:
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        if amount > self.balance:
            raise ValueError("Insufficient funds")
        self.balance -= amount
        self.transactions.append(("withdraw", amount))
        return self.balance

    def get_balance(self) -> float:
        return self.balance

    def transfer(self, target_account: "BankAccount", amount: float) -> bool:
        if amount <= 0:
            raise ValueError("Transfer amount must be positive")
        if amount > self.balance:
            raise ValueError("Insufficient funds")
        self.balance -= amount
        target_account.balance += amount
        return True

    def apply_interest(self, rate: float, years: int) -> float:
        self.balance = self.balance * (1 + rate) ** years
        return self.balance

    def transaction_count(self) -> int:
        return len(self.transactions)
'''
_BA_HIDDEN = '''import pytest
from src.bank_account import BankAccount

def test_withdraw_insufficient_raises():
    acc = BankAccount("Alice", 50.0)
    with pytest.raises(ValueError):
        acc.withdraw(500)

def test_withdraw_exact_balance_allowed():
    acc = BankAccount("Alice", 50.0)
    acc.withdraw(50.0)
    assert acc.get_balance() == pytest.approx(0.0)

def test_withdraw_normal():
    acc = BankAccount("Bob", 100.0)
    acc.withdraw(30.0)
    assert acc.get_balance() == pytest.approx(70.0)

def test_withdraw_failed_keeps_balance_positive():
    acc = BankAccount("Carol", 50.0)
    try:
        acc.withdraw(200.0)
    except ValueError:
        pass
    assert acc.get_balance() >= 0

def test_transfer_insufficient_sender_raises():
    sender = BankAccount("Bob", 0.0)
    receiver = BankAccount("Carol", 100.0)
    with pytest.raises(ValueError):
        sender.transfer(receiver, 1000.0)
    assert receiver.get_balance() == pytest.approx(100.0)

def test_transfer_valid():
    sender = BankAccount("Eve", 100.0)
    receiver = BankAccount("Frank", 50.0)
    sender.transfer(receiver, 50.0)
    assert sender.get_balance() == pytest.approx(50.0)
    assert receiver.get_balance() == pytest.approx(100.0)

def test_apply_interest_compound():
    acc = BankAccount("Dave", 1000.0)
    result = acc.apply_interest(0.1, 3)
    assert result == pytest.approx(1331.0, rel=1e-3)
    assert result != pytest.approx(1300.0, rel=1e-3)

def test_apply_interest_updates_balance():
    acc = BankAccount("Heidi", 1000.0)
    acc.apply_interest(0.1, 3)
    assert acc.get_balance() == pytest.approx(1331.0, rel=1e-3)

def test_regression():
    acc = BankAccount("Ivan", 100.0)
    acc.deposit(50.0)
    assert acc.get_balance() == pytest.approx(150.0)
    acc.deposit(10.0)
    acc.withdraw(5.0)
    assert acc.transaction_count() == 3
'''

_BA_PUBLIC = '''import pytest
from src.bank_account import BankAccount

def test_deposit_works():
    acc = BankAccount("Ian", 0.0)
    acc.deposit(25.0)
    assert acc.get_balance() == pytest.approx(25.0)

def test_deposit_nonpositive_raises():
    acc = BankAccount("Ian", 0.0)
    with pytest.raises(ValueError):
        acc.deposit(0)

def test_initial_balance():
    acc = BankAccount("Olivia", 10.0)
    assert acc.get_balance() == pytest.approx(10.0)
'''

_BA_ISSUE = {
    "issue_title": "Bug: BankAccount.withdraw() allows negative balance (no overdraft protection)",
    "issue_body": (
        "## Bug Report\n\n**File:** `src/bank_account.py`\n\n### Description\n"
        "`withdraw()` has no check preventing the balance from going negative; a user with $50 can "
        "withdraw $500 and end at -$450.\n"
        "`transfer()` does not check the sender's balance before deducting.\n"
        "`apply_interest()` uses the simple-interest formula (P + P*R*T) instead of compound "
        "interest (P * (1+R)**T).\n\n"
        "### Expected Behavior\n"
        "- `withdraw()` raises `ValueError('Insufficient funds')` when amount > balance\n"
        "- `transfer()` validates the sender's balance first\n"
        "- `apply_interest(0.1, 3)` on 1000 returns 1331.0 (compound)"
    ),
}
ORIGINAL_TASKS = [
    {
        "task_id": "task_001",
        "repository": "https://github.com/ShaikKoduruAsif114/agent-bug-testground",
        "gold_file": "src/calculator.py",
        "category": "exception_handling",
        "difficulty": "easy",
        "buggy": _CALC_BUGGY,
        "fixed": _CALC_FIXED,
        "hidden_tests": _CALC_HIDDEN,
        "public_tests": _CALC_PUBLIC,
        "issue_title": _CALC_ISSUE["issue_title"],
        "issue_body": _CALC_ISSUE["issue_body"],
        "buggy_behaviors": [
            "divide(10, 0) raises ZeroDivisionError instead of ValueError",
            "percentage(200, 10) returns 200.0 instead of 20.0",
            "factorial(0) hits RecursionError (missing base case)",
        ],
        "expected_behaviors": [
            "divide(10, 0) raises ValueError",
            "percentage(200, 10) returns 20.0",
            "factorial(0) returns 1",
            "factorial(5) returns 120",
        ],
    },
    {
        "task_id": "task_002",
        "repository": "https://github.com/ShaikKoduruAsif114/agent-bug-testground",
        "gold_file": "src/user_manager.py",
        "category": "input_validation",
        "difficulty": "easy",
        "buggy": _UM_BUGGY,
        "fixed": _UM_FIXED,
        "hidden_tests": _UM_HIDDEN,
        "public_tests": _UM_PUBLIC,
        "issue_title": _UM_ISSUE["issue_title"],
        "issue_body": _UM_ISSUE["issue_body"],
        "buggy_behaviors": [
            "get_user() returns key 'username' instead of 'name'",
            "update_email() accepts emails without '@'",
        ],
        "expected_behaviors": [
            "get_user(1)['name'] == 'Alice' (no KeyError)",
            "update_email(1, 'notanemail') raises ValueError",
            "update_email(1, 'valid@example.com') returns True",
        ],
    },
    {
        "task_id": "task_003",
        "repository": "https://github.com/ShaikKoduruAsif114/agent-bug-testground",
        "gold_file": "src/shopping_cart.py",
        "category": "arithmetic_logic",
        "difficulty": "medium",
        "buggy": _SC_BUGGY,
        "fixed": _SC_FIXED,
        "hidden_tests": _SC_HIDDEN,
        "public_tests": _SC_PUBLIC,
        "issue_title": _SC_ISSUE["issue_title"],
        "issue_body": _SC_ISSUE["issue_body"],
        "buggy_behaviors": [
            "get_total() ignores quantity",
            "apply_discount(10) subtracts 10 instead of 10%",
            "remove_item('missing') raises StopIteration",
        ],
        "expected_behaviors": [
            "get_total() == sum(price*qty)",
            "apply_discount(10) on $200 == 180.0",
            "remove_item('missing') returns gracefully",
        ],
    },
    {
        "task_id": "task_004",
        "repository": "https://github.com/ShaikKoduruAsif114/agent-bug-testground",
        "gold_file": "src/string_utils.py",
        "category": "parsing",
        "difficulty": "easy",
        "buggy": _SU_BUGGY,
        "fixed": _SU_FIXED,
        "hidden_tests": _SU_HIDDEN,
        "public_tests": _SU_PUBLIC,
        "issue_title": _SU_ISSUE["issue_title"],
        "issue_body": _SU_ISSUE["issue_body"],
        "buggy_behaviors": [
            "is_palindrome('Racecar') returns False",
            "count_words('hello  world') returns 3 instead of 2",
            "truncate('Hi', 100) returns 'Hi...'",
        ],
        "expected_behaviors": [
            "is_palindrome('Racecar') == True",
            "count_words('hello  world') == 2",
            "truncate('Hi', 100) == 'Hi'",
            "truncate('Hello World', 5) starts with 'Hello' and has '...'",
        ],
    },
    {
        "task_id": "task_005",
        "repository": "https://github.com/ShaikKoduruAsif114/agent-bug-testground",
        "gold_file": "src/bank_account.py",
        "category": "arithmetic_logic",
        "difficulty": "medium",
        "buggy": _BA_BUGGY,
        "fixed": _BA_FIXED,
        "hidden_tests": _BA_HIDDEN,
        "public_tests": _BA_PUBLIC,
        "issue_title": _BA_ISSUE["issue_title"],
        "issue_body": _BA_ISSUE["issue_body"],
        "buggy_behaviors": [
            "withdraw(500) from balance 50 leaves -450",
            "transfer of 1000 allowed from zero balance",
            "apply_interest uses simple (not compound) interest",
        ],
        "expected_behaviors": [
            "withdraw > balance raises ValueError",
            "transfer > balance raises ValueError",
            "apply_interest(0.1, 3) == 1331.0",
        ],
    },
]