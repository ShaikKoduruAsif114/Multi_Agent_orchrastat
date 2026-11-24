"""
Regression tests for the exact defects discovered in the Adaptive V3 audit.
Each test documents the bug it pins down; if any of these fail, a defect that
cost the V3 experiment its validity has come back.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_ledger as BL                      # noqa: E402
import paired_analysis as PA                   # noqa: E402
from conftest import (                         # noqa: E402
    base_record, provider_502_record, upstream_error_200_record,
    null_attempts_record, first_pass_contradiction_record,
    passed_count_conflict_record,
)


# --------------------------------------------------------------------------
# Regression 1: task_020 provider contamination
# The 502 was recorded ONLY in provider.contamination while the run completed;
# the original V3 report counted it as a clean adaptive failure.
# --------------------------------------------------------------------------
def test_regression_task020_contamination_only_in_provider_block():
    rec = provider_502_record("task_020", "adaptive_multi_agent", fatal=False)
    # completed run: status not 'error', so no generic infra label applies
    rec["execution"]["status"] = "genuine_agent_failure"
    e = BL.build_entry(rec)
    assert e["provider_failure"] is True, "contamination in provider block must flag provider_failure"
    assert e["FINAL_CLASSIFICATION"] == "provider_failure", \
        "provider contamination must take precedence over any generic label"
    assert e["provider_error_type"] == ["provider_server_error"]
    assert e["provider_http_status"] == ["502"]
    assert e["provider_contamination_source"] == "provider.contamination record"


def test_regression_task020_precedence_over_infra_label():
    rec = provider_502_record("task_020", "adaptive_multi_agent", fatal=False)
    rec["execution"]["status"] = "error"  # runner died too — still provider
    rec["execution"]["error_message"] = "sandbox subprocess crashed"  # generic label
    e = BL.build_entry(rec)
    assert e["FINAL_CLASSIFICATION"] == "provider_failure", \
        "provider contamination must outrank generic runner/infrastructure labels"
    assert e["infrastructure_failure"] is False


# --------------------------------------------------------------------------
# Regression 2: baseline 502 contamination
# Seven baseline runs died to raw 502s and were initially classed as
# infrastructure failures in the v2-era classifier.
# --------------------------------------------------------------------------
def test_regression_baseline_502_is_provider_not_infra():
    rec = provider_502_record("task_003", "baseline_b", fatal=True)
    e = BL.build_entry(rec)
    assert e["provider_failure"] is True
    assert e["infrastructure_failure"] is False
    assert e["FINAL_CLASSIFICATION"] == "provider_failure"
    assert "provider_server_error[runner]" in (e["provider_error_type"] or [])


def test_regression_baseline_502_fatal_death_detected():
    rec = provider_502_record("task_004", "baseline_b", fatal=True)
    e = BL.build_entry(rec)
    assert PA.is_fatal_death(e) is True, "status=error + provider sig = fatal death"


def test_regression_contaminated_completed_run_not_fatal():
    rec = provider_502_record("task_020", "adaptive_multi_agent", fatal=False)
    e = BL.build_entry(rec)
    assert PA.is_fatal_death(e) is False, \
        "completed runs are observed outcomes, not fatal deaths"
    assert PA.is_valid_run(e) is False, "but they are still not VALID_RUNs"


# --------------------------------------------------------------------------
# Regression 3: HTTP-200-wrapped upstream_error
# The provider returned HTTP 200 wrapping {"type":"upstream_error"}; the naive
# classifier called this an infrastructure failure.
# --------------------------------------------------------------------------
def test_regression_http200_upstream_error_is_provider():
    rec = upstream_error_200_record("task_008", "baseline_b")
    e = BL.build_entry(rec)
    assert e["provider_failure"] is True
    assert e["infrastructure_failure"] is False
    assert e["FINAL_CLASSIFICATION"] == "provider_failure"
    assert any(c.startswith("provider_upstream_error") for c in (e["provider_error_type"] or []))
    assert e["provider_http_status"] == ["200"]


def test_regression_http200_upstream_error_completed_variant():
    rec = upstream_error_200_record("task_010", "baseline_b")
    rec["execution"]["status"] = "genuine_agent_failure"  # runner survived
    e = BL.build_entry(rec)
    assert e["provider_failure"] is True and PA.is_fatal_death(e) is False


# --------------------------------------------------------------------------
# Regression 4: null repair.attempts
# Baseline error runs record repair.attempts=null; the original int() cast
# crashed the ledger build.
# --------------------------------------------------------------------------
def test_regression_null_repair_attempts_does_not_crash():
    rec = null_attempts_record("task_005", "baseline_b")
    e = BL.build_entry(rec)  # must not raise
    assert e["repair_attempts"] == 0
    assert e["FINAL_CLASSIFICATION"] == "provider_failure"


def test_regression_null_attempts_valid_run_baseline():
    rec = base_record("task_006", "baseline_b")
    rec["repair"]["attempts"] = None
    rec["repair"]["first_pass_resolved_hidden"] = None
    rec["end_to_end_resolved"] = True
    e = BL.build_entry(rec)
    assert e["repair_attempts"] == 0
    assert e["FINAL_CLASSIFICATION"] == "resolved"


# --------------------------------------------------------------------------
# Regression 5: adaptive first_pass_resolved contradiction
# Controller block said first_pass_resolved=false while hidden tests proved a
# first-pass success on tasks 001/002/026.
# --------------------------------------------------------------------------
def test_regression_first_pass_contradiction_detected():
    rec = first_pass_contradiction_record("task_001")
    e = BL.build_entry(rec)
    assert e["first_pass_field_conflict"] is not None
    assert e["first_pass_field_conflict"]["canonical_value"] is True
    assert e["first_pass_field_conflict"]["adaptive_block_value"] is False
    assert e["first_pass_resolved"] is True, "canonical source = repair.first_pass_resolved_hidden"


def test_regression_first_pass_contradiction_fails_validation():
    import validate_ledger as VL
    from pathlib import Path
    import json
    e = BL.build_entry(first_pass_contradiction_record("task_002"))
    pkg = Path(__file__).parent / "_tmp_contradiction_pkg"
    pkg.mkdir(exist_ok=True)
    try:
        (pkg / "task_ledger.json").write_text(json.dumps(
            {"entries": [e], "requested_model": "laguna-s-2.1"}, default=str))
        (pkg / "analysis.json").write_text(json.dumps({"n_runs": 1}))
        (pkg / "paired_analysis.json").write_text(json.dumps({"tiers": {}}))
        report = VL.validate_package(pkg)
        assert any(err.startswith("V06") for err in report["errors"]), \
            "validator must fail on contradictory first-pass fields"
    finally:
        (pkg / "task_ledger.json").unlink(missing_ok=True)
        (pkg / "analysis.json").unlink(missing_ok=True)
        (pkg / "paired_analysis.json").unlink(missing_ok=True)


def test_regression_no_false_conflict_when_block_agrees():
    rec = base_record("task_003", "adaptive_multi_agent")
    e = BL.build_entry(rec)
    assert e["first_pass_field_conflict"] is None


# --------------------------------------------------------------------------
# Regression 6: unequal retry budgets
# Adaptive ran with budgets 1-2, baseline with 3; first-pass/repair
# comparisons were presented as budget-matched.
# --------------------------------------------------------------------------
def test_regression_retry_budget_mismatch_detected():
    import validate_ledger as VL
    from pathlib import Path
    import json
    e_a = BL.build_entry(base_record("task_001", "adaptive_multi_agent"))
    e_b = BL.build_entry(base_record("task_001", "baseline_b"))
    pkg = Path(__file__).parent / "_tmp_budget_pkg"
    pkg.mkdir(exist_ok=True)
    try:
        (pkg / "task_ledger.json").write_text(json.dumps(
            {"entries": [e_a, e_b], "requested_model": "laguna-s-2.1"}))
        (pkg / "analysis.json").write_text(json.dumps({"n_runs": 2}))
        (pkg / "paired_analysis.json").write_text(json.dumps({"tiers": {}}))
        report = VL.validate_package(pkg)
        assert any(err.startswith("V04") for err in report["errors"]), \
            "validator must fail when arms run unequal retry budgets"
        assert "1" in str(report["errors"]) and "3" in str(report["errors"])
    finally:
        for n in ("task_ledger.json", "analysis.json", "paired_analysis.json"):
            (pkg / n).unlink(missing_ok=True)


def test_regression_retry_budget_disclosure_in_package(tmp_path):
    import json
    raw = tmp_path / "raw"
    raw.mkdir()
    for i in range(1, 3):
        t = f"task_{i:03d}"
        (raw / f"{t}_adaptive_multi_agent.json").write_text(json.dumps(
            base_record(t, "adaptive_multi_agent")))
        (raw / f"{t}_baseline_b.json").write_text(json.dumps(
            base_record(t, "baseline_b")))
    paths, _ = BL.build_package("synthetic_budget_check", raw_dir=raw,
                                out_dir=tmp_path / "pkg", skip_manifest_gate=True)
    analysis = json.loads(paths["analysis"].read_text(encoding="utf-8"))
    disc = analysis["retry_budget_disclosure"]
    assert disc["budgets_equal_across_arms"] is False
    assert "NOT budget-equivalent" in disc["verdict"]


def test_retry_budget_disclosure_ok_when_equal(tmp_path):
    import json
    raw = tmp_path / "raw"
    raw.mkdir()
    for i in range(1, 3):
        t = f"task_{i:03d}"
        a = base_record(t, "adaptive_multi_agent")
        a["repair"]["retry_budget"] = 3  # equalize budgets
        (raw / f"{t}_adaptive_multi_agent.json").write_text(json.dumps(a))
        (raw / f"{t}_baseline_b.json").write_text(json.dumps(base_record(t, "baseline_b")))
    paths, _ = BL.build_package("synthetic_budget_ok", raw_dir=raw,
                                out_dir=tmp_path / "pkg", skip_manifest_gate=True)
    analysis = json.loads(paths["analysis"].read_text(encoding="utf-8"))
    assert analysis["retry_budget_disclosure"]["budgets_equal_across_arms"] is True


# --------------------------------------------------------------------------
# Regression 7: passed_count / run-level boolean discrepancy
# V3 adaptive runs recorded hidden_tests_passed=true with
# hidden_tests_passed_count=0; per-test counts and run booleans disagreed.
# --------------------------------------------------------------------------
def test_regression_passed_count_conflict_detected():
    rec = passed_count_conflict_record("task_001")
    e = BL.build_entry(rec)
    assert e["hidden_count_inconsistent"] == "passed=true but passed_count=0"
    assert e["hidden_tests_passed"] is True       # run-level boolean preserved
    assert e["hidden_tests_passed_count"] == 0    # raw count preserved


def test_regression_passed_count_conflict_warns_not_fails():
    import validate_ledger as VL
    from pathlib import Path
    import json
    e = BL.build_entry(passed_count_conflict_record("task_002"))
    pkg = Path(__file__).parent / "_tmp_count_pkg"
    pkg.mkdir(exist_ok=True)
    try:
        (pkg / "task_ledger.json").write_text(json.dumps(
            {"entries": [e], "requested_model": "laguna-s-2.1"}))
        (pkg / "analysis.json").write_text(json.dumps({"n_runs": 1}))
        (pkg / "paired_analysis.json").write_text(json.dumps({"tiers": {}}))
        report = VL.validate_package(pkg)
        assert report["ok"] is True or not any(x.startswith("V10") for x in report["errors"]), \
            "count discrepancies are disclosed warnings, not hard failures"
        assert any(w.startswith("V10") for w in report["warnings"])
    finally:
        for n in ("task_ledger.json", "analysis.json", "paired_analysis.json"):
            (pkg / n).unlink(missing_ok=True)


def test_regression_opposite_count_conflict_detected():
    rec = base_record("task_003", "baseline_b")
    rec["regression"]["hidden_tests_passed"] = False
    rec["regression"]["hidden_tests_total"] = 18
    rec["regression"]["hidden_tests_passed_count"] = 18  # count says all passed
    e = BL.build_entry(rec)
    assert e["hidden_count_inconsistent"] == "passed=false but passed_count==hidden_tests_total"
