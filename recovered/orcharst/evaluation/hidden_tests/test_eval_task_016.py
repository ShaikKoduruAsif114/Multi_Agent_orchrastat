"""
evaluation/hidden_tests/test_eval_task_016.py

INDEPENDENT EVALUATION TESTS — Task 016 (file_utils)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_016.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/file_utils.py when
EVAL_FIX_MODULE=src.file_utils is set, so `from src.file_utils import ...`
resolves against the proposed fix.
"""
import pytest
from src.file_utils import safe_read, count_lines, append_file, file_size

def test_safe_read_existing(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello", encoding="utf-8")
    assert safe_read(str(p)) == "hello"

def test_safe_read_missing_returns_empty(tmp_path):
    assert safe_read(str(tmp_path / "missing.txt")) == ""

def test_count_lines_with_trailing_newline(tmp_path):
    p = tmp_path / "b.txt"
    p.write_text("one\ntwo\n", encoding="utf-8")
    assert count_lines(str(p)) == 2

def test_count_lines_without_trailing_newline(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("one\ntwo", encoding="utf-8")
    assert count_lines(str(p)) == 2

def test_count_lines_empty(tmp_path):
    p = tmp_path / "d.txt"
    p.write_text("", encoding="utf-8")
    assert count_lines(str(p)) == 0

def test_append_creates_missing_dirs(tmp_path):
    target = tmp_path / "sub" / "dir" / "log.txt"
    append_file(str(target), "entry\n")
    append_file(str(target), "entry2\n")
    assert target.read_text(encoding="utf-8") == "entry\nentry2\n"

def test_file_size(tmp_path):
    p = tmp_path / "e.txt"
    p.write_text("12345", encoding="utf-8")
    assert file_size(str(p)) == 5
