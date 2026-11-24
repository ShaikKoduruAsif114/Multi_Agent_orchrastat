"""
evaluation/benchmark/specs_new_1.py
Tasks 006-014: inventory_manager, date_utils, csv_parser, matrix_ops,
email_validator, temperature_converter, config_loader, text_stats, queue_manager
"""
from __future__ import annotations

REPO = "https://github.com/benchmark-fixtures"


def _t(task_id, repo_name, gold_file, category, difficulty, issue_title,
       issue_body, buggy, fixed, hidden, public, buggy_behaviors,
       expected_behaviors):
    return {
        "task_id": task_id,
        "repository": f"{REPO}/{repo_name}",
        "gold_file": gold_file,
        "category": category,
        "difficulty": difficulty,
        "issue_title": issue_title,
        "issue_body": issue_body,
        "buggy": buggy,
        "fixed": fixed,
        "hidden_tests": hidden,
        "public_tests": public,
        "buggy_behaviors": buggy_behaviors,
        "expected_behaviors": expected_behaviors,
    }


NEW_TASKS_1 = [
    _t(
        "task_006", "task_006_inventory_manager", "src/inventory_manager.py",
        "exception_handling", "medium",
        "Bug: Inventory.restock() crashes with KeyError when adding a new item to stock",
        "## Bug Report\n**File:** `src/inventory_manager.py`\n\nThe `restock(name, qty)` method raises "
        "`KeyError` when the item is not already in stock (it should add new items automatically). "
        "Additionally `get_low_stock(threshold)` returns items whose stock is strictly greater than "
        "the threshold instead of at-or-below, so critically low stock is never reported.\n"
        "### Expected\n- `restock('NewItem', 5)` adds the item instead of crashing\n"
        "- `get_low_stock(10)` includes items with stock == 10",
        '''class Inventory:
    def __init__(self):
        self.stock = {}

    def restock(self, name: str, qty: int) -> None:
        # BUG: KeyError when item not already present
        self.stock[name] = self.stock[name] + qty

    def sell(self, name: str, qty: int) -> None:
        if name not in self.stock or self.stock[name] < qty:
            raise ValueError("insufficient stock")
        self.stock[name] -= qty

    def get_stock(self, name: str) -> int:
        return self.stock.get(name, 0)

    def get_low_stock(self, threshold: int):
        # BUG: uses > threshold, so items exactly AT threshold are missed
        return {k: v for k, v in self.stock.items() if v > threshold and v <= threshold * 2}
''',
        '''class Inventory:
    def __init__(self):
        self.stock = {}

    def restock(self, name: str, qty: int) -> None:
        self.stock[name] = self.stock.get(name, 0) + qty

    def sell(self, name: str, qty: int) -> None:
        if name not in self.stock or self.stock[name] < qty:
            raise ValueError("insufficient stock")
        self.stock[name] -= qty

    def get_stock(self, name: str) -> int:
        return self.stock.get(name, 0)

    def get_low_stock(self, threshold: int):
        return {k: v for k, v in self.stock.items() if v <= threshold and v > 0}
''',
        '''import pytest
from src.inventory_manager import Inventory

def test_restock_new_item_does_not_crash():
    inv = Inventory()
    inv.restock("Widget", 5)
    assert inv.get_stock("Widget") == 5

def test_restock_existing_item_accumulates():
    inv = Inventory()
    inv.restock("Widget", 5)
    inv.restock("Widget", 3)
    assert inv.get_stock("Widget") == 8

def test_sell_and_values():
    inv = Inventory()
    inv.restock("A", 10)
    inv.sell("A", 4)
    assert inv.get_stock("A") == 6

def test_sell_too_much_raises():
    inv = Inventory()
    inv.restock("A", 2)
    with pytest.raises(ValueError):
        inv.sell("A", 5)

def test_low_stock_includes_threshold():
    inv = Inventory()
    inv.restock("A", 10)
    inv.restock("B", 11)
    inv.restock("C", 30)
    low = inv.get_low_stock(10)
    assert low.get("A") == 10
    assert "B" not in low
    assert "C" not in low
''',
        '''from src.inventory_manager import Inventory

def test_initial_empty():
    assert Inventory().stock == {}

def test_get_stock_missing_is_zero():
    assert Inventory().get_stock("nope") == 0
''',
        ["restock('New', 1) raises KeyError", "get_low_stock(10) misses items exactly at 10"],
        ["restock('New', 1) adds item with stock 1", "get_low_stock(10) includes stock == 10"],
    ),
    _t(
        "task_007", "task_007_date_utils", "src/date_utils.py",
        "arithmetic_logic", "medium",
        "Bug: days_between() returns negative values when the first date is later, and is_weekend() misclassifies Fridays",
        "## Bug Report\n**File:** `src/date_utils.py`\n\n`days_between(a, b)` returns a negative number "
        "when `a` is later than `b`; callers expect the number of days between two dates to be the "
        "absolute difference. `is_weekend()` incorrectly uses `weekday() > 5` so Friday (weekday 4) is "
        "misclassified and Sunday (weekday 6) is missed.\n### Expected\n- `days_between` is always non-negative\n"
        "- `is_weekend` True for Sat/Sun only",
        '''from datetime import date

def days_between(d1: date, d2: date) -> int:
    # BUG: negative when d1 > d2
    return (d2 - d1).days

def is_weekend(d: date) -> bool:
    # BUG: Friday (4) reported True, Sunday (6) reported False
    return d.weekday() > 5

def add_days(d: date, days: int) -> date:
    delta = days % 7
    if delta:
        return date.fromordinal(d.toordinal() + delta)
    return d

def days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days
''',
        '''from datetime import date

def days_between(d1: date, d2: date) -> int:
    return abs((d2 - d1).days)

def is_weekend(d: date) -> bool:
    return d.weekday() >= 5

def add_days(d: date, days: int) -> date:
    delta = days % 7
    if delta:
        return date.fromordinal(d.toordinal() + delta)
    return d

def days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days
''',
        '''from datetime import date
from src.date_utils import days_between, is_weekend, add_days, days_in_month

def test_days_between_reversed_order_absolute():
    a = date(2024, 1, 10)
    b = date(2024, 1, 1)
    assert days_between(a, b) == 9
    assert days_between(b, a) == 9

def test_days_between_same_day():
    d = date(2024, 3, 15)
    assert days_between(d, d) == 0

def test_is_weekend_friday_is_not_weekend():
    friday = date(2024, 3, 15)  # a Friday
    assert is_weekend(friday) is False

def test_is_weekend_saturday_sunday():
    sat = date(2024, 3, 16)
    sun = date(2024, 3, 17)
    assert is_weekend(sat) is True
    assert is_weekend(sun) is True

def test_is_weekend_monday_false():
    mon = date(2024, 3, 18)
    assert is_weekend(mon) is False

def test_add_days_and_days_in_month():
    d = date(2024, 1, 28)
    assert add_days(d, 2) == date(2024, 1, 30)
    assert days_in_month(2024, 2) == 29
''',
        '''from datetime import date
from src.date_utils import days_in_month

def test_days_in_month_january():
    assert days_in_month(2024, 1) == 31
''',
        ["days_between(reversed) returns negative", "is_weekend(Friday) returns True", "is_weekend(Sunday) returns False"],
        ["days_between is absolute", "is_weekend True only Sat/Sun"],
    ),
    _t(
        "task_008", "task_008_csv_parser", "src/csv_parser.py",
        "parsing", "medium",
        "Bug: parse_csv() splits fields naively on commas inside quoted values and parse_int_list() crashes on whitespace",
        "## Bug Report\n**File:** `src/csv_parser.py`\n\n`parse_csv()` uses `line.split(',')` so a "
        "quoted field containing a comma (`\"Smith, John\"`) is wrongly split into two columns. "
        "`parse_int_list()` does not strip surrounding whitespace, so `'1, 2, 3'` crashes with "
        "`ValueError: invalid literal`.\n### Expected\n- quoted fields with commas stay intact\n"
        "- `parse_int_list('1, 2, 3') == [1, 2, 3]`",
        '''def parse_csv(text: str) -> list:
    rows = []
    for line in text.strip().splitlines():
        if not line.strip():
            continue
        # BUG: naive split breaks quoted fields containing commas
        rows.append(line.split(","))
    return rows

def parse_int_list(text: str) -> list:
    # BUG: no whitespace stripping -> ValueError on '1, 2'
    return [int(x) for x in text.split(",")]

def to_csv_row(row) -> str:
    return ",".join(str(c) for c in row)
''',
        '''def parse_csv(text: str) -> list:
    rows = []
    for line in text.strip().splitlines():
        if not line.strip():
            continue
        fields = []
        current = ""
        in_quotes = False
        for ch in line:
            if ch == '"':
                in_quotes = not in_quotes
            elif ch == "," and not in_quotes:
                fields.append(current.strip())
                current = ""
            else:
                current += ch
        fields.append(current.strip())
        rows.append(fields)
    return rows

def parse_int_list(text: str) -> list:
    return [int(x.strip()) for x in text.split(",") if x.strip()]

def to_csv_row(row) -> str:
    def esc(c):
        c = str(c)
        if "," in c or '"' in c:
            return '"' + c.replace('"', '""') + '"'
        return c
    return ",".join(esc(c) for c in row)
''',
        '''from src.csv_parser import parse_csv, parse_int_list, to_csv_row

def test_parse_csv_quoted_field_with_comma():
    data = 'name,notes\\n"Smith, John","hello, world"'
    rows = parse_csv(data)
    assert rows[1][0] == "Smith, John"
    assert rows[1][1] == "hello, world"
    assert len(rows[1]) == 2

def test_parse_csv_basic():
    rows = parse_csv("a,b\\n1,2")
    assert rows[0] == ["a", "b"]
    assert rows[1] == ["1", "2"]

def test_parse_csv_skips_blank_lines():
    rows = parse_csv("a,b\\n\\n1,2\\n")
    assert len(rows) == 2

def test_parse_int_list_with_whitespace():
    assert parse_int_list("1, 2, 3") == [1, 2, 3]
    assert parse_int_list("5") == [5]

def test_to_csv_row_quotes_comma_field():
    assert to_csv_row(["a", "b,c"]) == 'a,"b,c"'
''',
        '''from src.csv_parser import parse_int_list

def test_parse_int_list_simple():
    assert parse_int_list("1,2,3") == [1, 2, 3]
''',
        ["quoted commas split into columns", "parse_int_list fails on whitespace"],
        ["quoted fields intact", "parse_int_list with whitespace OK"],
    ),
    _t(
        "task_009", "task_009_matrix_ops", "src/matrix_ops.py",
        "arithmetic_logic", "medium",
        "Bug: matrix_multiply() silently computes garbage on shape mismatch and transpose() crashes on empty matrices",
        "## Bug Report\n**File:** `src/matrix_ops.py`\n\n`matrix_multiply(A, B)` does not validate that "
        "`len(A[0]) == len(B)`. With mismatched shapes it either raises an opaque IndexError or silently "
        "produces a wrong matrix. `transpose` should return an empty list for an empty matrix but instead "
        "crashes with IndexError.\n### Expected\n- shape mismatch raises ValueError with a clear message\n"
        "- `transpose([]) == []`",
        '''def matrix_multiply(A, B):
    if not A or not B:
        return []
    # BUG: no shape validation
    result = [[0.0] * len(B[0]) for _ in range(len(A))]
    for i in range(len(A)):
        for j in range(len(B[0])):
            for k in range(len(B)):
                result[i][j] += A[i][k] * B[k][j]
    return result

def transpose(M):
    if not M:
        return M
    return [[row[i] for row in M] for i in range(len(M[0]))]
''',
        '''def matrix_multiply(A, B):
    if not A or not B:
        return []
    if len(A[0]) != len(B):
        raise ValueError("matrix shape mismatch: inner dimensions must agree")
    result = [[0.0] * len(B[0]) for _ in range(len(A))]
    for i in range(len(A)):
        for j in range(len(B[0])):
            for k in range(len(B)):
                result[i][j] += A[i][k] * B[k][j]
    return result

def transpose(M):
    if not M:
        return []
    return [[row[i] for row in M] for i in range(len(M[0]))]
''',
        '''import pytest
from src.matrix_ops import matrix_multiply, transpose

def test_matrix_multiply_correct():
    A = [[1, 2], [3, 4]]
    B = [[5, 6], [7, 8]]
    assert matrix_multiply(A, B) == [[19, 22], [43, 50]]

def test_matrix_multiply_shape_mismatch_raises():
    A = [[1, 2, 3]]
    B = [[1, 2]]
    with pytest.raises(ValueError):
        matrix_multiply(A, B)

def test_matrix_multiply_empty_inputs():
    assert matrix_multiply([], [[1]]) == []

def test_transpose_basic():
    M = [[1, 2, 3], [4, 5, 6]]
    assert transpose(M) == [[1, 4], [2, 5], [3, 6]]

def test_transpose_empty():
    assert transpose([]) == []
''',
        '''from src.matrix_ops import transpose

def test_transpose_square():
    assert transpose([[1, 2], [3, 4]]) == [[1, 3], [2, 4]]
''',
        ["no shape validation on multiply", "transpose([]) crashes"],
        ["ValueError on mismatch", "transpose([]) == []"],
    ),
    _t(
        "task_010", "task_010_email_validator", "src/email_validator.py",
        "input_validation", "easy",
        "Bug: is_valid_email() accepts emails without a TLD and normalizes addresses incorrectly",
        "## Bug Report\n**File:** `src/email_validator.py`\n\n`is_valid_email()` only checks that the "
        "string contains '@', so `user@localhost` and `user@` are accepted as valid. "
        "`normalize()` lowercases the local part too, losing case-sensitive information; only the domain "
        "part should be lowercased.\n### Expected\n- a valid email has a non-empty local part, an '@', "
        "and a domain with a dot and a 2+ char TLD\n- `normalize()` preserves local-part case",
        '''import re

def is_valid_email(email: str) -> bool:
    # BUG: '@' check only; no TLD requirement
    return isinstance(email, str) and "@" in email

def normalize(email: str) -> str:
    # BUG: lowercases the local part as well
    return email.strip().lower()

def extract_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1]
''',
        '''import re

_EMAIL_RE = re.compile(r"^[^@\\s]+@[^@\\s]+\\.[A-Za-z]{2,}$")

def is_valid_email(email: str) -> bool:
    return isinstance(email, str) and bool(_EMAIL_RE.match(email))

def normalize(email: str) -> str:
    email = email.strip()
    if "@" not in email:
        return email
    local, _, domain = email.rpartition("@")
    return local + "@" + domain.lower()

def extract_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower()
''',
        '''import pytest
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
''',
        '''from src.email_validator import is_valid_email, normalize

def test_valid_and_normalize():
    assert is_valid_email("x@y.io") is True
    assert normalize("Abc@Company.COM") == "Abc@company.com"
''',
        ["user@localhost accepted as valid", "normalize() lowercases local part"],
        ["missing TLD rejected", "local-part case preserved"],
    ),
    _t(
        "task_011", "task_011_temperature_converter", "src/temperature.py",
        "arithmetic_logic", "easy",
        "Bug: celsius_to_fahrenheit() uses wrong scale factor and fahrenheit_to_celsius() rounds incorrectly",
        "## Bug Report\n**File:** `src/temperature.py`\n\n`celsius_to_fahrenheit()` multiplies by 1.8 "
        "but forgets the +32 offset, and `fahrenheit_to_celsius()` subtracts 32 AFTER multiplying instead "
        "of before.\n### Expected\n- `celsius_to_fahrenheit(100) == 212.0`\n- "
        "`fahrenheit_to_celsius(212) == 100.0`",
        '''def celsius_to_fahrenheit(c: float) -> float:
    # BUG: missing +32
    return c * 1.8

def fahrenheit_to_celsius(f: float) -> float:
    # BUG: subtracts 32 after scaling
    return (f * 5 / 9) - 32

def is_freezing(c: float) -> bool:
    return c <= 0

def is_boiling(c: float) -> bool:
    return c >= 100
''',
        '''def celsius_to_fahrenheit(c: float) -> float:
    return c * 9 / 5 + 32

def fahrenheit_to_celsius(f: float) -> float:
    return (f - 32) * 5 / 9

def is_freezing(c: float) -> bool:
    return c <= 0

def is_boiling(c: float) -> bool:
    return c >= 100
''',
        '''import pytest
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
''',
        '''from src.temperature import is_freezing, is_boiling

def test_thresholds():
    assert is_freezing(-5) is True
    assert is_freezing(5) is False
    assert is_boiling(105) is True
    assert is_boiling(50) is False
''',
        ["celsius_to_fahrenheit(100) == 180", "fahrenheit_to_celsius(212) != 100"],
        ["correct conversion formulas both directions"],
    ),
    _t(
        "task_012", "task_012_config_loader", "src/config_loader.py",
        "state_management", "medium",
        "Bug: Config.set() mutates DEFAULTS globally and get() with a missing key raises instead of returning the fallback",
        "## Bug Report\n**File:** `src/config_loader.py`\n\n`Config.set()` writes into the shared "
        "`DEFAULTS` dict, so two `Config` instances leak values into each other. `get(key, default)` "
        "raises `KeyError` instead of returning `default` when the key is missing.\n"
        "### Expected\n- instances have independent overrides\n- `get('missing', 'fb') == 'fb'`",
        '''DEFAULTS = {"timeout": 30, "retries": 3, "debug": False}

class Config:
    def __init__(self, **overrides):
        self._values = dict(DEFAULTS)
        self._values.update(overrides)

    def get(self, key, default=None):
        # BUG: raises instead of returning default
        return self._values[key]

    def set(self, key, value):
        # BUG: mutates the global DEFAULTS dict
        DEFAULTS[key] = value
        self._values[key] = value

    def as_dict(self):
        return dict(self._values)
''',
        '''DEFAULTS = {"timeout": 30, "retries": 3, "debug": False}

class Config:
    def __init__(self, **overrides):
        self._values = dict(DEFAULTS)
        self._values.update(overrides)

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value

    def as_dict(self):
        return dict(self._values)
''',
        '''import pytest
from src.config_loader import Config, DEFAULTS

def test_get_missing_key_returns_default():
    cfg = Config()
    assert cfg.get("nonexistent", "fallback") == "fallback"

def test_set_is_instance_local():
    cfg_a = Config()
    cfg_b = Config()
    cfg_a.set("timeout", 99)
    assert cfg_b.get("timeout") == 30

def test_defaults_dict_not_polluted():
    before = dict(DEFAULTS)
    cfg = Config()
    cfg.set("brand_new_key", 123)
    assert "brand_new_key" not in DEFAULTS
    assert set(DEFAULTS) == set(before)

def test_overrides_applied():
    cfg = Config(timeout=5)
    assert cfg.get("timeout") == 5
    assert cfg.get("retries") == 3

def test_as_dict_snapshot():
    cfg = Config()
    cfg.set("x", 1)
    d = cfg.as_dict()
    d["x"] = 999
    assert cfg.get("x") == 1
''',
        '''from src.config_loader import Config

def test_defaults_readable():
    cfg = Config()
    assert cfg.get("debug") is False
''',
        ["set() leaks into DEFAULTS/global state", "get() raises KeyError on missing key"],
        ["per-instance overrides", "get() returns fallback"],
    ),
    _t(
        "task_013", "task_013_text_stats", "src/text_stats.py",
        "data_transformation", "medium",
        "Bug: word_frequencies() is case-sensitive, top_words() breaks ties inconsistently, and char stats count whitespace",
        "## Bug Report\n**File:** `src/text_stats.py`\n\n`word_frequencies()` treats 'The' and 'the' as "
        "different words. `top_words(n)` does not break frequency ties alphabetically, so output order is "
        "nondeterministic. `letter_frequency()` counts spaces and punctuation.\n"
        "### Expected\n- case-insensitive counting\n- deterministic tie-break (alphabetical)\n"
        "- only alphabetic characters counted in letter_frequency",
        '''from collections import Counter

def word_frequencies(text: str) -> dict:
    # BUG: case-sensitive
    words = text.split()
    return dict(Counter(words))

def top_words(text: str, n: int) -> list:
    # BUG: nondeterministic tie-break
    freq = word_frequencies(text)
    return sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:n]

def letter_frequency(text: str) -> dict:
    # BUG: counts whitespace/punctuation too
    return dict(Counter(text))
''',
        '''from collections import Counter

def word_frequencies(text: str) -> dict:
    words = text.lower().split()
    return dict(Counter(words))

def top_words(text: str, n: int) -> list:
    freq = word_frequencies(text)
    return sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:n]

def letter_frequency(text: str) -> dict:
    return dict(Counter(ch.lower() for ch in text if ch.isalpha()))
''',
        '''from src.text_stats import word_frequencies, top_words, letter_frequency

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
''',
        '''from src.text_stats import word_frequencies

def test_simple_frequency():
    freq = word_frequencies("hello hello world")
    assert freq["hello"] == 2
''',
        ["case-sensitive counting", "nondeterministic tie order", "punctuation counted as letters"],
        ["case-insensitive", "alphabetical tie-break", "alphabetic-only letter stats"],
    ),
    _t(
        "task_014", "task_014_queue_manager", "src/queue_manager.py",
        "off_by_one", "medium",
        "Bug: Queue.pop() returns the newest item instead of the oldest (FIFO violated) and peek() on empty raises",
        "## Bug Report\n**File:** `src/queue_manager.py`\n\n`TaskQueue.pop()` removes the LAST item "
        "(LIFO) although the class is documented as FIFO. `peek()` on an empty queue raises IndexError "
        "instead of returning None.\n### Expected\n- pop() returns items in insertion order\n"
        "- peek()/pop() on empty return None (pop with default)",
        '''class TaskQueue:
    def __init__(self):
        self._items = []

    def push(self, item) -> None:
        self._items.append(item)

    def pop(self):
        # BUG: LIFO instead of FIFO
        if not self._items:
            return None
        return self._items.pop()

    def peek(self):
        # BUG: raises on empty
        return self._items[-1]

    def __len__(self):
        return len(self._items)
''',
        '''class TaskQueue:
    def __init__(self):
        self._items = []

    def push(self, item) -> None:
        self._items.append(item)

    def pop(self):
        if not self._items:
            return None
        return self._items.pop(0)

    def peek(self):
        if not self._items:
            return None
        return self._items[0]

    def __len__(self):
        return len(self._items)
''',
        '''from src.queue_manager import TaskQueue

def test_fifo_order():
    q = TaskQueue()
    q.push("first")
    q.push("second")
    q.push("third")
    assert q.pop() == "first"
    assert q.pop() == "second"

def test_peek_returns_oldest():
    q = TaskQueue()
    q.push("a")
    q.push("b")
    assert q.peek() == "a"
    assert len(q) == 2

def test_pop_empty_returns_none():
    q = TaskQueue()
    assert q.pop() is None

def test_peek_empty_returns_none():
    q = TaskQueue()
    assert q.peek() is None

def test_mixed_usage():
    q = TaskQueue()
    assert q.pop() is None
    q.push(1)
    q.push(2)
    assert q.pop() == 1
    q.push(3)
    assert q.pop() == 2
    assert q.pop() == 3
    assert q.pop() is None
''',
        '''from src.queue_manager import TaskQueue

def test_push_increases_length():
    q = TaskQueue()
    assert len(q) == 0
    q.push("x")
    assert len(q) == 1
''',
        ["pop() is LIFO", "peek() raises IndexError on empty"],
        ["pop() is FIFO", "peek()/pop() return None on empty"],
    ),
]