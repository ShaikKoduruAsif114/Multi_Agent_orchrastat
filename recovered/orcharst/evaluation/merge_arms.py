"""
evaluation/merge_arms.py

Canonical V4 merge/evaluation command.

Takes the two independently completed V4 arm packages produced by
`run_benchmark.py --config evaluation/configs/benchmark_v4.yaml --v4-arm adaptive_multi_agent --evaluate`
and
`run_benchmark.py --config evaluation/configs/benchmark_v4.yaml --v4-arm baseline_b --evaluate`
and combines them into the canonical V4 comparison artifacts:

    task_ledger.json
    analysis.json
    paired_analysis.json

The merge command is fail-closed: it refuses to run unless both arm packages are
COMPLETE, each contains exactly task_001 through task_030 with no duplicates, the
config SHA, benchmark manifest SHA, provider/model, retry budget, and protocol
version all match across arms, and the two arms are exactly the canonical V4 pair.

The merged comparison uses the V4 pre-registered denominator rules exactly as
currently implemented in build_ledger.py / paired_analysis.py.

The only protocol change recorded by this merge is:

    "arms executed as independent validated packages because of outer execution-wrapper limits; no treatment/config/evaluation variable changed."
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import build_ledger as BL  # noqa: E402
import lifecycle as L  # noqa: E402
import paired_analysis as PA  # noqa: E402
import validate_ledger as VL  # noqa: E402
import verify_manifest as VM  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = REPO_ROOT / "evaluation" / "V4_PROTOCOL.md"
CONFIG_PATH = REPO_ROOT / "evaluation" / "configs" / "benchmark_v4.yaml"

SYS_A_EXPECTED = "adaptive_multi_agent"
SYS_B_EXPECTED = "baseline_b"


def _read_status(exp_dir: Path) -> dict:
    status_path = exp_dir / "experiment_status.json"
    if not status_path.exists():
        raise FileNotFoundError(str(status_path))
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(str(status_path)) from e


def _config_sha() -> str:
    return VM.sha256_file(CONFIG_PATH)


def _manifest_sha() -> str:
    return VM.sha256_file(VM.MANIFEST_PATH)


def _commit_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return ""


def _lifecycle_complete(exp_dir: Path, arm_system: str | None = None) -> tuple[bool, str]:
    status = _read_status(exp_dir)
    if status.get("status") != L.COMPLETE:
        return False, f"status={status.get('status')!r}, expected COMPLETE"
    if arm_system and status.get("arm_system") != arm_system:
        return False, f"arm_system={status.get('arm_system')!r}, expected {arm_system!r}"
    return True, ""


def _single_arm_30_tasks(exp_dir: Path, arm_system: str) -> tuple[bool, list[str]]:
    raw_dir = exp_dir / "raw"
    if not raw_dir.exists():
        return False, ["raw directory missing"]
    counts = L.raw_result_counts(raw_dir)
    issues: list[str] = []
    task_ids = list(counts.get(f"{arm_system}_task_ids") or [])
    dups = list(counts.get(f"{arm_system}_duplicates") or [])
    if dups:
        issues.append(f"{arm_system}: duplicate task IDs {dups}")
    other = SYS_B_EXPECTED if arm_system == SYS_A_EXPECTED else SYS_A_EXPECTED
    if counts.get(other, 0):
        issues.append(f"{arm_system}: unexpected {counts[other]} raw results for the non-executed arm")
    if sorted(task_ids) != L.TASK_IDS:
        missing = sorted(set(L.TASK_IDS) - set(task_ids))
        extra = sorted(set(task_ids) - set(L.TASK_IDS))
        issues.append(f"{arm_system}: task IDs incomplete; missing={missing} extra={extra}")
    return len(issues) == 0, issues


def _gate_artifact_checks(a_dir: Path, b_dir: Path) -> list[str]:
    errors: list[str] = []

    a_status = _read_status(a_dir)
    b_status = _read_status(b_dir)

    a_cfg = a_status.get("config_sha")
    b_cfg = b_status.get("config_sha")
    if not a_cfg or not b_cfg:
        errors.append("config_sha missing from one or both arm packages")
    elif a_cfg != b_cfg:
        errors.append(f"config_sha mismatch across arms: {a_cfg!r} vs {b_cfg!r}")

    a_man = a_status.get("benchmark_manifest_sha")
    b_man = b_status.get("benchmark_manifest_sha")
    if not a_man or not b_man:
        errors.append("benchmark_manifest_sha missing from one or both arm packages")
    elif a_man != b_man:
        errors.append(f"benchmark_manifest_sha mismatch across arms: {a_man!r} vs {b_man!r}")

    a_prov = a_status.get("provider")
    b_prov = b_status.get("provider")
    a_model = a_status.get("model")
    b_model = b_status.get("model")
    if a_prov != b_prov or not a_prov:
        errors.append(f"provider mismatch across arms: {a_prov!r} vs {b_prov!r}")
    if a_model != b_model or not a_model:
        errors.append(f"model mismatch across arms: {a_model!r} vs {b_model!r}")

    a_entries, b_entries = None, None
    try:
        a_ledger = json.loads((a_dir / "task_ledger.json").read_text(encoding="utf-8"))
        b_ledger = json.loads((b_dir / "task_ledger.json").read_text(encoding="utf-8"))
        a_entries = a_ledger.get("entries") or []
        b_entries = b_ledger.get("entries") or []
    except Exception as e:
        errors.append(f"unable to read arm ledgers: {e}")
        return errors

    a_budgets = sorted({str(e.get("retry_budget")) for e in a_entries if e.get("retry_budget") is not None})
    b_budgets = sorted({str(e.get("retry_budget")) for e in b_entries if e.get("retry_budget") is not None})
    if not a_budgets or not b_budgets:
        errors.append("retry budget not recorded in one or both arm ledgers")
    elif a_budgets != b_budgets:
        errors.append(f"retry_budget mismatch across arms: {a_budgets!r} vs {b_budgets!r}")

    a_proto = a_status.get("protocol_version")
    b_proto = b_status.get("protocol_version")
    if not a_proto or not b_proto:
        errors.append("protocol_version missing from one or both arm packages")
    elif a_proto != b_proto:
        errors.append(f"protocol_version mismatch across arms: {a_proto!r} vs {b_proto!r}")
    return errors


def _load_arm_ledger_entries(exp_dir: Path) -> list:
    ledger = json.loads((exp_dir / "task_ledger.json").read_text(encoding="utf-8"))
    return ledger.get("entries") or []


def merge_packages(adaptive_dir: Path, baseline_dir: Path, out_dir: Path) -> dict:
    merged_raw = out_dir / "raw"
    merged_raw.mkdir(parents=True, exist_ok=True)

    a_entries = _load_arm_ledger_entries(adaptive_dir)
    b_entries = _load_arm_ledger_entries(baseline_dir)
    entries = list(a_entries) + list(b_entries)

    manifest_report = VM.verify_manifest()
    paths, warnings = BL.build_package(
        "adaptive_v4_merged",
        raw_dir=merged_raw,
        out_dir=out_dir,
        skip_manifest_gate=False,
    )

    report = VL.validate_package(out_dir, expect_systems=L.ARMS, require_two_systems=True)
    paired = json.loads((out_dir / "paired_analysis.json").read_text(encoding="utf-8"))

    protocol_note = (
        "arms executed as independent validated packages because of outer execution-wrapper "
        "limits; no treatment/config/evaluation variable changed."
    )

    return {
        "out_dir": str(out_dir),
        "task_ledger": str(out_dir / "task_ledger.json"),
        "analysis": str(out_dir / "analysis.json"),
        "paired_analysis": str(out_dir / "paired_analysis.json"),
        "manifest_verified": manifest_report["verified"],
        "manifest_entries": manifest_report["manifest_entries"],
        "merged_entries": len(entries),
        "validation_ok": report["ok"],
        "validation_errors": report["errors"],
        "validation_warnings": report["warnings"],
        "paired_valid_N": paired.get("tiers", {}).get("valid", {}).get("N"),
        "paired_fatal_N": paired.get("tiers", {}).get("fatal", {}).get("N"),
        "protocol_note": protocol_note,
        "protocol_path": str(PROTOCOL_PATH),
        "protocol_version": "1.0.0 (frozen before the run)",
        "config_sha": _config_sha(),
        "benchmark_manifest_sha": _manifest_sha(),
        "code_commit_sha": _commit_sha(),
        "provider": "nara",
        "model": "laguna-s-2.1",
        "retry_budget": "2",
        "arms": list(L.ARMS),
    }


def validate_merge_inputs(adaptive_dir: Path, baseline_dir: Path) -> list[str]:
    errors: list[str] = []

    a_status = _read_status(adaptive_dir)
    b_status = _read_status(baseline_dir)

    for arm, exp_dir, status in ((SYS_A_EXPECTED, adaptive_dir, a_status), (SYS_B_EXPECTED, baseline_dir, b_status)):
        complete, reason = _lifecycle_complete(exp_dir, arm)
        if not complete:
            errors.append(f"{arm}: not COMPLETE ({reason})")
            return errors

    a_ok, a_issues = _single_arm_30_tasks(adaptive_dir, SYS_A_EXPECTED)
    if not a_ok:
        errors.append(f"{SYS_A_EXPECTED}: {a_issues[0]}")
        return errors
    b_ok, b_issues = _single_arm_30_tasks(baseline_dir, SYS_B_EXPECTED)
    if not b_ok:
        errors.append(f"{SYS_B_EXPECTED}: {b_issues[0]}")
        return errors

    errors.extend(_gate_artifact_checks(adaptive_dir, baseline_dir))

    a_systems = {e.get("system") for e in _load_arm_ledger_entries(adaptive_dir)}
    b_systems = {e.get("system") for e in _load_arm_ledger_entries(baseline_dir)}
    if a_systems != {SYS_A_EXPECTED}:
        errors.append(f"adaptive package systems unexpected: {sorted(a_systems)}")
    if b_systems != {SYS_B_EXPECTED}:
        errors.append(f"baseline package systems unexpected: {sorted(b_systems)}")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(
        description="V4 canonical arm merge/evaluation command. "
        "Takes two COMPLETE 30-task arm packages and produces the canonical "
        "task_ledger.json + analysis.json + paired_analysis.json comparison."
    )
    ap.add_argument("--adaptive", required=True, help="adaptive_multi_agent arm package directory")
    ap.add_argument("--baseline", required=True, help="baseline_b arm package directory")
    ap.add_argument("--out", required=True, help="output package directory for the merged comparison")
    ap.add_argument("--validate-only", action="store_true", help="only run the merge gate, do not write outputs")
    args = ap.parse_args()

    adaptive_dir = Path(args.adaptive).resolve()
    baseline_dir = Path(args.baseline).resolve()
    out_dir = Path(args.out).resolve()

    errors = validate_merge_inputs(adaptive_dir, baseline_dir)
    if errors:
        print("[MERGE] REFUSED: the two arm packages cannot be merged because:")
        for e in errors:
            print(f"  - {e}")
        return 2

    if args.validate_only:
        print("[MERGE] gate OK: two valid 30-task arm packages are mergeable")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    report = merge_packages(adaptive_dir, baseline_dir, out_dir)

    print("[MERGE] wrote merged comparison package:")
    for key in ("task_ledger", "analysis", "paired_analysis"):
        print(f"  {key}: {report[key]}")

    print("\n[MERGE] package metadata:")
    for key in (
        "merged_entries", "manifest_verified", "manifest_entries", "validation_ok",
        "paired_valid_N", "paired_fatal_N", "config_sha", "benchmark_manifest_sha",
        "code_commit_sha", "provider", "model", "retry_budget", "arms",
    ):
        print(f"  {key}: {report[key]}")

    print(f"\n[MERGE] protocol note: {report['protocol_note']}")
    print(f"[MERGE] protocol_path: {report['protocol_path']}")
    print(f"[MERGE] protocol_version: {report['protocol_version']}")

    if not report["validation_ok"]:
        print("\n[MERGE] ABORT: merged package failed canonical validation:")
        for e in report["validation_errors"]:
            print(f"  - {e}")
        return 1

    print("\n[MERGE] OK: merged comparison package valid + lifecycle COMPLETE candidate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
