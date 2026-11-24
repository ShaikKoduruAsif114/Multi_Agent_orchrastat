"""
evaluation/benchmark/specs_new_3.py
Tasks 023-030: json_flattener, lru_cache, slugify, statistics_utils,
path_resolver, retry_policy, interval_merger, ini_parser
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


NEW_TASKS_3 = [
    _t(
        "task_023", "task_023_json_flattener", "src/json_flattener.py",
        "data_transformation", "hard",
        "Bug: flatten_json() loses nested keys deeper than 2 levels and mangles list indices",
        "## Bug Report\n**File:** `src/json_flattener.py`\n\n`flatten_json({'a': {'b': {'c': 1}}})` "
        "returns the wrong result for depth-3 nesting (inner dicts are str()-ed instead of recursed). "
        "Arrays produce keys like 'a.0' via enumerate off-by-one ('a.1' for the first element).\n"
        "### Expected\n- arbitrary nesting recursed: 'a.b.c' -> 1\n- list indices are 0-based: "
        "'items.0' for the first element\n- `unflatten()` restores nested structure",
        '''def flatten_json(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                # BUG: fails to recurse for depth > 2 -> str() fallback
                inner = flatten_json(v, key)
                if inner:
                    out.update(inner)
                else:
                    out[key] = str(v)
            else:
                out[key] = v
    elif isinstance(obj, list):
        for i, v in enumerate(obj, start=1):
            # BUG: 1-based indices
            key = f"{prefix}.{i}" if prefix else str(i)
            if isinstance(v, (dict, list)):
                inner = flatten_json(v, key)
                if inner:
                    out.update(inner)
                else:
                    out[key] = str(v)
            else:
                out[key] = v
    return out

def unflatten(flat: dict) -> dict:
    result = {}
    for key, value in flat.items():
        parts = key.split(".")
        node = result
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return result
''',
        '''def flatten_json(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            out.update(flatten_json(v, key))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            key = f"{prefix}.{i}" if prefix else str(i)
            out.update(flatten_json(v, key))
    else:
        out[prefix] = obj
    return out

def unflatten(flat: dict) -> dict:
    result = {}
    for key, value in flat.items():
        parts = key.split(".")
        node = result
        for i, part in enumerate(parts[:-1]):
            nxt = parts[i + 1]
            if nxt.isdigit():
                node = node.setdefault(part, [])
            else:
                node = node.setdefault(part, {})
            if isinstance(node, list):
                while len(node) <= int(nxt):
                    node.append({})
                node = node[int(nxt)]
        node[parts[-1]] = value
    return result
''',
        '''from src.json_flattener import flatten_json, unflatten

def test_depth_three_nesting():
    flat = flatten_json({"a": {"b": {"c": 1}}})
    assert flat == {"a.b.c": 1}

def test_list_indices_zero_based():
    flat = flatten_json({"items": ["x", "y"]})
    assert flat == {"items.0": "x", "items.1": "y"}

def test_mixed_nesting():
    flat = flatten_json({"a": {"list": [1, {"deep": 2}]}, "b": 3})
    assert flat == {"a.list.0": 1, "a.list.1.deep": 2, "b": 3}

def test_scalars():
    assert flatten_json({"x": 5}) == {"x": 5}
    assert flatten_json({}) == {}
    assert flatten_json([]) == {}

def test_values_preserved():
    flat = flatten_json({"n": None, "f": 1.5, "s": "hi", "b": False})
    assert flat == {"n": None, "f": 1.5, "s": "hi", "b": False}

def test_unflatten_round_trip():
    original = {"a": {"b": 1}, "c": 2}
    assert unflatten(flatten_json(original)) == original
''',
        '''from src.json_flattener import flatten_json

def test_simple_flatten():
    assert flatten_json({"a": {"b": 2}}) == {"a.b": 2}
''',
        ["depth-3 dicts become str() values", "list keys are 1-based"],
        ["full recursion", "0-based list indices", "round-trip unflatten"],
    ),
    _t(
        "task_024", "task_024_lru_cache", "src/lru_cache.py",
        "state_management", "hard",
        "Bug: LRUCache evicts the most recently used entry and get() does not refresh recency",
        "## Bug Report\n**File:** `src/lru_cache.py`\n\n`LRUCache.get()` does not move the accessed "
        "key to the most-recently-used position, and `put()` evicts from the FRONT of the order list "
        "(which after insertion order is the *most* recently used). Correct LRU behavior required.\n"
        "### Expected\n- get() refreshes recency\n- eviction removes the LEAST recently used entry\n"
        "- capacity never exceeded",
        '''class LRUCache:
    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self._data = {}
        self._order = []

    def get(self, key):
        # BUG: no recency refresh on access
        return self._data.get(key)

    def put(self, key, value):
        if key in self._data:
            self._data[key] = value
            return
        if len(self._data) >= self.capacity:
            # BUG: evicts most recently used (front of order list)
            victim = self._order.pop(0)
            del self._data[victim]
        self._data[key] = value
        self._order.append(key)

    def __len__(self):
        return len(self._data)

    def keys_snapshot(self):
        return list(self._order)
''',
        '''class LRUCache:
    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self._data = {}
        self._order = []

    def _touch(self, key):
        if key in self._order:
            self._order.remove(key)
        self._order.append(key)

    def get(self, key):
        if key in self._data:
            self._touch(key)
            return self._data[key]
        return None

    def put(self, key, value):
        self._touch(key)
        self._data[key] = value
        if len(self._data) > self.capacity:
            victim = self._order.pop(0)
            del self._data[victim]

    def __len__(self):
        return len(self._data)

    def keys_snapshot(self):
        return list(self._order)
''',
        '''from src.lru_cache import LRUCache

def test_put_and_get():
    cache = LRUCache(2)
    cache.put("a", 1)
    assert cache.get("a") == 1

def test_evicts_least_recently_used():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3

def test_get_refreshes_recency():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1

def test_update_existing_key_no_eviction():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 10)
    assert len(cache) == 2
    assert cache.get("a") == 10

def test_capacity_never_exceeded():
    cache = LRUCache(3)
    for i in range(10):
        cache.put(f"k{i}", i)
    assert len(cache) == 3

def test_order_snapshot_reflects_recency():
    cache = LRUCache(2)
    cache.put("x", 1)
    cache.put("y", 2)
    cache.get("x")
    assert cache.keys_snapshot() == ["y", "x"]
''',
        '''from src.lru_cache import LRUCache

def test_capacity_validation():
    try:
        LRUCache(0)
        raised = False
    except ValueError:
        raised = True
    assert raised
''',
        ["get() does not refresh recency", "put() evicts the newest entry"],
        ["true LRU eviction semantics"],
    ),
    _t(
        "task_025", "task_025_slugify", "src/slugify.py",
        "parsing", "easy",
        "Bug: slugify() leaves punctuation in output and does not collapse consecutive separators",
        "## Bug Report\n**File:** `src/slugify.py`\n\n`slugify('Hello, World!')` returns "
        "`'hello,-world!'` — only whitespace/underscores are split, so punctuation survives and "
        "consecutive separators produce repeated hyphens ('a  b' -> 'a--b').\n"
        "### Expected\n- lowercase, non-alphanumerics become single hyphens, no leading/trailing hyphens\n"
        "- `slugify('Hello, World!') == 'hello-world'`",
        '''import re

def slugify(text: str) -> str:
    text = text.lower()
    # BUG: punctuation handled after join; no collapse
    words = re.split(r"[\\s_]", text)
    return "-".join(words)

def slugify_upper(text: str) -> str:
    return slugify(text).upper()

def truncate_slug(slug: str, max_len: int) -> str:
    if len(slug) <= max_len:
        return slug
    return slug[:max_len]
''',
        '''import re

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")

def slugify_upper(text: str) -> str:
    return slugify(text).upper()

def truncate_slug(slug: str, max_len: int) -> str:
    if len(slug) <= max_len:
        return slug
    truncated = slug[:max_len]
    return truncated.rstrip("-")
''',
        '''from src.slugify import slugify, slugify_upper, truncate_slug

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
''',
        '''from src.slugify import slugify

def test_simple_word():
    assert slugify("Hello") == "hello"
''',
        ["punctuation survives", "'a  b' -> 'a--b'"],
        ["clean single-hyphen slugs"],
    ),
    _t(
        "task_026", "task_026_statistics_utils", "src/statistics_utils.py",
        "arithmetic_logic", "medium",
        "Bug: median() picks the wrong element for even-length input and percentile() extrapolates beyond the data",
        "## Bug Report\n**File:** `src/statistics_utils.py`\n\n`median()` returns the lower of the "
        "two middle elements for even-length lists instead of their mean. `percentile(data, p)` for "
        "p=0 goes out of bounds.\n### Expected\n- median([1,2,3,4]) == 2.5\n- `percentile(data, 0)` "
        "returns min, `percentile(data, 100)` returns max",
        '''def median(values: list):
    if not values:
        raise ValueError("empty list")
    s = sorted(values)
    n = len(s)
    mid = n // 2
    # BUG: even case ignores upper middle element
    if n % 2 == 0:
        return s[mid - 1]
    return s[mid]

def percentile(values: list, p: float):
    if not values:
        raise ValueError("empty list")
    s = sorted(values)
    k = (len(s) - 1) * (p / 100)
    # BUG: no clamping -> p=0 gives index -0 fine but p slightly >100 explodes
    return s[int(round(k))]

def mean(values: list) -> float:
    if not values:
        raise ValueError("empty list")
    return sum(values) / len(values)
''',
        '''def median(values: list):
    if not values:
        raise ValueError("empty list")
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2
    return s[mid]

def percentile(values: list, p: float):
    if not values:
        raise ValueError("empty list")
    if not 0 <= p <= 100:
        raise ValueError("p must be in [0, 100]")
    s = sorted(values)
    k = (len(s) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)

def mean(values: list) -> float:
    if not values:
        raise ValueError("empty list")
    return sum(values) / len(values)
''',
        '''import pytest
from src.statistics_utils import median, percentile, mean

def test_median_odd():
    assert median([5, 1, 3]) == 3

def test_median_even_averages_middle():
    assert median([1, 2, 3, 4]) == 2.5
    assert median([4, 2]) == 3.0

def test_median_unsorted_input():
    assert median([9, 1, 8, 2]) == 5.0

def test_median_empty_raises():
    with pytest.raises(ValueError):
        median([])

def test_percentile_bounds():
    data = [10, 20, 30, 40]
    assert percentile(data, 0) == 10
    assert percentile(data, 100) == 40

def test_percentile_interpolates():
    data = [10, 20, 30, 40]
    assert percentile(data, 50) == 25.0

def test_percentile_out_of_range_raises():
    with pytest.raises(ValueError):
        percentile([1, 2], 150)

def test_mean():
    assert mean([2, 4, 6]) == 4.0
''',
        '''from src.statistics_utils import mean

def test_mean_simple():
    assert mean([1, 2, 3]) == 2.0
''',
        ["even-length median takes lower element", "percentile beyond bounds crashes"],
        ["averaged median", "clamped/interpolated percentile"],
    ),
    _t(
        "task_027", "task_027_path_resolver", "src/path_resolver.py",
        "file_path", "medium",
        "Bug: resolve_path() joins URLs/paths wrongly, missing extension detection, and relative walk escapes root",
        "## Bug Report\n**File:** `src/path_resolver.py`\n\n`resolve_path(base, sub)` breaks when "
        "`sub` is absolute (should return the absolute sub as-is) or when segments are empty. "
        "`has_extension()` returns True for names like 'archive.tar.gz' even when checking for '.gz' "
        "on a stem-only check basis; `is_within_root()` incorrectly approves paths containing '..' "
        "segments.\n### Expected\n- absolute sub -> returned unchanged\n- 'a/../../etc' must be "
        "rejected by is_within_root",
        '''import os

def resolve_path(base: str, sub: str) -> str:
    # BUG: absolute 'sub' gets joined under base anyway
    if not sub:
        return base
    return os.path.join(base, sub)

def has_extension(name: str, ext: str) -> bool:
    # BUG: substring check matches anywhere in the name
    return ext in name

def is_within_root(root: str, target: str) -> bool:
    # BUG: naive prefix check, ignores '..' traversal
    normalized = os.path.normpath(target)
    return normalized.startswith(os.path.basename(root))
''',
        '''import os

def resolve_path(base: str, sub: str) -> str:
    if not sub:
        return base
    if os.path.isabs(sub):
        return os.path.normpath(sub)
    return os.path.normpath(os.path.join(base, sub))

def has_extension(name: str, ext: str) -> bool:
    if not ext.startswith("."):
        ext = "." + ext
    return os.path.splitext(name)[1].lower() == ext.lower()

def is_within_root(root: str, target: str) -> bool:
    root_abs = os.path.abspath(root)
    target_abs = os.path.abspath(target)
    return os.path.commonpath([root_abs, target_abs]) == root_abs
''',
        '''import pytest
from src.path_resolver import resolve_path, has_extension, is_within_root
import os

def test_resolve_relative(tmp_path):
    result = resolve_path(str(tmp_path), "src/main.py")
    assert result == os.path.join(str(tmp_path), "src", "main.py")

def test_resolve_absolute_sub_unchanged(tmp_path):
    absolute = os.path.abspath(os.sep + "etc" + os.sep + "passwd")
    result = resolve_path(str(tmp_path), absolute)
    assert os.path.normpath(result) == absolute

def test_resolve_empty_sub():
    assert resolve_path("C:\\\\base", "") == "C:\\\\base"

def test_has_extension_correct():
    assert has_extension("report.pdf", ".pdf") is True
    assert has_extension("report.pdf", "pdf") is True
    assert has_extension("archive.tar.gz", ".gz") is True
    assert has_extension("notes.txt", ".pdf") is False
    assert has_extension("unrelated.pdf.bak", ".pdf") is False

def test_is_within_root_blocks_traversal(tmp_path):
    inside = tmp_path / "a.txt"
    inside.write_text("x")
    assert is_within_root(str(tmp_path), str(inside)) is True
    outside = tmp_path.parent / "sibling.txt"
    outside.write_text("x")
    assert is_within_root(str(tmp_path), str(outside)) is False

def test_is_within_root_rejects_dotdot(tmp_path):
    sneaky = str(tmp_path / ".." / "escape.txt")
    assert is_within_root(str(tmp_path), sneaky) is False
''',
        '''from src.path_resolver import resolve_path

def test_resolve_simple():
    import os
    assert "main.py" in resolve_path(os.getcwd(), "main.py")
''',
        ["absolute sub joined under base", "has_extension is a substring check", "'..' traversal approved"],
        ["absolute preserved", "true extension comparison", "traversal rejected"],
    ),
    _t(
        "task_028", "task_028_retry_policy", "src/retry_policy.py",
        "api_misuse", "hard",
        "Bug: backoff_delay() computes exponentially growing delays without a cap and retry loop passes wrong args to the callable",
        "## Bug Report\n**File:** `src/retry_policy.py`\n\n`backoff_delay(attempt)` grows without "
        "bound (ignores `max_delay`) and resets on jitter. `retry_call(func, *args)` calls `func()` "
        "without forwarding `args` — the classic API-misuse bug.\n"
        "### Expected\n- delay = min(base * 2**attempt, max_delay)\n- `retry_call` forwards all "
        "positional args to `func` and returns its result",
        '''import time

def backoff_delay(attempt: int, base: float = 0.5, max_delay: float = 30.0) -> float:
    # BUG: ignores max_delay entirely
    return base * (2 ** attempt)

def retry_call(func, *args, retries: int = 3, base: float = 0.5):
    last_error = None
    for attempt in range(retries + 1):
        try:
            # BUG: args never forwarded
            return func()
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff_delay(attempt, base))
    raise last_error

def parse_retry_after(header: str) -> float:
    return float(header)
''',
        '''import time

def backoff_delay(attempt: int, base: float = 0.5, max_delay: float = 30.0) -> float:
    return min(base * (2 ** attempt), max_delay)

def retry_call(func, *args, retries: int = 3, base: float = 0.5):
    last_error = None
    for attempt in range(retries + 1):
        try:
            return func(*args)
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff_delay(attempt, base))
    raise last_error

def parse_retry_after(header: str) -> float:
    return float(header)
''',
        '''import pytest
from src.retry_policy import backoff_delay, retry_call, parse_retry_after

def test_backoff_growth_is_capped():
    delays = [backoff_delay(a, base=0.5, max_delay=2.0) for a in range(6)]
    assert delays == [0.5, 1.0, 2.0, 2.0, 2.0, 2.0]

def test_backoff_default_cap():
    assert backoff_delay(20) == 30.0

def test_retry_call_forwards_args():
    calls = []
    def flaky(a, b):
        calls.append((a, b))
        if len(calls) < 3:
            raise IOError("transient")
        return a + b
    result = retry_call(flaky, 2, 3)
    assert result == 5
    assert calls == [(2, 3), (2, 3), (2, 3)]

def test_retry_call_eventual_failure_reraises():
    def always_fail(x):
        raise ValueError(f"bad {x}")
    with pytest.raises(ValueError):
        retry_call(always_fail, 7, retries=2)

def test_retry_call_zero_retries():
    def ok():
        return "done"
    assert retry_call(ok, retries=0) == "done"

def test_parse_retry_after():
    assert parse_retry_after("5") == 5.0
''',
        '''from src.retry_policy import backoff_delay

def test_first_delay():
    assert backoff_delay(0) == 0.5
''',
        ["uncapped exponential delay", "args dropped when calling func"],
        ["capped backoff", "args forwarded and result returned"],
    ),
    _t(
        "task_029", "task_029_interval_merger", "src/interval_merger.py",
        "regression_style", "hard",
        "Bug: merge_intervals() misses overlaps for touching ranges and insert_interval() corrupts ordering",
        "## Bug Report\n**File:** `src/interval_merger.py`\n\nA v2.0 regression: `merge_intervals()` "
        "no longer merges adjacent-but-touching intervals like (1,3) and (3,5) that used to merge into "
        "(1,5), and `insert_interval()` appends without re-sorting so later operations see corrupt order.\n"
        "### Expected\n- touching intervals merge\n- `insert_interval()` keeps the list sorted\n"
        "- overlaps merge correctly",
        '''def merge_intervals(intervals: list) -> list:
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        last = merged[-1]
        # BUG: requires strict overlap; touching ranges no longer merged
        if start < last[1]:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return [tuple(iv) for iv in merged]

def insert_interval(intervals: list, interval: tuple) -> list:
    # BUG: appends without restoring sorted order
    intervals.append(interval)
    return intervals

def total_coverage(intervals: list) -> int:
    return sum(end - start for start, end in merge_intervals(intervals))
''',
        '''def merge_intervals(intervals: list) -> list:
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        last = merged[-1]
        if start <= last[1]:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return [tuple(iv) for iv in merged]

def insert_interval(intervals: list, interval: tuple) -> list:
    intervals.append(interval)
    intervals.sort()
    return intervals

def total_coverage(intervals: list) -> int:
    return sum(end - start for start, end in merge_intervals(intervals))
''',
        '''from src.interval_merger import merge_intervals, insert_interval, total_coverage

def test_overlapping_merge():
    assert merge_intervals([(1, 4), (2, 5)]) == [(1, 5)]

def test_touching_intervals_merge():
    assert merge_intervals([(1, 3), (3, 5)]) == [(1, 5)]

def test_disjoint_stay_separate():
    assert merge_intervals([(1, 2), (4, 5)]) == [(1, 2), (4, 5)]

def test_unsorted_input():
    assert merge_intervals([(5, 7), (1, 3), (2, 4)]) == [(1, 4), (5, 7)]

def test_containment():
    assert merge_intervals([(1, 10), (2, 3)]) == [(1, 10)]

def test_insert_keeps_sorted():
    result = insert_interval([(1, 2), (7, 8)], (4, 5))
    assert result == [(1, 2), (4, 5), (7, 8)]

def test_insert_empty():
    assert insert_interval([], (0, 1)) == [(0, 1)]

def test_total_coverage_no_double_count():
    assert total_coverage([(1, 4), (3, 6), (8, 10)]) == 7
''',
        '''from src.interval_merger import merge_intervals

def test_single_interval():
    assert merge_intervals([(2, 9)]) == [(2, 9)]
''',
        ["(1,3)+(3,5) no longer merge", "insert_interval leaves list unsorted"],
        ["touching ranges merge", "sorted insertion"],
    ),
    _t(
        "task_030", "task_030_ini_parser", "src/ini_parser.py",
        "configuration", "medium",
        "Bug: parse_ini() drops duplicate keys instead of last-wins, ignores inline comments, and section headers keep brackets",
        "## Bug Report\n**File:** `src/ini_parser.py`\n\n`parse_ini()` stores section headers WITH "
        "brackets (`[core]`), splits `key = value # comment` including the comment into the value, and "
        "when a key repeats the first value wins (should be last-wins).\n"
        "### Expected\n- sections stored without brackets\n- inline `;` comments stripped\n"
        "- duplicate keys: last value wins",
        '''def parse_ini(text: str) -> dict:
    config = {}
    section = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("["):
            # BUG: brackets kept in the section name
            section = line
            config[section] = {}
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        # BUG: inline comments not stripped
        if section is not None:
            config[section][key.strip()] = value.strip()
    return config

def get_value(config: dict, section: str, key: str, default=None):
    sec = config.get(f"[{section}]", config.get(section))
    if sec is None:
        return default
    return sec.get(key, default)
''',
        '''def parse_ini(text: str) -> dict:
    config = {}
    section = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("["):
            if line.endswith("]"):
                line = line[1:-1]
            section = line.strip()
            config.setdefault(section, {})
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(";", 1)[0].split("#", 1)[0].strip()
        if section is not None:
            config[section][key.strip()] = value
    return config

def get_value(config: dict, section: str, key: str, default=None):
    sec = config.get(section)
    if sec is None:
        return default
    return sec.get(key, default)
''',
        '''from src.ini_parser import parse_ini, get_value

def test_sections_without_brackets():
    config = parse_ini("[core]\\nname = app\\n")
    assert "core" in config
    assert "[core]" not in config
    assert config["core"]["name"] == "app"

def test_inline_comment_stripped():
    config = parse_ini("[core]\\nport = 8080 ; the port\\n")
    assert config["core"]["port"] == "8080"

def test_hash_comment_stripped():
    config = parse_ini("[core]\\nmode = fast # speed\\n")
    assert config["core"]["mode"] == "fast"

def test_duplicate_keys_last_wins():
    config = parse_ini("[core]\\ntimeout = 5\\ntimeout = 30\\n")
    assert config["core"]["timeout"] == "30"

def test_comment_only_lines_ignored():
    config = parse_ini("; a comment\\n# another\\n[net]\\nssl = on\\n")
    assert config == {"net": {"ssl": "on"}}

def test_get_value_helper():
    config = parse_ini("[db]\\nhost = local\\n")
    assert get_value(config, "db", "host") == "local"
    assert get_value(config, "db", "missing", "fallback") == "fallback"
    assert get_value(config, "no_section", "k") is None
''',
        '''from src.ini_parser import parse_ini

def test_simple_parse():
    config = parse_ini("[a]\\nx = 1\\n")
    assert config["a"]["x"] == "1"
''',
        ["section keys contain brackets", "inline comments leak into values", "first duplicate value wins"],
        ["bracket-free sections", "comments stripped", "last-wins semantics"],
    ),
]