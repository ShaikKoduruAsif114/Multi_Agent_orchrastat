"""
evaluation/benchmark/build_fixture_repos.py

Materializes every benchmark task spec into a self-contained local fixture
"repository" (issues/<n>.json + buggy src/<name>.py). The agents already
prefer these local fixtures over network calls via
agent.tools.set_repository_resolver(...), so a task is fully runnable
offline once its fixture repo exists.

Usage:
    python evaluation/benchmark/build_fixture_repos.py            # build all 30
    python evaluation/benchmark/build_fixture_repos.py --task task_006
    python evaluation/benchmark/build_fixture_repos.py --out-dir <dir> --clean
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

BENCH_DIR = Path(__file__).parent
PROJECT_ROOT = BENCH_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.benchmark.spec_loader import load_all_specs, validate_spec

DEFAULT_OUT = BENCH_DIR / "fixture_repos"


def build_one(spec: dict, out_root: Path) -> Path:
    validate_spec(spec)
    repo_dir = out_root / spec["task_id"]
    repo_dir.mkdir(parents=True, exist_ok=True)

    # --- src/<name>.py : the buggy module the agent must fix ---------------
    src_dir = repo_dir / "src"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "__init__.py").write_text("", encoding="utf-8")
    (repo_dir / spec["gold_file"]).write_text(spec["buggy"], encoding="utf-8")

    # --- issues/<n>.json : local issue readable via local_get_issue --------
    issue_number = int(spec["task_id"].split("_")[1])
    issue_payload = {
        "number": issue_number,
        "title": spec["issue_title"],
        "body": spec["issue_body"],
        "repository": spec["repository"],
        "labels": ["bug", spec["category"], spec["difficulty"]],
    }
    issues_dir = repo_dir / "issues"
    issues_dir.mkdir(exist_ok=True)
    (issues_dir / f"{issue_number}.json").write_text(
        json.dumps(issue_payload, indent=2), encoding="utf-8"
    )

    # --- README.md : a tiny repo description for context -------------------
    (repo_dir / "README.md").write_text(
        f"# {spec['task_id']}\n\n{spec['issue_title']}\n\n"
        f"Category: {spec['category']} | Difficulty: {spec['difficulty']}\n",
        encoding="utf-8",
    )
    return repo_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local fixture repos for benchmark tasks")
    parser.add_argument("--task", default=None, help="Build only this task_id (e.g. task_006)")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT), help="Output root directory")
    parser.add_argument("--clean", action="store_true", help="Delete output dir first")
    args = parser.parse_args()

    out_root = Path(args.out_dir)
    if args.clean and out_root.exists():
        shutil.rmtree(out_root)

    specs = load_all_specs()
    if args.task:
        specs = [s for s in specs if s["task_id"] == args.task]
        if not specs:
            print(f"[ERROR] Unknown task_id: {args.task}")
            return 1

    for spec in specs:
        repo_dir = build_one(spec, out_root)
        print(f"[OK] {spec['task_id']} -> {repo_dir}")

    built = len(specs)
    print(f"\nBuilt {built} fixture repo(s) under {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
