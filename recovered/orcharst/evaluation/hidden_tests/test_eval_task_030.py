"""
evaluation/hidden_tests/test_eval_task_030.py

INDEPENDENT EVALUATION TESTS — Task 030 (ini_parser)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_030.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/ini_parser.py when
EVAL_FIX_MODULE=src.ini_parser is set, so `from src.ini_parser import ...`
resolves against the proposed fix.
"""
from src.ini_parser import parse_ini, get_value

def test_sections_without_brackets():
    config = parse_ini("[core]\nname = app\n")
    assert "core" in config
    assert "[core]" not in config
    assert config["core"]["name"] == "app"

def test_inline_comment_stripped():
    config = parse_ini("[core]\nport = 8080 ; the port\n")
    assert config["core"]["port"] == "8080"

def test_hash_comment_stripped():
    config = parse_ini("[core]\nmode = fast # speed\n")
    assert config["core"]["mode"] == "fast"

def test_duplicate_keys_last_wins():
    config = parse_ini("[core]\ntimeout = 5\ntimeout = 30\n")
    assert config["core"]["timeout"] == "30"

def test_comment_only_lines_ignored():
    config = parse_ini("; a comment\n# another\n[net]\nssl = on\n")
    assert config == {"net": {"ssl": "on"}}

def test_get_value_helper():
    config = parse_ini("[db]\nhost = local\n")
    assert get_value(config, "db", "host") == "local"
    assert get_value(config, "db", "missing", "fallback") == "fallback"
    assert get_value(config, "no_section", "k") is None
