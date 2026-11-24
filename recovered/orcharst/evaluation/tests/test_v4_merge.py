"""
Tests for the V4 arm merge/evaluation command and the fail-closed merge gate.

These tests never run any live benchmark or API calls. They assemble synthetic
COMPLETE/incomplete single-arm packages under evaluation/tmp and exercise the
merge command's refusal and acceptance rules plus the equivalence of the merged
paired metrics to the canonical paired calculation.
"""

from __future__ import annotations

import json
import sys
import subprocess
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lifecycle as L  # noqa: E402
import build_ledger as BL  # noqa: E402
import paired_analysis as PA  # noqa: E402
import merge_arms  # noqa: E402

from conftest import base_record  # noqa: E402

SYS_A = "adaptive_multi_agent"
SYS_B = "baseline_b"
TASKS = [f"task_{i:03d}" for i in range(1, 31)]


def _mock_config(tmp_path: Path) -> Path:
    p = tmp_path / "benchmark_v4.yaml"
    p.write_text(
        "systems:\n"
        "  - name: adaptive_multi_agent\n"
        "    module: x\n"
        "  - name: baseline_b\n"
        "    module: y\n",
        encoding="utf-8",
    )
    return p


def _write_arm_raw_dir(raw_dir: Path, arm_system: str, task_ids: list[str], *, leader: bool = True):
    raw_dir.mkdir(parents=True, exist_ok=True)
    for idx, task_id in enumerate(task_ids):
        rec = base_record(task_id, arm_system)
        rec["repair"]["retry_budget"] = 2
        (raw_dir / f"{task_id}_{arm_system}.json").write_text(
            json.dumps(rec, default=str), encoding="utf-8"
        )


def _real_config_sha(cfg: Path) -> str:
    import hashlib
    return hashlib.sha256(cfg.read_bytes()).hexdigest()


def _make_arm_package(tmp_path: Path, arm_system: str, *, complete: bool = True, sub: Path | None = None) -> Path:
    """Create a synthetic V4 arm package directory with lifecycle metadata.

    The created package records the real benchmark_v4.yaml config_sha so the
    merge gate can verify arm-to-current config identity.
    """
    exp_dir = (sub or tmp_path) / f"{arm_system}_arm_pkg"
    # Use the real config path for config_sha fidelity inside the package.
    real_cfg = tmp_path / "benchmark_v4.yaml"
    real_cfg.parent.mkdir(parents=True, exist_ok=True)
    real_cfg.write_text(
        "systems:\n"
        "  - name: adaptive_multi_agent\n"
        "    module: x\n"
        "  - name: baseline_b\n"
        "    module: y\n",
        encoding="utf-8",
    )

    L.init_lifecycle(
        exp_dir,
        config_path=real_cfg,
        arm_system=arm_system,
        benchmark_manifest_sha="manifest_sha_placeholder",
        commit_sha="commit_sha_placeholder",
        provider="nara",
        model="laguna-s-2.1",
    )

    raw_dir = exp_dir / "raw"
    if complete:
        _write_arm_raw_dir(raw_dir, arm_system, TASKS)
        # Pretend evaluation already happened: write a valid single-arm package.
        paths, _warnings = BL.build_package(
            f"{arm_system}_arm_pkg",
            raw_dir=raw_dir,
            out_dir=exp_dir,
            skip_manifest_gate=True,
        )
        # Replay the real on-disk config_sha into the package status so the merge
        # gate sees matching arm-to-current config identity.
        status_path = exp_dir / "experiment_status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["config_sha"] = _real_config_sha(real_cfg)
        status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    else:
        _write_arm_raw_dir(raw_dir, arm_system, TASKS[:25])

    return exp_dir


