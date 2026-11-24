"""
evaluation/hidden_tests/test_eval_task_017.py

INDEPENDENT EVALUATION TESTS — Task 017 (api_client)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_017.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/api_client.py when
EVAL_FIX_MODULE=src.api_client is set, so `from src.api_client import ...`
resolves against the proposed fix.
"""
from src.api_client import ApiClient

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
