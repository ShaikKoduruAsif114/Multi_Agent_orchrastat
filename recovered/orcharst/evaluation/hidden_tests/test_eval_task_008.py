"""
evaluation/hidden_tests/test_eval_task_008.py

INDEPENDENT EVALUATION TESTS — Task 008 (csv_parser)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_008.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/csv_parser.py when
EVAL_FIX_MODULE=src.csv_parser is set, so `from src.csv_parser import ...`
resolves against the proposed fix.
"""
from src.csv_parser import parse_csv, parse_int_list, to_csv_row

def test_parse_csv_quoted_field_with_comma():
    data = 'name,notes\n"Smith, John","hello, world"'
    rows = parse_csv(data)
    assert rows[1][0] == "Smith, John"
    assert rows[1][1] == "hello, world"
    assert len(rows[1]) == 2

def test_parse_csv_basic():
    rows = parse_csv("a,b\n1,2")
    assert rows[0] == ["a", "b"]
    assert rows[1] == ["1", "2"]

def test_parse_csv_skips_blank_lines():
    rows = parse_csv("a,b\n\n1,2\n")
    assert len(rows) == 2

def test_parse_int_list_with_whitespace():
    assert parse_int_list("1, 2, 3") == [1, 2, 3]
    assert parse_int_list("5") == [5]

def test_to_csv_row_quotes_comma_field():
    assert to_csv_row(["a", "b,c"]) == 'a,"b,c"'
