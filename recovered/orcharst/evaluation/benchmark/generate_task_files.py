"""
evaluation/benchmark/generate_task_files.py

Generates, from the task specs:
  1. evaluation/hidden_tests/test_eval_task_NNN.py   (NNN = 006..030)
  2. evaluation/benchmark/task_NNN_<name>.json       (task files for run_benchmark.py)

The hidden test files wrap spec["hidden_tests"] with the standard evaluation
header; the JSON files mirror the task_001..005 shape exactly.

Usage:
    python evaluation/benchmark/generate_task_files.py            # generate all
    python evaluation/benchmark/generate_task_files.py --task task_006
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BENCH_DIR = Path(__file__).parent
PROJECT_ROOT = BENCH_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.benchmark.spec_loader import load_all_specs, validate_spec

HIDDEN_TESTS_DIR = PROJECT_ROOT / "evaluation" / "hidden_tests"

HEADER = '''"""
evaluation/hidden_tests/test_eval_task_{nnn}.py

INDEPENDENT EVALUATION TESTS — Task {nnn} ({module_name}.py)

These tests are written by a human evaluator BEFORE running the benchmark.
They are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for {task_id}.

The agent's proposed fix is materialized under its real package path
(src/{module_name}.py) by evaluation/hidden_tests/conftest.py from the
EVAL_FIX_CODE / EVAL_FIX_MODULE environment variables.
"""
'''

FILE_TEMPLATE = HEADER + '''
# ---------------------------------------------------------------------------
# Hidden test suite for {task_id}
# ---------------------------------------------------------------------------
{hidden_tests}
'''


def task_short_name(spec: dict) -> str:
    """task_006_inventory_manager -> inventory_manager"""
    parts = spec["repository"].rsplit("/", 1)[-1].split("_", 2)
    return parts[2] if len(parts) > 2 else spec["task_id"]


def generate_hidden_test_file(spec: dict, overwrite: bool = False) -> Path:
    nnn = spec["task_id"].split("_")[1]
    module_name = spec["gold_file"].replace("\\", "/").split("/")[-1].removesuffix(".py")
    out_path = HIDDEN_TESTS_DIR / f"test_eval_task_{nnn}.py"
    if out_path.exists() and not overwrite:
        return out_path
    content = FILE_TEMPLATE.format(
        nnn=nnn, task_id=spec["task_id"], module_name=module_name,
        hidden_tests=spec["hidden_tests"].rstrip() + "\n",
    )
    out_path.write_text(content, encoding="utf-8")
    return out_path


def generate_task_json(spec: dict, overwrite: bool = False) -> Path:
    nnn = spec["task_id"].split("_")[1]
    short = task_short_name(spec)
    out_path = BENCH_DIR / f"task_{nnn}_{short}.json"
    if out_path.exists() and not overwrite:
        return out_path
    task = {
        "task_id": spec["task_id"],
        "repository": spec["repository"],
        "issue_id": int(nnn),
        "issue_title": spec["issue_title"],
        "issue_body": spec["issue_body"],
        "gold_file": spec["gold_file"],
        "gold_file_alternatives": [],
        "buggy_behaviors": spec["buggy_behaviors"],
        "expected_behaviors": spec["expected_behaviors"],
        "hidden_test_file": f"evaluation/hidden_tests/test_eval_task_{nnn}.py",
        "metadata": {
            "source": f"Synthetic benchmark spec ({spec['repository']})",
            "selection_reason": (
                "Deterministic pure-Python bug with verified hidden test suite "
                "(fails on buggy, passes on fixed source)."
            ),
            "language": "Python",
            "dependencies": [],
            "license": "Project-internal test data",
            "difficulty": spec["difficulty"],
            "category": spec["category"],
            "notes": f"All bugs are in a single file: {spec['gold_file']}.",
        },
    }
    out_path.write_text(json.dumps(task, indent=2), encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate hidden test files and task JSONs from specs")
    parser.add_argument("--task", default=None, help="Generate only this task_id")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate existing files")
    args = parser.parse_args()

    HIDDEN_TESTS_DIR.mkdir(parents=True, exist_ok=True)
    specs = load_all_specs()
    # Tasks 001-005 are hand-crafted (real GitHub repos, bespoke JSON shape).
    # This generator only materializes the synthetic specs 006-030.
    specs = [s for s in specs if s["task_id"] >= "task_006"]
    if args.task:
        specs = [s for s in specs if s["task_id"] == args.task]
        if not specs:
            print(f"[ERROR] Unknown or hand-crafted task_id: {args.task}")
            return 1

    for spec in specs:
        validate_spec(spec)
        test_path = generate_hidden_test_file(spec, overwrite=args.overwrite)
        json_path = generate_task_json(spec, overwrite=args.overwrite)
        print(f"[OK] {spec['task_id']}: {test_path.name}, {json_path.name}")

    print(f"\nGenerated files for {len(specs)} task(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