def _patch_status(exp_dir: Path, status: str):
    status_path = exp_dir / "experiment_status.json"
    doc = json.loads(status_path.read_text(encoding="utf-8"))
    doc["status"] = status
    status_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _patch_field(exp_dir: Path, field: str, value):
    status_path = exp_dir / "experiment_status.json"
    doc = json.loads(status_path.read_text(encoding="utf-8"))
    doc[field] = value
    status_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _gate_cmd(adaptive_dir: Path, baseline_dir: Path, out_dir: Path, validate_only: bool = False) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "merge_arms.py"),
        "--adaptive", str(adaptive_dir),
        "--baseline", str(baseline_dir),
        "--out", str(out_dir),
    ]
    if validate_only:
        cmd.append("--validate-only")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def test_merge_refuses_incomplete_arm_package(tmp_path):
    a_dir = _make_arm_package(tmp_path, SYS_A, complete=True)
    b_dir = _make_arm_package(tmp_path, SYS_B, complete=True, sub=tmp_path / "b")
    _patch_status(b_dir, L.IN_PROGRESS)
    out = tmp_path / "merged"
    proc = _gate_cmd(a_dir, b_dir, out, validate_only=True)
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "REFUSED" in combined
    assert "baseline_b" in combined
    assert "COMPLETE" in combined


def test_merge_refuses_non_complete_lifecycle_state(tmp_path):
    a_dir = _make_arm_package(tmp_path, SYS_A, complete=True)
    b_dir = _make_arm_package(tmp_path, SYS_B, complete=True, sub=tmp_path / "b")
    _patch_status(b_dir, L.INVALID_PARTIAL)
    proc = _gate_cmd(a_dir, b_dir, tmp_path / "merged", validate_only=True)
    assert proc.returncode != 0
    assert "REFUSED" in proc.stdout + proc.stderr


def test_merge_refuses_missing_task(tmp_path):
    a_dir = _make_arm_package(tmp_path, SYS_A, complete=True)
    b_dir = _make_arm_package(tmp_path, SYS_B, complete=True, sub=tmp_path / "b")
    # Remove one baseline raw file so the single-arm invariant fails.
    (b_dir / "raw" / "task_007_baseline_b.json").unlink()
    _patch_status(b_dir, L.COMPLETE)
    proc = _gate_cmd(a_dir, b_dir, tmp_path / "merged", validate_only=True)
    assert proc.returncode != 0
    assert "REFUSED" in proc.stdout + proc.stderr


def test_merge_refuses_duplicate_task(tmp_path):
    a_dir = _make_arm_package(tmp_path, SYS_A, complete=True)
    b_dir = _make_arm_package(tmp_path, SYS_B, complete=True, sub=tmp_path / "b")
    dup = b_dir / "raw" / "task_007_baseline_b.json"
    dup.write_text(dup.read_text(encoding="utf-8"), encoding="utf-8")
    _patch_status(b_dir, L.COMPLETE)
    proc = _gate_cmd(a_dir, b_dir, tmp_path / "merged", validate_only=True)
    assert proc.returncode != 0
    assert "REFUSED" in proc.stdout + proc.stderr


def test_merge_refuses_config_sha_mismatch(tmp_path):
    a_dir = _make_arm_package(tmp_path, SYS_A, complete=True)
    b_dir = _make_arm_package(tmp_path, SYS_B, complete=True, sub=tmp_path / "b")

    # Tamper with the recorded config_sha in the adaptive package status file.
    _patch_field(a_dir, "config_sha", "tampered-sha-for-merge-gate-test")
    proc = _gate_cmd(a_dir, b_dir, tmp_path / "merged", validate_only=True)
    assert proc.returncode != 0
    assert "REFUSED" in proc.stdout + proc.stderr
    assert "config_sha" in proc.stdout + proc.stderr


