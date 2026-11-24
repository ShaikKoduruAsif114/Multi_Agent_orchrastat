"""
evaluation/benchmark/validate_harness.py

End-to-end validation of the PRODUCTION evaluation harness:
for every synthetic task (006-030), run the generated
evaluation/hidden_tests/test_eval_task_NNN.py via pytest with the conftest
EVAL_FIX_PATH / EVAL_FIX_MODULE injection.

Acceptance: fixed source -> all pass (rc 0); buggy source -> failures (rc != 0).

Usage:
    python evaluation/benchmark/validate_harness.py [--task task_015]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.benchmark.spec_loader import load_all_specs


def run_one(spec: dict) -> tuple[int, int]:
    nnn = spec["task_id"].split("_")[1]
    module = spec["gold_file"].replace("\\", "/").removesuffix(".py").replace("/", ".")
    test_file = PROJECT_ROOT / "evaluation" / "hidden_tests" / f"test_eval_task_{nnn}.py"

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for key in ("fixed", "buggy"):
            src_file = Path(tmp) / f"{key}.py"
            src_file.write_text(spec[key], encoding="utf-8")
            env = os.environ.copy()
            env["EVAL_FIX_PATH"] = str(src_file)
            env["EVAL_FIX_MODULE"] = module
            env.pop("EVAL_FIX_CODE", None)
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "-q", "--no-header",
                 "-p", "no:cacheprovider", "--disable-warnings"],
                capture_output=True, text=True, cwd=str(PROJECT_ROOT),
                env=env, timeout=120,
            )
            results.append(proc.returncode)
    fixed_rc, buggy_rc = results
    return fixed_rc, buggy_rc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default=None)
    args = parser.parse_args()

    specs = [s for s in load_all_specs() if s["task_id"] >= "task_006"]
    if args.task:
        specs = [s for s in specs if s["task_id"] == args.task]

    failures = []
    for spec in specs:
        fixed_rc, buggy_rc = run_one(spec)
        ok = fixed_rc == 0 and buggy_rc != 0
        print(f"{'OK ' if ok else 'BAD'} {spec['task_id']}: fixed_rc={fixed_rc} buggy_rc={buggy_rc}")
        if not ok:
            failures.append(spec["task_id"])

    print(f"\n{len(specs) - len(failures)}/{len(specs)} tasks validated through production harness")
    if failures:
        print("FAILURES:", failures)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
