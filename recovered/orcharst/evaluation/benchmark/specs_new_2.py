"""
evaluation/benchmark/specs_new_2.py
Tasks 015-022: pagination, file_utils, api_client, session_store,
data_transform, rate_limiter, ledger, feature_flags
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


NEW_TASKS_2 = [
    _t(
        "task_015", "task_015_pagination", "src/pagination.py",
        "off_by_one", "medium",
        "Bug: paginate() returns the wrong slice for the last page and total_pages() over-counts",
        "## Bug Report\n**File:** `src/pagination.py`\n\n`paginate(items, page, size)` computes "
        "`start = page * size` but ends at `start + size - 1`, silently dropping the last item of every "
        "page. `total_pages()` uses integer division without rounding up, so 10 items with page size 4 "
        "report 2 pages instead of 3.\n### Expected\n- page 2 of [0..9] with size 4 is [4,5,6,7]\n"
        "- `total_pages(10, 4) == 3`",
        '''def paginate(items: list, page: int, size: int) -> list:
    if page < 1 or size < 1:
        raise ValueError("page and size must be >= 1")
    start = (page - 1) * size
    # BUG: end index drops the last item of the page
    return items[start:start + size - 1]

def total_pages(item_count: int, size: int) -> int:
    if size < 1:
        raise ValueError("size must be >= 1")
    # BUG: no ceiling
    return item_count // size

def page_bounds(page: int, size: int, item_count: int):
    start = (page - 1) * size
    return (start, min(start + size, item_count))
''',
        '''def paginate(items: list, page: int, size: int) -> list:
    if page < 1 or size < 1:
        raise ValueError("page and size must be >= 1")
    start = (page - 1) * size
    return items[start:start + size]

def total_pages(item_count: int, size: int) -> int:
    if size < 1:
        raise ValueError("size must be >= 1")
    return (item_count + size - 1) // size

def page_bounds(page: int, size: int, item_count: int):
    start = (page - 1) * size
    return (start, min(start + size, item_count))
''',
        '''import pytest
from src.pagination import paginate, total_pages, page_bounds

def test_paginate_first_page():
    items = list(range(10))
    assert paginate(items, 1, 4) == [0, 1, 2, 3]

def test_paginate_middle_page():
    items = list(range(10))
    assert paginate(items, 2, 4) == [4, 5, 6, 7]

def test_paginate_last_partial_page():
    items = list(range(10))
    assert paginate(items, 3, 4) == [8, 9]

def test_paginate_beyond_end():
    items = list(range(5))
    assert paginate(items, 9, 4) == []

def test_total_pages_ceil():
    assert total_pages(10, 4) == 3
    assert total_pages(8, 4) == 2
    assert total_pages(1, 4) == 1
    assert total_pages(0, 4) == 0

def test_page_bounds():
    assert page_bounds(2, 4, 10) == (4, 8)
    assert page_bounds(3, 4, 10) == (8, 10)
''',
        '''import pytest
from src.pagination import paginate

def test_paginate_invalid_args():
    with pytest.raises(ValueError):
        paginate([1], 0, 1)
''',
        ["every page drops its last item", "total_pages under-counts"],
        ["correct slicing", "ceiling division"],
    ),
    _t(
        "task_016", "task_016_file_utils", "src/file_utils.py",
        "file_path", "medium",
        "Bug: safe_read() swallows real errors, count_lines() miscounts the last line, and append_file() crashes on missing dirs",
        "## Bug Report\n**File:** `src/file_utils.py`\n\n`safe_read()` returns `''` for ANY error "
        "including permission errors (should only tolerate FileNotFoundError). `count_lines()` misses "
        "the final line when the file lacks a trailing newline. `append_file()` should create missing "
        "parent directories but crashes when they don't exist.\n### Expected\n- missing file -> '' but "
        "other OSError -> raise\n- no trailing newline still counted\n- append creates parents",
        '''def safe_read(path: str) -> str:
    # BUG: swallows all exceptions
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

def count_lines(path: str) -> int:
    with open(path, "r", encoding="utf-8") as f:
        # BUG: misses last line without trailing newline
        return sum(1 for line in f if line.endswith("\\n"))

def append_file(path: str, text: str) -> None:
    # BUG: crashes if parent dir missing
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)

def file_size(path: str) -> int:
    import os
    return os.path.getsize(path)
''',
        '''def safe_read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""

def count_lines(path: str) -> int:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if not content:
        return 0
    n = content.count("\\n")
    if not content.endswith("\\n"):
        n += 1
    return n

def append_file(path: str, text: str) -> None:
    import os
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)

def file_size(path: str) -> int:
    import os
    return os.path.getsize(path)
''',
        '''import pytest
from src.file_utils import safe_read, count_lines, append_file, file_size

def test_safe_read_existing(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello", encoding="utf-8")
    assert safe_read(str(p)) == "hello"

def test_safe_read_missing_returns_empty(tmp_path):
    assert safe_read(str(tmp_path / "missing.txt")) == ""

def test_count_lines_with_trailing_newline(tmp_path):
    p = tmp_path / "b.txt"
    p.write_text("one\\ntwo\\n", encoding="utf-8")
    assert count_lines(str(p)) == 2

def test_count_lines_without_trailing_newline(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("one\\ntwo", encoding="utf-8")
    assert count_lines(str(p)) == 2

def test_count_lines_empty(tmp_path):
    p = tmp_path / "d.txt"
    p.write_text("", encoding="utf-8")
    assert count_lines(str(p)) == 0

def test_append_creates_missing_dirs(tmp_path):
    target = tmp_path / "sub" / "dir" / "log.txt"
    append_file(str(target), "entry\\n")
    append_file(str(target), "entry2\\n")
    assert target.read_text(encoding="utf-8") == "entry\\nentry2\\n"

def test_file_size(tmp_path):
    p = tmp_path / "e.txt"
    p.write_text("12345", encoding="utf-8")
    assert file_size(str(p)) == 5
''',
        '''from src.file_utils import safe_read

def test_safe_read_api():
    assert safe_read("definitely/not/here.txt") == ""
''',
        ["permission/other errors silently become ''", "last line uncounted", "append crashes on missing dirs"],
        ["only FileNotFoundError tolerated", "correct line counting", "append creates parents"],
    ),
    _t(
        "task_017", "task_017_api_client", "src/api_client.py",
        "api_misuse", "medium",
        "Bug: ApiClient.get() passes URL as keyword the server mock rejects and post() ignores json_body",
        "## Bug Report\n**File:** `src/api_client.py`\n\n`ApiClient` wraps an HTTP session. "
        "`get()` calls `session.request('GET', params=...)` but passes the query params positionally "
        "into the wrong slot, and `post()` builds the body but never forwards it to the session "
        "(`json_body` is dropped). Backed by an injectable session for testing.\n"
        "### Expected\n- `get('/users', params={'a': 1})` forwards `params={'a': 1}`\n"
        "- `post('/users', json_body={...})` forwards `json={...}`",
        '''class ApiClient:
    def __init__(self, session, base_url="https://api.example.com"):
        self.session = session
        self.base_url = base_url.rstrip("/")

    def get(self, path: str, params=None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        # BUG: params passed positionally into headers slot
        return self.session.request("GET", url, params)

    def post(self, path: str, json_body=None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        # BUG: json_body never forwarded
        return self.session.request("POST", url)

    def delete(self, path: str):
        url = f"{self.base_url}/{path.lstrip('/')}"
        return self.session.request("DELETE", url)
''',
        '''class ApiClient:
    def __init__(self, session, base_url="https://api.example.com"):
        self.session = session
        self.base_url = base_url.rstrip("/")

    def get(self, path: str, params=None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        return self.session.request("GET", url, params=params)

    def post(self, path: str, json_body=None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        return self.session.request("POST", url, json=json_body)

    def delete(self, path: str):
        url = f"{self.base_url}/{path.lstrip('/')}"
        return self.session.request("DELETE", url)
''',
        '''from src.api_client import ApiClient

class FakeSession:
    def __init__(self):
        self.calls = []

    def request(self, method, url, params=None, json=None):
        self.calls.append({"method": method, "url": url, "params": params, "json": json})
        return {"status": 200, "method": method}

def test_get_forwards_params():
    s = FakeSession()
    client = ApiClient(s)
    client.get("/users", params={"page": 2})
    call = s.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://api.example.com/users"
    assert call["params"] == {"page": 2}

def test_get_without_params():
    s = FakeSession()
    client = ApiClient(s)
    client.get("/health")
    assert s.calls[0]["params"] is None

def test_post_forwards_json_body():
    s = FakeSession()
    client = ApiClient(s)
    client.post("/users", json_body={"name": "Ada"})
    call = s.calls[0]
    assert call["method"] == "POST"
    assert call["json"] == {"name": "Ada"}

def test_post_without_body():
    s = FakeSession()
    client = ApiClient(s)
    client.post("/ping")
    assert s.calls[0]["json"] is None

def test_delete():
    s = FakeSession()
    client = ApiClient(s)
    client.delete("/users/7")
    assert s.calls[0]["method"] == "DELETE"
    assert s.calls[0]["url"].endswith("/users/7")
''',
        '''from src.api_client import ApiClient

class EchoSession:
    def request(self, method, url, params=None, json=None):
        return method

def test_client_constructs():
    client = ApiClient(EchoSession())
    assert client.base_url == "https://api.example.com"
''',
        ["params land in the wrong argument slot", "json_body silently dropped on post()"],
        ["params and json forwarded to session"],
    ),
    _t(
        "task_018", "task_018_session_store", "src/session_store.py",
        "state_management", "medium",
        "Bug: SessionStore shares one dict across all instances and expired sessions are never cleaned",
        "## Bug Report\n**File:** `src/session_store.py`\n\n`SessionStore` uses a mutable default "
        "argument (`sessions={}`), so all instances share the same session dict. `purge_expired()` "
        "never removes anything because it compares against the wrong clock.\n"
        "### Expected\n- two stores are independent\n- `purge_expired(now)` drops sessions whose "
        "`expires_at <= now`",
        '''import time

def _now():
    return time.time()

class SessionStore:
    def __init__(self, sessions={}):
        # BUG: mutable default shared across instances
        self.sessions = sessions

    def create(self, token: str, ttl: float = 300.0):
        self.sessions[token] = {"expires_at": _now() + ttl, "data": {}}
        return self.sessions[token]

    def get(self, token: str, now=None):
        now = now if now is not None else _now()
        session = self.sessions.get(token)
        if not session:
            return None
        # BUG: sign flipped -> expired sessions still valid
        if session["expires_at"] >= now + 10**9:
            return None
        return session

    def purge_expired(self, now=None):
        now = now if now is not None else _now()
        removed = []
        for token, session in list(self.sessions.items()):
            # BUG: keeps everything (condition inverted)
            if session["expires_at"] < now - 10**9:
                removed.append(token)
                del self.sessions[token]
        return removed
''',
        '''import time

def _now():
    return time.time()

class SessionStore:
    def __init__(self, sessions=None):
        self.sessions = sessions if sessions is not None else {}

    def create(self, token: str, ttl: float = 300.0):
        self.sessions[token] = {"expires_at": _now() + ttl, "data": {}}
        return self.sessions[token]

    def get(self, token: str, now=None):
        now = now if now is not None else _now()
        session = self.sessions.get(token)
        if not session:
            return None
        if session["expires_at"] <= now:
            del self.sessions[token]
            return None
        return session

    def purge_expired(self, now=None):
        now = now if now is not None else _now()
        removed = []
        for token, session in list(self.sessions.items()):
            if session["expires_at"] <= now:
                removed.append(token)
                del self.sessions[token]
        return removed
''',
        '''from src.session_store import SessionStore

def test_stores_are_independent():
    a = SessionStore()
    b = SessionStore()
    a.create("tok-a")
    a.create("tok-b")
    b.create("tok-c")
    assert a.get("tok-c") is None
    assert b.get("tok-a") is None
    assert len(b.sessions) == 1

def test_get_valid_session():
    store = SessionStore()
    store.create("tok", ttl=100)
    assert store.get("tok", now=50) is not None

def test_get_expired_session_returns_none():
    store = SessionStore()
    store.sessions["old"] = {"expires_at": 10, "data": {}}
    assert store.get("old", now=20) is None

def test_purge_expired_removes_only_expired():
    store = SessionStore()
    store.sessions["dead"] = {"expires_at": 5, "data": {}}
    store.sessions["alive"] = {"expires_at": 500, "data": {}}
    removed = store.purge_expired(now=100)
    assert removed == ["dead"]
    assert "alive" in store.sessions
    assert "dead" not in store.sessions

def test_purge_empty_returns_empty():
    assert SessionStore().purge_expired(now=1) == []
''',
        '''from src.session_store import SessionStore

def test_create_returns_session():
    store = SessionStore()
    s = store.create("t1")
    assert "expires_at" in s
''',
        ["instances share one dict", "expired sessions still returned", "purge is a no-op"],
        ["independent state", "expiry enforced", "purge removes exactly expired"],
    ),
    _t(
        "task_019", "task_019_data_transform", "src/data_transform.py",
        "data_transformation", "medium",
        "Bug: group_by() loses elements, flatten() drops nested empty lists, and dedupe() keeps the wrong occurrence",
        "## Bug Report\n**File:** `src/data_transform.py`\n\n`group_by(items, key)` only keeps the "
        "last element per key because it overwrites instead of appending. `flatten()` skips empty "
        "nested lists entirely (they should vanish but deeper nesting is mishandled). `dedupe()` "
        "keeps the LAST occurrence of duplicates instead of the first.\n"
        "### Expected\n- group_by appends\n- flatten handles arbitrary nesting\n- dedupe keeps first occurrence order",
        '''def group_by(items: list, key) -> dict:
    grouped = {}
    for item in items:
        # BUG: overwrites instead of appending
        grouped[key(item)] = item
    return grouped

def flatten(nested: list) -> list:
    out = []
    for element in nested:
        if isinstance(element, list):
            # BUG: only flattens one level of nesting
            if element:
                out.extend(element)
        else:
            out.append(element)
    return out

def dedupe(items: list) -> list:
    # BUG: keeps last occurrence
    seen = {}
    for item in items:
        seen[repr(item)] = item
    return list(seen.values())
''',
        '''def group_by(items: list, key) -> dict:
    grouped = {}
    for item in items:
        grouped.setdefault(key(item), []).append(item)
    return grouped

def flatten(nested: list) -> list:
    out = []
    for element in nested:
        if isinstance(element, list):
            out.extend(flatten(element))
        else:
            out.append(element)
    return out

def dedupe(items: list) -> list:
    seen = set()
    out = []
    for item in items:
        marker = repr(item)
        if marker not in seen:
            seen.add(marker)
            out.append(item)
    return out
''',
        '''from src.data_transform import group_by, flatten, dedupe

def test_group_by_appends_all():
    rows = [{"t": "a", "v": 1}, {"t": "b", "v": 2}, {"t": "a", "v": 3}]
    grouped = group_by(rows, lambda r: r["t"])
    assert grouped["a"] == [{"t": "a", "v": 1}, {"t": "a", "v": 3}]
    assert grouped["b"] == [{"t": "b", "v": 2}]

def test_group_by_empty():
    assert group_by([], lambda x: x) == {}

def test_flatten_deep_nesting():
    assert flatten([1, [2, [3, [4]], 5]]) == [1, 2, 3, 4, 5]

def test_flatten_empty_lists():
    assert flatten([[], [1, []], 2]) == [1, 2]
    assert flatten([]) == []

def test_dedupe_keeps_first():
    assert dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]

def test_dedupe_preserves_order():
    assert dedupe(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]
''',
        '''from src.data_transform import flatten

def test_flatten_simple():
    assert flatten([1, [2, 3]]) == [1, 2, 3]
''',
        ["group_by keeps only last element per key", "single-level flatten only", "dedupe keeps last occurrence"],
        ["group_by appends", "recursive flatten", "first-occurrence dedupe"],
    ),
    _t(
        "task_020", "task_020_rate_limiter", "src/rate_limiter.py",
        "regression_style", "hard",
        "Bug: RateLimiter.allow_request() counts window boundaries wrongly and blocks legitimate traffic",
        "## Bug Report\n**File:** `src/rate_limiter.py`\n\nThe sliding-window limiter counts ALL "
        "timestamps ever recorded instead of only those within the window, so after the first burst "
        "every later request is denied forever. A regression introduced in v1.2.\n"
        "### Expected\n- at most `max_requests` within any `window_sec`\n- old timestamps expire and "
        "no longer count",
        '''class RateLimiter:
    def __init__(self, max_requests: int, window_sec: float):
        self.max_requests = max_requests
        self.window_sec = window_sec
        self._hits = []

    def allow_request(self, now: float) -> bool:
        # BUG: never prunes timestamps outside the window
        if len(self._hits) >= self.max_requests:
            return False
        self._hits.append(now)
        return True

    def hits_in_window(self, now: float) -> int:
        return len(self._hits)
''',
        '''class RateLimiter:
    def __init__(self, max_requests: int, window_sec: float):
        self.max_requests = max_requests
        self.window_sec = window_sec
        self._hits = []

    def allow_request(self, now: float) -> bool:
        self._prune(now)
        if len(self._hits) >= self.max_requests:
            return False
        self._hits.append(now)
        return True

    def _prune(self, now: float):
        cutoff = now - self.window_sec
        self._hits = [t for t in self._hits if t > cutoff]

    def hits_in_window(self, now: float) -> int:
        self._prune(now)
        return len(self._hits)
''',
        '''from src.rate_limiter import RateLimiter

def test_allows_up_to_limit():
    rl = RateLimiter(3, window_sec=10)
    assert rl.allow_request(1.0) is True
    assert rl.allow_request(2.0) is True
    assert rl.allow_request(3.0) is True

def test_blocks_beyond_limit():
    rl = RateLimiter(2, window_sec=10)
    rl.allow_request(1.0)
    rl.allow_request(2.0)
    assert rl.allow_request(3.0) is False

def test_window_expiry_frees_capacity():
    rl = RateLimiter(2, window_sec=5)
    assert rl.allow_request(1.0) is True
    assert rl.allow_request(2.0) is True
    assert rl.allow_request(6.5) is True
    assert rl.allow_request(7.0) is True

def test_old_hits_do_not_accumulate_forever():
    rl = RateLimiter(3, window_sec=4)
    for t in (0.5, 1.0, 1.5):
        rl.allow_request(t)
    assert rl.allow_request(10.0) is True
    assert rl.allow_request(10.5) is True
    assert rl.allow_request(11.0) is True
    assert rl.allow_request(11.5) is False

def test_hits_in_window_counts_correctly():
    rl = RateLimiter(5, window_sec=10)
    rl.allow_request(1.0)
    rl.allow_request(8.0)
    assert rl.hits_in_window(12.0) == 1
''',
        '''from src.rate_limiter import RateLimiter

def test_construction():
    rl = RateLimiter(4, window_sec=60)
    assert rl.max_requests == 4
''',
        ["old timestamps counted forever -> permanent lockout"],
        ["sliding window prunes expired hits"],
    ),
    _t(
        "task_021", "task_021_ledger", "src/ledger.py",
        "exception_handling", "hard",
        "Bug: Ledger.commit_batch() leaves entries half-applied when one transfer fails (no rollback)",
        "## Bug Report\n**File:** `src/ledger.py`\n\n`commit_batch()` applies transfers one at a "
        "time; if a later transfer fails (e.g. insufficient funds) earlier ones stay applied. "
        "The batch must be atomic: either all transfers apply or none.\n"
        "### Expected\n- any failing transfer rolls back the whole batch and re-raises ValueError\n"
        "- `balance()` reflects only fully-applied batches",
        '''class Ledger:
    def __init__(self):
        self.balances = {}

    def open_account(self, name: str, amount: float = 0.0):
        if name in self.balances:
            raise ValueError("account exists")
        self.balances[name] = amount
        return amount

    def balance(self, name: str) -> float:
        return self.balances.get(name, 0.0)

    def _apply(self, sender: str, receiver: str, amount: float):
        if self.balances.get(sender, 0.0) < amount:
            raise ValueError("insufficient funds")
        self.balances[sender] = self.balances.get(sender, 0.0) - amount
        self.balances[receiver] = self.balances.get(receiver, 0.0) + amount

    def commit_batch(self, transfers: list):
        # BUG: no rollback -> partial application
        for sender, receiver, amount in transfers:
            self._apply(sender, receiver, amount)
        return len(transfers)
''',
        '''class Ledger:
    def __init__(self):
        self.balances = {}

    def open_account(self, name: str, amount: float = 0.0):
        if name in self.balances:
            raise ValueError("account exists")
        self.balances[name] = amount
        return amount

    def balance(self, name: str) -> float:
        return self.balances.get(name, 0.0)

    def _apply(self, sender: str, receiver: str, amount: float):
        if self.balances.get(sender, 0.0) < amount:
            raise ValueError("insufficient funds")
        self.balances[sender] = self.balances.get(sender, 0.0) - amount
        self.balances[receiver] = self.balances.get(receiver, 0.0) + amount

    def commit_batch(self, transfers: list):
        snapshot = dict(self.balances)
        try:
            for sender, receiver, amount in transfers:
                self._apply(sender, receiver, amount)
        except ValueError:
            self.balances = snapshot
            raise
        return len(transfers)
''',
        '''import pytest
from src.ledger import Ledger

def test_batch_all_succeed():
    led = Ledger()
    led.open_account("a", 100)
    led.open_account("b", 0)
    n = led.commit_batch([("a", "b", 30), ("b", "a", 10)])
    assert n == 2
    assert led.balance("a") == 80
    assert led.balance("b") == 20

def test_batch_is_atomic_on_failure():
    led = Ledger()
    led.open_account("a", 100)
    led.open_account("b", 0)
    led.open_account("c", 0)
    with pytest.raises(ValueError):
        led.commit_batch([("a", "b", 60), ("a", "c", 60)])
    assert led.balance("a") == 100
    assert led.balance("b") == 0
    assert led.balance("c") == 0

def test_single_transfer_rolls_back():
    led = Ledger()
    led.open_account("x", 10)
    with pytest.raises(ValueError):
        led.commit_batch([("x", "y", 50)])
    assert led.balance("x") == 10

def test_open_account_duplicate_raises():
    led = Ledger()
    led.open_account("d", 5)
    with pytest.raises(ValueError):
        led.open_account("d", 5)
''',
        '''from src.ledger import Ledger

def test_open_account():
    led = Ledger()
    led.open_account("z", 25)
    assert led.balance("z") == 25
''',
        ["failed batch leaves earlier transfers applied"],
        ["atomic batch with rollback", "successful batches apply fully"],
    ),
    _t(
        "task_022", "task_022_feature_flags", "src/feature_flags.py",
        "configuration", "medium",
        "Bug: FeatureFlags env override precedence is inverted and unknown flags crash instead of warning",
        "## Bug Report\n**File:** `src/feature_flags.py`\n\n`FeatureFlags` resolves flag values with "
        "inverted precedence: the defaults dict overrides both the environment and the user-supplied "
        "overrides. Also `is_enabled('unknown')` raises KeyError instead of returning the default.\n"
        "### Expected\n- precedence: user overrides > environment > defaults\n- unknown flag -> "
        "return `default_for_unknown` (False unless specified)",
        '''import os

DEFAULTS = {"dark_mode": False, "beta_api": False, "telemetry": True}

class FeatureFlags:
    def __init__(self, overrides=None, environ=None):
        self.overrides = overrides or {}
        self.environ = environ if environ is not None else dict(os.environ)

    def is_enabled(self, name: str, default_for_unknown: bool = False) -> bool:
        # BUG: defaults checked first and returned immediately
        if name in DEFAULTS:
            return DEFAULTS[name]
        if name in self.overrides:
            return bool(self.overrides[name])
        env_val = self.environ.get(f"FLAG_{name.upper()}")
        if env_val is not None:
            return env_val.strip().lower() in ("1", "true", "yes", "on")
        return default_for_unknown

    def all_flags(self) -> dict:
        merged = dict(DEFAULTS)
        merged.update(self.overrides)
        return merged
''',
        '''import os

DEFAULTS = {"dark_mode": False, "beta_api": False, "telemetry": True}

class FeatureFlags:
    def __init__(self, overrides=None, environ=None):
        self.overrides = overrides or {}
        self.environ = environ if environ is not None else dict(os.environ)

    def is_enabled(self, name: str, default_for_unknown: bool = False) -> bool:
        if name in self.overrides:
            return bool(self.overrides[name])
        env_val = self.environ.get(f"FLAG_{name.upper()}")
        if env_val is not None:
            return env_val.strip().lower() in ("1", "true", "yes", "on")
        if name in DEFAULTS:
            return DEFAULTS[name]
        return default_for_unknown

    def all_flags(self) -> dict:
        merged = dict(DEFAULTS)
        for key, value in self.environ.items():
            if key.startswith("FLAG_") and key[5:].lower() in merged:
                merged[key[5:].lower()] = value.strip().lower() in ("1", "true", "yes", "on")
        merged.update(self.overrides)
        return merged
''',
        '''from src.feature_flags import FeatureFlags

def test_override_beats_everything():
    ff = FeatureFlags(
        overrides={"telemetry": False},
        environ={"FLAG_TELEMETRY": "true"},
    )
    assert ff.is_enabled("telemetry") is False

def test_env_beats_defaults():
    ff = FeatureFlags(environ={"FLAG_DARK_MODE": "yes"})
    assert ff.is_enabled("dark_mode") is True

def test_defaults_used_when_no_env():
    ff = FeatureFlags(environ={})
    assert ff.is_enabled("dark_mode") is False
    assert ff.is_enabled("telemetry") is True

def test_env_false_disables_flag():
    ff = FeatureFlags(environ={"FLAG_TELEMETRY": "0"})
    assert ff.is_enabled("telemetry") is False

def test_unknown_flag_returns_default():
    ff = FeatureFlags(environ={})
    assert ff.is_enabled("nope") is False
    assert ff.is_enabled("nope", default_for_unknown=True) is True

def test_all_flags_merges_layers():
    ff = FeatureFlags(
        overrides={"beta_api": True},
        environ={"FLAG_DARK_MODE": "true"},
    )
    flags = ff.all_flags()
    assert flags["beta_api"] is True
    assert flags["dark_mode"] is True
    assert flags["telemetry"] is True
''',
        '''from src.feature_flags import FeatureFlags

def test_construction():
    assert FeatureFlags(environ={}).all_flags()["telemetry"] is True
''',
        ["defaults override env/overrides", "unknown flag raises KeyError"],
        ["correct precedence chain", "unknown flags return default_for_unknown"],
    ),
]