def test_merge_refuses_retry_budget_mismatch(tmp_path):
    a_dir = _make_arm_package(tmp_path, SYS_A, complete=True)
    b_dir = _make_arm_package(tmp_path, SYS_B, complete=True, sub=tmp_path / "b")

    # Rewrite the baseline ledger entries to claim retry_budget 3.
    b_ledger = json.loads((b_dir / "task_ledger.json").read_text(encoding="utf-8"))
    for e in b_ledger["entries"]:
        e["retry_budget"] = 3
    (b_dir / "task_ledger.json").write_text(
        json.dumps(b_ledger, indent=2, default=str), encoding="utf-8"
    )
    proc = _gate_cmd(a_dir, b_dir, tmp_path / "merged", validate_only=True)
    assert proc.returncode != 0
    assert "REFUSED" in proc.stdout + proc.stderr
    assert "retry_budget" in proc.stdout + proc.stderr


def test_merge_refuses_provider_model_mismatch(tmp_path):
    a_dir = _make_arm_package(tmp_path, SYS_A, complete=True)
    b_dir = _make_arm_package(tmp_path, SYS_B, complete=True, sub=tmp_path / "b")

    _patch_field(b_dir, "model", "some-other-model")
    proc = _gate_cmd(a_dir, b_dir, tmp_path / "merged", validate_only=True)
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "REFUSED" in combined
    assert "model" in combined


def test_merge_refuses_extra_noise_in_arm_dir(tmp_path):
    a_dir = _make_arm_package(tmp_path, SYS_A, complete=True)
    b_dir = _make_arm_package(tmp_path, SYS_B, complete=True, sub=tmp_path / "b")
    # Add stray baseline raw result into the adaptive arm raw dir.
    bad = base_record("task_999", SYS_B)
    (a_dir / "raw" / "task_999_baseline_b.json").write_text(
        json.dumps(bad, default=str), encoding="utf-8"
    )
    proc = _gate_cmd(a_dir, b_dir, tmp_path / "merged", validate_only=True)
    assert proc.returncode != 0
    assert "REFUSED" in proc.stdout + proc.stderr


def test_merge_accepts_two_valid_30_task_arm_packages(tmp_path):
    a_dir = _make_arm_package(tmp_path, SYS_A, complete=True)
    b_dir = _make_arm_package(tmp_path, SYS_B, complete=True, sub=tmp_path / "b")
    out = tmp_path / "merged"
    proc = _gate_cmd(a_dir, b_dir, out, validate_only=True)
    assert proc.returncode == 0
    assert "gate OK" in proc.stdout
    assert "mergeable" in proc.stdout


def test_merge_produces_canonical_comparison_and_paired_metrics_equal_direct_calc(tmp_path):
    a_dir = _make_arm_package(tmp_path, SYS_A, complete=True)
    b_dir = _make_arm_package(tmp_path, SYS_B, complete=True, sub=tmp_path / "b")
    out = tmp_path / "merged"
    proc = _gate_cmd(a_dir, b_dir, out, validate_only=False)
    assert proc.returncode == 0

    ledger = json.loads((out / "task_ledger.json").read_text(encoding="utf-8"))
    analysis = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    paired = json.loads((out / "paired_analysis.json").read_text(encoding="utf-8"))

    entries = ledger["entries"]
    systems = tuple(sorted({e["system"] for e in entries}))
    assert systems == ("adaptive_multi_agent", "baseline_b")

    # Canonical direct calculation via the same evaluator used by build_ledger.
    direct = PA.paired_analysis(entries, systems)
    merged_tier = paired["tiers"]["valid"]

    assert merged_tier["N"] == direct["tiers"]["valid"]["N"]
    assert merged_tier["outcome_counts"] == direct["tiers"]["valid"]["outcome_counts"]
    assert merged_tier["mcnemar_exact_two_sided_p"] == pytest.approx(
        direct["tiers"]["valid"]["mcnemar_exact_two_sided_p"]
    )

    # The merged package is a complete canonical package (task_ledger + analysis +
    # paired_analysis) and validates with the two-system validator.
    from evaluation.validate_ledger import validate_package
    report = validate_package(out, expect_systems=list(systems), require_two_systems=True)
    assert report["ok"] is True
