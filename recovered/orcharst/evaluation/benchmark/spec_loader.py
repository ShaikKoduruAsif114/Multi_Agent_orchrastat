"""
evaluation/benchmark/spec_loader.py

Loads the 30 benchmark task specs (see tasks/*.py) and validates their shape.
The full benchmark is described by SPECS (list of dicts), merged from
specs_original.py (the 5 seed tasks) and specs_new_*.py (25 new tasks).
"""
from __future__ import annotations

import os
from pathlib import Path

_SPEC_DIR = Path(__file__).parent


def load_all_specs() -> list:
    from evaluation.benchmark.specs_original import ORIGINAL_TASKS
    from evaluation.benchmark.specs_new_1 import NEW_TASKS_1
    from evaluation.benchmark.specs_new_2 import NEW_TASKS_2
    from evaluation.benchmark.specs_new_3 import NEW_TASKS_3

    specs = ORIGINAL_TASKS + NEW_TASKS_1 + NEW_TASKS_2 + NEW_TASKS_3
    ids = [s["task_id"] for s in specs]
    assert len(ids) == len(set(ids)), f"Duplicate task_ids: {set(ids)}"
    assert len(specs) >= 30, f"Expected >=30 tasks, got {len(specs)}"
    return specs


REQUIRED_FIELDS = [
    "task_id", "repository", "gold_file", "issue_title", "issue_body",
    "category", "difficulty", "buggy", "fixed", "hidden_tests", "public_tests",
    "buggy_behaviors", "expected_behaviors",
]


def validate_spec(spec: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if f not in spec]
    if missing:
        raise ValueError(f"{spec.get('task_id','?')} missing fields: {missing}")
    for key in ("buggy", "fixed", "hidden_tests", "public_tests"):
        ast_check(spec[key], spec["task_id"], key)


def ast_check(source: str, task_id: str, field: str) -> None:
    import ast
    try:
        ast.parse(source)
    except SyntaxError as e:
        raise SyntaxError(f"{task_id} [{field}] has a SyntaxError: {e}") from e