"""
Tests for the fail-closed V4 experiment lifecycle.

These tests exercise lifecycle.py only. They create throwaway experiment
directories under evaluation/tmp and never touch:
  - evaluation/results/exp_20260911_014541_full30/
  - any historical V3/archstrong experiment directory
  - the live benchmark manifest, configs, or raw artifacts

No benchmark tasks are executed and no API calls are made.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lifecycle as L  # noqa: E402


CONFIG_SHA = "config_sha_placeholder"
MANIFEST_SHA = "manifest_sha_placeholder"
COMMIT_SHA = "commit_sha_placeholder"


def _write_mock_raw(exp_dir: Path, system: str, task_ids: list[str],
                     *, duplicate_ids: list[str] = None) -> None:
    """Write one mock raw result per task_id. Duplicate IDs are written as
    distinct files so raw_result_counts can detect n>1 entries for the same
    (task_id, system) pair."""
    raw_dir = exp_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for idx, task_id in enumerate(task_ids):
        rec = {
            "task_id": task_id,
            "system": system,
            "repository": "https://example.invalid",
            "issue_title": f"mock {task_id}#{idx}",
            "timestamp": L._utc_now_iso(),
            "end_to_end_resolved": False,
            "execution": {
                "status": "error",
                "failure_category": "test_marker",
                "latency_seconds": 0.0,
                "llm_calls": None,
                "input_tokens": None,
                "output_tokens": None,
                "error_message": "mock",
            },
            "localization": {"predicted_file": None, "gold_file": "src/x.py", "top1_correct": None},
            "patch": {"generated": False, "syntax_valid": None},
            "tests": {"generated": False, "generated_tests_passed": None},
            "regression": {"hidden_tests_passed": None, "regression_free": None},
            "repair": {"attempts": None, "first_attempt_success": None, "resolved_within_retry_budget": False},
            "cost": {"estimated_usd": None},
            "pr": {"branch_created": False, "commit_created": False, "pr_created": False},
        }
        # Distinct filename per write so glob returns both entries.
        (raw_dir / f"{task_id}_{system}_v{idx}.json").write_text(json.dumps(rec), encoding="utf-8")
    for idx, task_id in enumerate(duplicate_ids or [], start=1000):
        rec = {
            "task_id": task_id,
            "system": system,
            "repository": "https://example.invalid",
            "issue_title": f"mock dup {task_id}#{idx}",
            "timestamp": L._utc_now_iso(),
            "end_to_end_resolved": False,
            "execution": {
                "status": "error",
                "failure_category": "test_marker",
                "latency_seconds": 0.0,
                "llm_calls": None,
                "input_tokens": None,
                "output_tokens": None,
                "error_message": "mock",
            },
            "localization": {"predicted_file": None, "gold_file": "src/x.py", "top1_correct": None},
            "patch": {"generated": False, "syntax_valid": None},
            "tests": {"generated": False, "generated_tests_passed": None},
            "regression": {"hidden_tests_passed": None, "regression_free": None},
            "repair": {"attempts": None, "first_attempt_success": None, "resolved_within_retry_budget": False},
            "cost": {"estimated_usd": None},
            "pr": {"branch_created": False, "commit_created": False, "pr_created": False},
        }
        (raw_dir / f"{task_id}_{system}_dup{idx}.json").write_text(json.dumps(rec), encoding="utf-8")


def _stub_config_path(tmp_path: Path) -> Path:
    p = tmp_path / "benchmark_v4.yaml"
    p.write_text("systems:\n  - name: adaptive_multi_agent\n    module: x\n  - name: baseline_b\n    module: y\n", encoding="utf-8")
    return p


def _make_complete_experiment(tmp_path: Path, *, config_path=None, arm_system=None) -> Path:
    config_path = config_path or _stub_config_path(tmp_path)
    exp_dir = tmp_path / ("complete_exp_full30_arm" if arm_system else "complete_exp_full30")
    L.init_lifecycle(
        exp_dir,
        config_path=config_path,
        arm_system=arm_system,
        benchmark_manifest_sha=MANIFEST_SHA,
        commit_sha=COMMIT_SHA,
        provider="nara",
        model="laguna-s-2.1",
    )
    if arm_system:
        _write_mock_raw(exp_dir, arm_system, L.TASK_IDS)
    else:
        _write_mock_raw(exp_dir, "adaptive_multi_agent", L.TASK_IDS)
        _write_mock_raw(exp_dir, "baseline_b", L.TASK_IDS)
    return exp_dir


def test_lifecycle_states_defined():
    assert L.IN_PROGRESS == "IN_PROGRESS"
    assert L.COMPLETE == "COMPLETE"
    assert L.INVALID_PARTIAL == "INVALID_PARTIAL"
    assert L.FAILED == "FAILED"
    assert L.EXPECTED_TASKS == 30
    assert L.EXPECTED_ARMS == 2
    assert L.EXPECTED_RAW_RESULTS == 60
    assert L.ARMS == ("adaptive_multi_agent", "baseline_b")
    assert len(L.TASK_IDS) == 30


def test_init_lifecycle_writes_status(tmp_path):
    exp_dir = tmp_path / "fresh_exp_full30"
    cfg = _stub_config_path(tmp_path)
    doc = L.init_lifecycle(
        exp_dir, config_path=cfg,
        benchmark_manifest_sha=MANIFEST_SHA,
        commit_sha=COMMIT_SHA,
        provider="nara",
        model="laguna-s-2.1",
    )
    status_path = exp_dir / "experiment_status.json"
    assert status_path.exists()
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == L.IN_PROGRESS
    assert payload["experiment_id"] == exp_dir.name
    assert payload["expected_tasks"] == 30
    assert payload["expected_arms"] == 2
    assert payload["expected_raw_results"] == 60
    assert payload["config_sha"] == L.config_sha(cfg)
    assert payload["benchmark_manifest_sha"] == MANIFEST_SHA
    assert payload["commit_sha"] == COMMIT_SHA
    assert payload["provider"] == "nara"
    assert payload["model"] == "laguna-s-2.1"


def test_init_lifecycle_refuses_stale_nonempty_directory(tmp_path):
    exp_dir = tmp_path / "stale_exp_full30"
    exp_dir.mkdir()
    (exp_dir / "raw").mkdir()
    (exp_dir / "raw" / "task_001_adaptive_multi_agent.json").write_text("{}", encoding="utf-8")
    cfg = _stub_config_path(tmp_path)
    with pytest.raises(RuntimeError, match="not empty"):
        L.init_lifecycle(exp_dir, config_path=cfg)


def test_init_lifecycle_refuses_existing_status_file(tmp_path):
    exp_dir = tmp_path / "status_exists_exp_full30"
    exp_dir.mkdir()
    (exp_dir / "experiment_status.json").write_text("{}", encoding="utf-8")
    cfg = _stub_config_path(tmp_path)
    with pytest.raises(RuntimeError, match="experiment_status.json already exists"):
        L.init_lifecycle(exp_dir, config_path=cfg)


def test_write_status_refresh(tmp_path):
    exp_dir = tmp_path / "refresh_exp_full30"
    cfg = _stub_config_path(tmp_path)
    doc = L.init_lifecycle(exp_dir, config_path=cfg)
    first = json.loads((exp_dir / "experiment_status.json").read_text(encoding="utf-8"))
    assert first["status"] == L.IN_PROGRESS
    L.write_status(exp_dir, L.COMPLETE)
    second = json.loads((exp_dir / "experiment_status.json").read_text(encoding="utf-8"))
    assert second["status"] == L.COMPLETE
    assert second["experiment_id"] == first["experiment_id"]


def test_raw_result_counts_empty(tmp_path):
    exp_dir = tmp_path / "empty_exp_full30"
    exp_dir.mkdir()
    c = L.raw_result_counts(exp_dir / "raw")
    assert c["adaptive_multi_agent"] == 0
    assert c["baseline_b"] == 0
    assert c["raw_file_count"] == 0
    assert c["adaptive_task_ids"] == []
    assert c["baseline_task_ids"] == []
    assert c["adaptive_duplicates"] == []
    assert c["baseline_duplicates"] == []


def test_raw_result_counts_counts_both_arms(tmp_path):
    exp_dir = tmp_path / "both_arms_exp_full30"
    exp_dir.mkdir()
    _write_mock_raw(exp_dir, "adaptive_multi_agent", ["task_001", "task_002"])
    _write_mock_raw(exp_dir, "baseline_b", ["task_001", "task_002", "task_003"])
    c = L.raw_result_counts(exp_dir / "raw")
    assert c["adaptive_multi_agent"] == 2
    assert c["baseline_b"] == 3
    assert c["raw_file_count"] == 5


def test_raw_result_counts_detects_duplicates(tmp_path):
    exp_dir = tmp_path / "dup_exp_full30"
    exp_dir.mkdir()
    _write_mock_raw(exp_dir, "baseline_b", ["task_001"], duplicate_ids=["task_001"])
    c = L.raw_result_counts(exp_dir / "raw")
    assert c["baseline_duplicates"] == ["task_001"]


def test_invariant_ok_requires_30_and_30(tmp_path):
    exp_dir = tmp_path / "incomplete_exp_full30"
    exp_dir.mkdir()
    _write_mock_raw(exp_dir, "adaptive_multi_agent", L.TASK_IDS[:25])
    _write_mock_raw(exp_dir, "baseline_b", [])
    c = L.raw_result_counts(exp_dir / "raw")
    ok, issues = L.invariant_ok(c)
    assert not ok
    assert any("adaptive raw results" in i for i in issues)
    assert any("baseline raw results" in i for i in issues)


def test_invariant_ok_requires_task_id_coverage(tmp_path):
    exp_dir = tmp_path / "missing_id_exp_full30"
    exp_dir.mkdir()
    # 30 adaptive files but wrong IDs
    _write_mock_raw(exp_dir, "adaptive_multi_agent",
                    [f"task_{i:03d}" for i in range(1, 31)])
    _write_mock_raw(exp_dir, "baseline_b",
                    [f"task_{i:03d}" for i in range(2, 31)])  # missing task_001
    c = L.raw_result_counts(exp_dir / "raw")
    ok, issues = L.invariant_ok(c)
    assert not ok
    assert any("baseline task IDs incomplete" in i for i in issues)


def test_invariant_ok_detects_duplicates(tmp_path):
    exp_dir = tmp_path / "dup_invariant_exp_full30"
    exp_dir.mkdir()
    _write_mock_raw(exp_dir, "adaptive_multi_agent", L.TASK_IDS,
                    duplicate_ids=["task_001"])
    _write_mock_raw(exp_dir, "baseline_b", L.TASK_IDS)
    c = L.raw_result_counts(exp_dir / "raw")
    ok, issues = L.invariant_ok(c)
    assert not ok
    assert any("duplicate adaptive" in i for i in issues)


def test_invariant_ok_true_only_when_exact_60(tmp_path):
    exp_dir = tmp_path / "exact60_exp_full30"
    exp_dir.mkdir()
    _write_mock_raw(exp_dir, "adaptive_multi_agent", L.TASK_IDS)
    _write_mock_raw(exp_dir, "baseline_b", L.TASK_IDS)
    c = L.raw_result_counts(exp_dir / "raw")
    ok, issues = L.invariant_ok(c)
    assert ok
    assert issues == []


def test_classify_state_failed_when_no_durable_results(tmp_path):
    exp_dir = tmp_path / "no_results_exp_full30"
    exp_dir.mkdir()
    state = L.classify_state(exp_dir)
    assert state == L.FAILED


def test_classify_state_invalid_partial_on_25_adaptive_0_baseline(tmp_path):
    exp_dir = tmp_path / "partial_25_0_exp_full30"
    exp_dir.mkdir()
    cfg = _stub_config_path(tmp_path)
    L.init_lifecycle(
        exp_dir,
        config_path=cfg,
        arm_system="adaptive_multi_agent",
    )        _write_mock_raw(exp_dir, "adaptive_multi_agent", L.TASK_IDS[:25])
        state = L.classify_state(exp_dir, require_validation_ok=False)
        assert state == L.INVALID_PARTIAL


def test_classify_state_invalid_partial_on_30_29(tmp_path):
    exp_dir = tmp_path / "partial_30_29_exp_full30"
    exp_dir.mkdir()
    cfg = _stub_config_path(tmp_path)    L.init_lifecycle(
        exp_dir,
        config_path=cfg,
        arm_system="baseline_b",
    )
    _write_mock_raw(exp_dir, "baseline_b", L.TASK_IDS)
    _write_mock_raw(exp_dir, "adaptive_multi_agent", L.TASK_IDS[:-1])
    state = L.classify_state(exp_dir, require_validation_ok=False)
    assert state == L.INVALID_PARTIAL


def test_classify_state_complete_when_60_and_no_validation_gate(tmp_path):
    exp_dir = _make_complete_experiment(tmp_path)
    state = L.classify_state(exp_dir, require_validation_ok=False)
    assert state == L.COMPLETE


def test_classify_state_respects_validation_gate(tmp_path):
    exp_dir = _make_complete_experiment(tmp_path)
    state = L.classify_state(exp_dir, require_validation_ok=True, validation_ok=False)
    assert state == L.INVALID_PARTIAL


def test_finalize_experiment_completes_only_after_validation_ok(tmp_path):
    exp_dir = _make_complete_experiment(tmp_path)
    doc = L.finalize_experiment(exp_dir, validation_ok=True, validation_warnings=["w1"])
    assert doc["status"] == L.COMPLETE
    assert doc["final_invariant_ok"] is True
    assert doc["validation_ok"] is True
    assert doc["validation_warnings"] == ["w1"]
    payload = json.loads((exp_dir / "experiment_status.json").read_text(encoding="utf-8"))
    assert payload["status"] == L.COMPLETE


def test_finalize_experiment_invalid_partial_on_failed_validation(tmp_path):
    exp_dir = _make_complete_experiment(tmp_path)
    doc = L.finalize_experiment(
        exp_dir,
        validation_ok=False,
        validation_errors=["V04: retry budget mismatch"],
    )
    assert doc["status"] == L.INVALID_PARTIAL
    assert doc["validation_ok"] is False
    assert any("V04" in e for e in doc["validation_errors"])


def test_finalize_experiment_failed_when_no_durable_results(tmp_path):
    exp_dir = tmp_path / "empty_finalize_exp_full30"
    exp_dir.mkdir()
    cfg = _stub_config_path(tmp_path)
    L.init_lifecycle(exp_dir, config_path=cfg)
    doc = L.finalize_experiment(exp_dir, validation_ok=False, validation_errors=[])
    assert doc["status"] == L.FAILED


def test_finalize_experiment_invalid_partial_on_missing_one_baseline(tmp_path):
    exp_dir = tmp_path / "missing_one_baseline_finalize_exp_full30"
    exp_dir.mkdir()
    cfg = _stub_config_path(tmp_path)
    L.init_lifecycle(exp_dir, config_path=cfg)
    _write_mock_raw(exp_dir, "adaptive_multi_agent", L.TASK_IDS)
    _write_mock_raw(exp_dir, "baseline_b", L.TASK_IDS[:-1])
    doc = L.finalize_experiment(exp_dir, validation_ok=True, validation_errors=[])
    assert doc["status"] == L.INVALID_PARTIAL


def test_finalize_experiment_single_arm_completes_after_30_validated(tmp_path):
    exp_dir = _make_complete_experiment(tmp_path, arm_system="adaptive_multi_agent")
    doc = L.finalize_experiment(exp_dir, validation_ok=True, validation_warnings=[])
    assert doc["status"] == L.COMPLETE
    assert doc["final_invariant_ok"] is True
    payload = json.loads((exp_dir / "experiment_status.json").read_text(encoding="utf-8"))
    assert payload["status"] == L.COMPLETE


def test_finalize_experiment_single_arm_invalid_partial_on_25(tmp_path):
    exp_dir = tmp_path / "single_arm_partial_finalize"
    exp_dir.mkdir()
    cfg = _stub_config_path(tmp_path)
    L.init_lifecycle(exp_dir, config_path=cfg, arm_system="baseline_b")
    _write_mock_raw(exp_dir, "baseline_b", L.TASK_IDS[:25])
    doc = L.finalize_experiment(exp_dir, validation_ok=True, validation_errors=[])
    assert doc["status"] == L.INVALID_PARTIAL
    assert "single-arm 30-result invariant" in doc["completion_reason"]


def test_classify_state_single_arm_complete_when_30_present(tmp_path):
    exp_dir = _make_complete_experiment(tmp_path, arm_system="baseline_b")
    state = L.classify_state(exp_dir, require_validation_ok=False)
    assert state == L.COMPLETE


def test_classify_state_single_arm_invalid_partial_on_25(tmp_path):
    exp_dir = tmp_path / "single_arm_partial_classify"
    exp_dir.mkdir()
    cfg = _stub_config_path(tmp_path)
    L.init_lifecycle(exp_dir, config_path=cfg, arm_system="adaptive_multi_agent")
    _write_mock_raw(exp_dir, "adaptive_multi_agent", L.TASK_IDS[:25])
    state = L.classify_state(exp_dir, require_validation_ok=False)
    assert state == L.INVALID_PARTIAL


def test_dry_run_lifecycleCreates_inprogress_then_invalid_partial(tmp_path):
    exp_dir = L.dry_run_lifecycle(tmp_path, _stub_config_path(tmp_path))
    status = json.loads((exp_dir / "experiment_status.json").read_text(encoding="utf-8"))
    assert status["status"] == L.INVALID_PARTIAL
    counts = L.raw_result_counts(exp_dir / "raw")
    assert counts["adaptive_multi_agent"] == 3
    assert counts["baseline_b"] == 0
    assert counts["raw_file_count"] == 3


def test_preserve_existing_partial_experiment_not_touched(tmp_path):
    # Simulate the real partial run: 25 adaptive, 0 baseline
    exp_dir = tmp_path / "preserved_partial_exp_full30"
    exp_dir.mkdir()
    (exp_dir / "raw").mkdir()
    _write_mock_raw(exp_dir, "adaptive_multi_agent", L.TASK_IDS[:25])
    (exp_dir / "experiment_status.json").write_text(
        json.dumps({"experiment_id": exp_dir.name, "status": L.IN_PROGRESS}), encoding="utf-8")
    # Reading/inspecting state must not delete or modify anything.
    c = L.raw_result_counts(exp_dir / "raw")
    assert c["adaptive_multi_agent"] == 25
    assert c["baseline_b"] == 0
    assert c["raw_file_count"] == 25
    assert len(list((exp_dir / "raw").glob("*.json"))) == 25
    assert (exp_dir / "experiment_status.json").exists()
