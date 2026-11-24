"""
evaluation/hidden_tests/test_eval_task_027.py

INDEPENDENT EVALUATION TESTS — Task 027 (path_resolver)

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_027.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/path_resolver.py when
EVAL_FIX_MODULE=src.path_resolver is set, so `from src.path_resolver import ...`
resolves against the proposed fix.
"""
import pytest
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
    assert resolve_path("C:\\base", "") == "C:\\base"

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
