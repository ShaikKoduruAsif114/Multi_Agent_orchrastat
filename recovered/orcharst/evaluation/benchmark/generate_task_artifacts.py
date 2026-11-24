"""
evaluation/benchmark/generate_task_artifacts.py

Generates the benchmark runner artifacts for tasks 006-030 from the
validated task specs:

  1. evaluation/hidden_tests/test_eval_task_<NN>.py  (hidden test file,
     verbatim from spec["hidden_tests"], never shown to the agent)
  2. evaluation/benchmark/task_<NN>_<name>.json       (task card consumed by
     evaluation/run_benchmark.py, same schema as the original 5 task JSONs)

Idempotent: re-running overwrites the generated files deterministically.
The original task_001..task_005 artifacts are hand-authored and NOT touched.

Usage:
    python -m evaluation.benchmark.generate_task_artifacts
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from evaluation.benchmark.spec_loader import load_all_specs  # noqa: E402

HIDDEN_TESTS_DIR = REPO_ROOT / "evaluation" / "hidden_tests"
BENCHMARK_DIR = REPO_ROOT / "evaluation" / "benchmark"

# Difficulty ordering used for the metadata notes
CATEGORY_LABELS = {
    "off_by_one": "Off-by-one / boundary logic",
    "state_management": "State & identity management",
    "parsing": "Input parsing",
    "arithmetic_logic": "Arithmetic & logic",
    "file_path": "File & path handling",
    "api_misuse": "API / argument misuse",
    "data_transformation": "Data transformation",
    "exception_handling": "Exception & transaction handling",
    "regression_style": "Regression (previously correct behavior broke)",
    "configuration": "Configuration & precedence",
}

TEST_FILE_HEADER = '''"""
evaluation/hidden_tests/test_eval_task_{nn}.py

INDEPENDENT EVALUATION TESTS — Task {nn} ({module})

AUTO-GENERATED from evaluation/benchmark/specs (do not edit by hand;
regenerate with: python -m evaluation.benchmark.generate_task_artifacts).

These tests are NEVER shown to the agent or used in any LLM prompt.
They represent the authoritative evaluation signal for task_{nn}.

The agent's proposed fix is injected via conftest.py: at pytest start the
fix source (EVAL_FIX_CODE) is materialized as src/{module_name}.py when
EVAL_FIX_MODULE=src.{module_name} is set, so `from src.{module_name} import ...`
resolves against the proposed fix.
"""
'''


def main() -> None:
    specs = load_all_specs()
    generated_tests = 0
    generated_tasks = 0

    for spec in specs:
        task_id = spec["task_id"]
        nn = task_id.split("_")[1]
        module_name = Path(spec["gold_file"]).stem  # e.g. pagination
        repo_name = Path(spec["repository"]).name

        # ---- 1. hidden test file -------------------------------------------
        # Original 5 tasks keep their hand-written hidden test files.
        test_path = HIDDEN_TESTS_DIR / f"test_eval_task_{nn}.py"
        if not test_path.exists() or nn >= "006":
            header = TEST_FILE_HEADER.format(nn=nn, module=module_name,
                                             module_name=module_name)
            test_path.write_text(header + spec["hidden_tests"], encoding="utf-8")
            generated_tests += 1

        # ---- 2. task JSON ---------------------------------------------------
        # Original 5 tasks keep their hand-authored task JSONs.
        if nn < "006":
            continue
        import re
        short_name = re.sub(r"^task_\d+_", "", repo_name)
        json_path = BENCHMARK_DIR / f"task_{nn}_{short_name}.json"
        if not json_path.exists():
            category = spec["category"]
            task_card = {
                "task_id": task_id,
                "repository": spec["repository"],
                "issue_id": 1,
                "issue_title": spec["issue_title"],
                "issue_body": spec["issue_body"],
                "gold_file": spec["gold_file"],
                "gold_file_alternatives": [],
                "buggy_behaviors": spec["buggy_behaviors"],
                "expected_behaviors": spec["expected_behaviors"],
                "hidden_test_file": f"evaluation/hidden_tests/test_eval_task_{nn}.py",
                "metadata": {
                    "source": "Synthetic single-module fixture repo "
                              f"({repo_name}) defined in evaluation/benchmark/specs",
                    "selection_reason": (
                        f"{CATEGORY_LABELS.get(category, category)} bug; "
                        "pure Python stdlib; verified hidden tests "
                        "(fail on buggy, pass on fixed)"
                    ),
                    "language": "Python",
                    "dependencies": [],
                    "license": "Project-internal test data",
                    "difficulty": spec["difficulty"],
                    "bug_count": len(spec["buggy_behaviors"]),
                    "notes": f"Agent must identify {spec['gold_file']}.",
                },
            }
            json_path.write_text(
                json.dumps(task_card, indent=2) + "\n", encoding="utf-8"
            )
            generated_tasks += 1

    print(f"Generated/refreshed {generated_tests} hidden test file(s)")
    print(f"Generated/refreshed {generated_tasks} task JSON file(s)")


if __name__ == "__main__":
    main()