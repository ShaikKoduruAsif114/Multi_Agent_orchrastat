"""
Unit tests for the canonical evaluation modules: classification precedence,
denominator rules, paired analysis, McNemar, manifest verification, and the
validators' failure classes (V01-V10).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_ledger as BL                      # noqa: E402
import paired_analysis as PA                   # noqa: E402
import validate_ledger as VL                   # noqa: E402
import validate_report as VR                   # noqa: E402
import verify_manifest as VM                   # noqa: E402
from conftest import (                         # noqa: E402
    base_record, provider_502_record, upstream_error_200_record,
    passed_count_conflict_record, TASKS,
)

SYS_A = "adaptive_multi_agent"
SYS_B = "baseline_b"


# ===========================================================================
# build_ledger: FINAL_CLASSIFICATION precedence
# ===========================================================================
@pytest.mark.parametrize("err,expected_cat", [
    ("Error code: 502 - bad gateway", "provider_server_error"),
    ("Error code: 503 - unavailable", "provider_unavailable"),
    ("Error code: 429 - rate limited", "provider_rate_limit"),
    ("Error code: 401 - unauthorized", "provider_auth_error"),
    ('{"type": "upstream_error"}', "provider_upstream_error"),
    ("provider_timeout after 30s", "provider_timeout"),
    ("model_not_found: no such model", "provider_model_unavailable"),
    ("Connection error: reset by peer", "provider_unavailable"),
])
def test_provider_signature_categories(err, expected_cat):
    hit, cat, _status = BL.provider_signature(err)
    assert hit is True and cat == expected_cat


@pytest.mark.parametrize("err", [
    "patch_quality_gate_failed: ['syntax_valid']",
    "unbound variable in fixture", "", None, "sandbox OOM",
])
def test_provider_signature_negative(err):
    assert BL.provider_signature(err)[0] is False


def test_provider_beats_infra():
    e = BL.build_entry(provider_502_record("task_001", SYS_B, fatal=True))
    assert e["FINAL_CLASSIFICATION"] == "provider_failure"
    assert e["infrastructure_failure"] is False


def test_infra_when_no_provider_signature():
    rec = base_record("task_001", SYS_B)
    rec["execution"]["status"] = "error"
    rec["execution"]["error_message"] = "sandbox subprocess crashed unexpectedly"
    rec["end_to_end_resolved"] = False
    e = BL.build_entry(rec)
    assert e["FINAL_CLASSIFICATION"] == "infrastructure_failure"
    assert e["provider_failure"] is False


def test_gate_rejection_is_genuine_agent_failure():
    rec = base_record("task_002", "multi_agent")
    rec["execution"]["status"] = "patch_failed"
    rec["execution"]["error_message"] = "patch_quality_gate_failed: ['syntax_valid']"
    rec["end_to_end_resolved"] = False
    rec["regression"]["hidden_tests_executed"] = False
    e = BL.build_entry(rec)
    assert e["FINAL_CLASSIFICATION"] == "genuine_agent_failure"


def test_resolved_requires_all_conditions():
    assert BL.build_entry(base_record("task_001", SYS_B))["FINAL_CLASSIFICATION"] == "resolved"
    rec = base_record("task_001", SYS_B)
    rec["localization"]["top1_correct"] = False
    e = BL.build_entry(rec)
    assert e["FINAL_CLASSIFICATION"] == "invalid_evaluation"
    assert "e2e_true_but_top1_false" in (e["outcome_consistency_flags"] or [])
    rec2 = base_record("task_001", SYS_B)
    rec2["patch"]["syntax_valid"] = False
    e2 = BL.build_entry(rec2)
    assert e2["FINAL_CLASSIFICATION"] == "invalid_evaluation"
    assert "e2e_true_but_syntax_invalid" in (e2["outcome_consistency_flags"] or [])


def test_invalid_evaluation_when_no_signal():
    rec = base_record("task_001", SYS_B)
    rec["end_to_end_resolved"] = False
    rec["regression"]["hidden_tests_executed"] = False
    rec["regression"]["hidden_tests_passed"] = None
    rec["execution"]["status"] = "incomplete"
    assert BL.build_entry(rec)["FINAL_CLASSIFICATION"] == "invalid_evaluation"


def test_localization_not_evaluable_when_no_prediction():
    rec = base_record("task_001", SYS_B)
    rec["localization"]["predicted_file"] = None
    e = BL.build_entry(rec)
    assert e["localization_evaluable"] is False
    assert e["localization_top1"] is None  # never a hit nor a miss


# ===========================================================================
# build_ledger: repair accounting per system convention
# ===========================================================================
def test_multi_agent_repair_accounting():
    rec = base_record("task_001", "multi_agent")
    rec["repair"] = {"repair_attempt_count": 2, "attempts": 3,
                     "first_pass_resolved_hidden": False,
                     "repair_eligible": True, "repair_recovered": True}
    rec["end_to_end_resolved"] = True
    e = BL.build_entry(rec)
    assert e["repair_attempts"] == 2
    assert e["first_pass_resolved"] is False
    assert e["repair_recovered"] is True


def test_baseline_repair_accounting():
    rec = base_record("task_001", SYS_B)
    rec["repair"] = {"attempts": 4, "first_pass_resolved_hidden": False,
                     "retry_budget": 3}
    rec["end_to_end_resolved"] = True
    e = BL.build_entry(rec)
    assert e["repair_attempts"] == 3
    assert e["repair_eligible"] is True
    assert e["repair_recovered"] is True


def test_adaptive_repair_from_controller_block():
    rec = base_record("task_001", SYS_A)
    rec["adaptive"]["repair_attempts"] = 2
    rec["adaptive"]["repair_recovered"] = True
    rec["adaptive"]["repair_eligible"] = True
    rec["repair"]["first_pass_resolved_hidden"] = False
    e = BL.build_entry(rec)
    assert e["repair_attempts"] == 2
    assert e["repair_recovered"] is True
    assert e["first_pass_resolved"] is False


def test_adaptive_path_metadata_captured():
    e = BL.build_entry(base_record("task_001", SYS_A))
    assert e["final_path"] == "PATH_A"
    assert e["initial_path"] == "PATH_A"
    assert e["escalated"] is False
    assert e["difficulty_class"] == "simple"


def test_escalation_metadata():
    rec = base_record("task_001", SYS_A)
    rec["adaptive"].update({"initial_path": "PATH_A", "final_path": "PATH_B",
                            "escalated": True, "escalation_reason": "repair failed"})
    e = BL.build_entry(rec)
    assert e["escalated"] is True and e["final_path"] == "PATH_B"


# ===========================================================================
# paired_analysis: denominator tiers are code
# ===========================================================================
def _mk_entry(task, system, resolved, classification):
    return {"task_id": task, "system": system, "final_resolved": resolved,
            "FINAL_CLASSIFICATION": classification,
            "final_status": "error" if classification == "provider_failure" else "ok",
            "provider_failure": classification == "provider_failure"}


def _two_sys_entries():
    entries = []
    for t in ("task_001", "task_002"):
        entries.append(_mk_entry(t, SYS_A, True, "resolved"))
        entries.append(_mk_entry(t, SYS_B, True, "resolved"))
    return entries


def test_valid_tier_excludes_any_contaminated_side():
    entries = [
        _mk_entry("task_001", SYS_A, True, "resolved"),
        _mk_entry("task_001", SYS_B, True, "provider_failure"),
        _mk_entry("task_002", SYS_A, True, "resolved"),
        _mk_entry("task_002", SYS_B, True, "resolved"),
    ]
    out = PA.paired_analysis(entries, (SYS_A, SYS_B))
    tv = out["tiers"]["valid"]
    assert tv["tasks"] == ["task_002"]
    assert "provider_failure" in tv["excluded_tasks"]["task_001"]


def test_fatal_tier_keeps_contaminated_completed():
    entries = [
        _mk_entry("task_001", SYS_A, False, "genuine_agent_failure"),
        _mk_entry("task_001", SYS_B, True, "resolved"),
        _mk_entry("task_002", SYS_A, False, "provider_failure"),
        _mk_entry("task_002", SYS_B, True, "resolved"),
        _mk_entry("task_003", SYS_A, True, "resolved"),
        _mk_entry("task_003", SYS_B, False, "genuine_agent_failure"),
    ]
    out = PA.paired_analysis(entries, (SYS_A, SYS_B))
    tv = out["tiers"]["fatal"]
    assert tv["N"] == 2                      # task_002 fatal death excluded
    assert "task_001" in tv["tasks"] and "task_003" in tv["tasks"]


def test_all_tier_descriptive_only():
    entries = [
        _mk_entry("task_001", SYS_A, True, "resolved"),
        _mk_entry("task_001", SYS_B, False, "provider_failure"),
    ]
    out = PA.paired_analysis(entries, (SYS_A, SYS_B))
    assert out["tiers"]["all"]["N"] == 1
    assert out["tiers"]["all"]["outcome_counts"]["adaptive_multi_agent_only"] == 1


def test_missing_counterpart_recorded():
    entries = [_mk_entry("task_001", SYS_A, True, "resolved")]
    out = PA.paired_analysis(entries, (SYS_A, SYS_B))
    assert out["tiers"]["valid"]["unpaired"][0]["task_id"] == "task_001"
    assert out["tiers"]["valid"]["unpaired"][0]["missing_system"] == SYS_B


def test_duplicate_entry_raises():
    entries = [_mk_entry("task_001", SYS_B, True, "resolved"),
               _mk_entry("task_001", SYS_B, False, "resolved")]
    with pytest.raises(ValueError, match="duplicate"):
        PA.index_entries(entries)


def test_outcome_cells_carry_task_ids():
    entries = []
    for t in ("task_001", "task_002", "task_003", "task_004"):
        entries.append(_mk_entry(t, SYS_A, True, "resolved"))
        entries.append(_mk_entry(t, SYS_B, True, "resolved"))
    entries.append(_mk_entry("task_005", SYS_A, True, "resolved"))
    entries.append(_mk_entry("task_005", SYS_B, False, "genuine_agent_failure"))
    out = PA.paired_analysis(entries, (SYS_A, SYS_B))
    tv = out["tiers"]["valid"]
    assert tv["outcome_cells"]["both"] == ["task_001", "task_002", "task_003", "task_004"]
    assert tv["outcome_cells"]["adaptive_multi_agent_only"] == ["task_005"]


def test_tier_role_labels_present():
    out = PA.paired_analysis(_two_sys_entries(), (SYS_A, SYS_B))
    assert out["tiers"]["valid"]["role"].startswith("PRIMARY")
    assert "DESCRIPTIVE" in out["tiers"]["all"]["role"]


# ===========================================================================
# McNemar: exact two-sided values pinned by the audits
# ===========================================================================
@pytest.mark.parametrize("b,c,expected_p", [
    (1, 3, 0.625),      # archstrong final30 audit
    (3, 3, 1.0),        # V3 clean paired audit
    (0, 0, 1.0),
    (0, 1, 1.0),
    (0, 5, 0.0625),     # 2*(1/32) = 0.0625
    (1, 1, 1.0),
    (0, 8, 0.0078125),  # 2/256
])
def test_mcnemar_exact_values(b, c, expected_p):
    assert PA.mcnemar_exact_two_sided(b, c) == pytest.approx(expected_p)


def test_mcnemar_9v3_all30_audit_value():
    # Pinned to the exact closed form rather than a rounded decimal:
    # p = 2 * P(X<=3; Bin(12, .5)) = (C(12,0)+...+C(12,3)) / 2^11
    import math
    expected = sum(math.comb(12, i) for i in range(4)) / 2 ** 11
    assert PA.mcnemar_exact_two_sided(9, 3) == pytest.approx(expected)
    assert round(PA.mcnemar_exact_two_sided(9, 3), 3) == 0.146


def test_mcnemar_one_sided_is_half():
    assert round(PA.mcnemar_exact_two_sided(9, 3) / 2, 3) == 0.073


def test_mcnemar_symmetric():
    assert PA.mcnemar_exact_two_sided(9, 3) == PA.mcnemar_exact_two_sided(3, 9)


def test_denominator_rules_registry_complete():
    rules = PA.denominator_rules()
    for key in ("VALID_RUN", "FATAL_DEATH", "tier:valid", "tier:fatal", "tier:all"):
        assert key in rules


# ===========================================================================
# verify_manifest: immutable-input gate
# ===========================================================================
def test_verify_manifest_real_repo_passes():
    report = VM.verify_manifest()
    assert report["manifest_entries"] == 182
    assert report["verified"] == 182
    assert report["ok"] is True


def test_verify_manifest_detects_tampering(tmp_path):
    (tmp_path / "evaluation" / "hidden_tests").mkdir(parents=True)
    f1 = tmp_path / "evaluation" / "hidden_tests" / "test_eval_task_001.py"
    f2 = tmp_path / "evaluation" / "hidden_tests" / "test_eval_task_002.py"
    f1.write_text("A")
    f2.write_text("B")
    manifest = tmp_path / "manifest.txt"
    manifest.write_text(
        "evaluation/hidden_tests/test_eval_task_001.py|%s\n"
        "evaluation/hidden_tests/test_eval_task_002.py|%s\n"
        % (VM.sha256_file(f1), VM.sha256_file(f2)))
    assert VM.verify_manifest(manifest, repo_root=tmp_path)["ok"] is True
    f1.write_text("TAMPERED")
    report = VM.verify_manifest(manifest, repo_root=tmp_path)
    assert report["ok"] is False
    assert report["changed"][0]["path"] == "evaluation/hidden_tests/test_eval_task_001.py"


def test_verify_manifest_detects_missing_file(tmp_path):
    (tmp_path / "evaluation" / "hidden_tests").mkdir(parents=True)
    f1 = tmp_path / "evaluation" / "hidden_tests" / "test_eval_task_001.py"
    f1.write_text("A")
    manifest = tmp_path / "manifest.txt"
    manifest.write_text("evaluation/hidden_tests/test_eval_task_001.py|%s\n"
                        % VM.sha256_file(f1))
    f1.unlink()
    report = VM.verify_manifest(manifest, repo_root=tmp_path)
    assert report["ok"] is False and report["missing"]


def test_verify_manifest_detects_extra_frozen_scope_file(tmp_path):
    (tmp_path / "evaluation" / "hidden_tests").mkdir(parents=True)
    f1 = tmp_path / "evaluation" / "hidden_tests" / "test_eval_task_001.py"
    f1.write_text("A")
    manifest = tmp_path / "manifest.txt"
    manifest.write_text("evaluation/hidden_tests/test_eval_task_001.py|%s\n"
                        % VM.sha256_file(f1))
    (tmp_path / "evaluation" / "hidden_tests" / "test_eval_task_031.py").write_text("NEW")
    report = VM.verify_manifest(manifest, repo_root=tmp_path)
    assert report["ok"] is False
    assert report["extra"] == ["evaluation/hidden_tests/test_eval_task_031.py"]


def test_verify_manifest_ignores_pycache(tmp_path):
    (tmp_path / "evaluation" / "hidden_tests" / "__pycache__").mkdir(parents=True)
    f1 = tmp_path / "evaluation" / "hidden_tests" / "test_eval_task_001.py"
    f1.write_text("A")
    (tmp_path / "evaluation" / "hidden_tests" / "__pycache__" / "junk.pyc").write_text("x")
    manifest = tmp_path / "manifest.txt"
    manifest.write_text("evaluation/hidden_tests/test_eval_task_001.py|%s\n"
                        % VM.sha256_file(f1))
    assert VM.verify_manifest(manifest, repo_root=tmp_path)["ok"] is True


def test_verify_manifest_bom_tolerated(tmp_path):
    (tmp_path / "evaluation" / "hidden_tests").mkdir(parents=True)
    f1 = tmp_path / "evaluation" / "hidden_tests" / "test_eval_task_001.py"
    f1.write_text("A")
    manifest = tmp_path / "manifest.txt"
    manifest.write_bytes(("\ufeff" + "evaluation/hidden_tests/test_eval_task_001.py|%s\n"
                          % VM.sha256_file(f1)).encode("utf-8"))
    assert VM.verify_manifest(manifest, repo_root=tmp_path)["ok"] is True


def test_verify_manifest_rejects_duplicate_paths(tmp_path):
    f1 = tmp_path / "a.txt"
    f1.write_text("A")
    digest = VM.sha256_file(f1)
    manifest = tmp_path / "manifest.txt"
    manifest.write_text(f"a.txt|{digest}\na.txt|{digest}\n")
    with pytest.raises(ValueError, match="duplicate"):
        VM.parse_manifest(manifest)


# ===========================================================================
# validate_ledger: failure classes V01-V09
# ===========================================================================
def _write_pkg(out_dir: Path, entries, requested="laguna-s-2.1",
               paired=None, n_runs=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = {"entries": entries, "requested_model": requested}
    (out_dir / "task_ledger.json").write_text(json.dumps(ledger))
    (out_dir / "analysis.json").write_text(json.dumps(
        {"n_runs": len(entries) if n_runs is None else n_runs}))
    if paired is None and entries:
        systems = tuple(sorted({e["system"] for e in entries}))
        if len(systems) == 2:
            paired = PA.paired_analysis(entries, systems)
    (out_dir / "paired_analysis.json").write_text(json.dumps(paired or {"tiers": {}}))
    return out_dir


def _pkg_with_both_systems(tmp_path, tasks=("task_001", "task_002")):
    entries = []
    for t in tasks:
        entries.append(BL.build_entry(base_record(t, SYS_A)))
        entries.append(BL.build_entry(base_record(t, SYS_B)))
    return entries


def test_v01_missing_tasks(tmp_path):
    entries = _pkg_with_both_systems(tmp_path)  # only 2 of 30 tasks
    report = VL.validate_package(_write_pkg(tmp_path / "pkg", entries),
                                 expected_task_count=30)
    assert any(e.startswith("V01") for e in report["errors"])


def test_v02_duplicate_entries(tmp_path):
    e1 = BL.build_entry(base_record("task_001", SYS_B))
    report = VL.validate_package(_write_pkg(tmp_path, [e1, dict(e1)]))
    assert any(e.startswith("V02") for e in report["errors"])


def test_v03_missing_counterpart(tmp_path):
    entries = [BL.build_entry(base_record(t, SYS_B)) for t in ("task_001", "task_002")]
    report = VL.validate_package(_write_pkg(tmp_path, entries))
    assert any(e.startswith("V03") for e in report["errors"])


def test_v03_missing_whole_arm(tmp_path):
    entries = [BL.build_entry(base_record(t, SYS_B)) for t in ("task_001", "task_002")]
    report = VL.validate_package(_write_pkg(tmp_path, entries),
                                 expect_systems=[SYS_A, SYS_B])
    assert any("missing arms" in e and SYS_A in e for e in report["errors"])


def test_v04_budget_mismatch_surfaces_through_build(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for t in ("task_001", "task_002"):
        (raw / f"{t}_{SYS_A}.json").write_text(json.dumps(base_record(t, SYS_A)))
        (raw / f"{t}_{SYS_B}.json").write_text(json.dumps(base_record(t, SYS_B)))
    paths, _ = BL.build_package("budget_check", raw_dir=raw,
                                out_dir=tmp_path / "pkg", skip_manifest_gate=True)
    report = VL.validate_package(paths["task_ledger"].parent)
    assert any(e.startswith("V04") for e in report["errors"])


def test_v05_model_mismatch(tmp_path):
    e = BL.build_entry(base_record("task_001", SYS_B))
    e["served_model"] = ["some-other-model"]
    report = VL.validate_package(_write_pkg(tmp_path, [e]))
    assert any(e2.startswith("V05") for e2 in report["errors"])


def test_v06_contradiction_fails(tmp_path):
    from conftest import first_pass_contradiction_record
    e = BL.build_entry(first_pass_contradiction_record("task_001"))
    report = VL.validate_package(_write_pkg(tmp_path, [e]))
    assert any(e2.startswith("V06") for e2 in report["errors"])


def test_v07_outcome_inconsistency(tmp_path):
    rec = base_record("task_001", SYS_B)
    rec["regression"]["hidden_tests_executed"] = False  # resolved but never ran tests
    rec["regression"]["hidden_tests_passed"] = None
    rec["execution"]["status"] = "resolved"
    e = BL.build_entry(rec)
    report = VL.validate_package(_write_pkg(tmp_path, [e]))
    assert any("resolved_but_hidden_tests_not_executed" in e2 for e2 in report["errors"])


def test_v08_missing_primary_tier(tmp_path):
    e = BL.build_entry(base_record("task_001", SYS_B))
    report = VL.validate_package(_write_pkg(tmp_path, [e]))
    assert any(e2.startswith("V08") for e2 in report["errors"])


def test_v08_cell_sum_mismatch(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "task_ledger.json").write_text(json.dumps(
        {"entries": [], "requested_model": "laguna-s-2.1"}))
    (pkg / "analysis.json").write_text(json.dumps({"n_runs": 0}))
    (pkg / "paired_analysis.json").write_text(json.dumps({"tiers": {"valid": {
        "N": 2, "tasks": ["task_001", "task_002"],
        "outcome_counts": {"both": 20, "x_only": 1, "y_only": 1, "neither": 0}}}}))
    report = VL.validate_package(pkg)
    assert any("cells sum" in e for e in report["errors"])


def test_v08_n_runs_mismatch(tmp_path):
    entries = _pkg_with_both_systems(tmp_path)
    report = VL.validate_package(_write_pkg(tmp_path / "pkg", entries, n_runs=999))
    assert any("n_runs" in e for e in report["errors"])


def test_v09_stale_aggregates(tmp_path):
    entries = _pkg_with_both_systems(tmp_path)
    pkg = _write_pkg(tmp_path / "pkg", entries)
    agg = pkg / "aggregates"
    agg.mkdir()
    (agg / "aggregates.json").write_text(json.dumps(
        {"systems": {SYS_B: {"e2e_resolved": 0}}}))  # ledger says 2 -> stale
    report = VL.validate_package(pkg)
    assert any(err.startswith("V09") and "e2e_resolved" in err
               for err in report["errors"])


def test_v09_forensic_generator_flagged(tmp_path):
    entries = _pkg_with_both_systems(tmp_path)
    pkg = _write_pkg(tmp_path / "pkg", entries)
    led = json.loads((pkg / "task_ledger.json").read_text(encoding="utf-8"))
    led["generator"] = "evaluation/tmp/build_v3_ledger.py"
    (pkg / "task_ledger.json").write_text(json.dumps(led))
    report = VL.validate_package(pkg)
    assert any("V09" in e and "temporary" in e for e in report["errors"])


def test_v10_passed_count_is_warning_not_error(tmp_path):
    e = BL.build_entry(passed_count_conflict_record("task_001"))
    report = VL.validate_package(_write_pkg(tmp_path, [e]))
    assert not any(x.startswith("V10") for x in report["errors"])
    assert any(w.startswith("V10") for w in report["warnings"])


def test_fidelity_check_rebuilds_from_raw(tmp_path):
    rec = base_record("task_001", SYS_B)
    e = BL.build_entry(rec)
    pkg = _write_pkg(tmp_path, [e])
    raw = pkg / "raw"
    raw.mkdir()
    (raw / "task_001_baseline_b.json").write_text(json.dumps(rec))
    report = VL.validate_package(pkg)
    assert not [x for x in report["errors"] if "fidelity" in x]
    bad = dict(e)
    bad["final_resolved"] = not e["final_resolved"]
    (pkg / "task_ledger.json").write_text(json.dumps(
        {"entries": [bad], "requested_model": "laguna-s-2.1"}))
    report = VL.validate_package(pkg)
    assert any("fidelity" in x for x in report["errors"])


# ===========================================================================
# validate_report: claims and ledger-facts blocks
# ===========================================================================
def _report_pkg(tmp_path):
    entries = _pkg_with_both_systems(tmp_path, tasks=("task_001",))
    pkg = _write_pkg(tmp_path / "pkg", entries)
    return pkg


def test_report_claims_match(tmp_path):
    pkg = _report_pkg(tmp_path)
    report_md = tmp_path / "report.md"
    report_md.write_text("Result: <!--claim: baseline_b.final_resolved=1--> done")
    rep = VR.check_report(report_md, pkg)
    assert rep["ok"] is True and rep["n_mismatch"] == 0


def test_report_claims_mismatch_fails(tmp_path):
    pkg = _report_pkg(tmp_path)
    report_md = tmp_path / "report.md"
    report_md.write_text("Result: <!--claim: baseline_b.final_resolved=999-->")
    rep = VR.check_report(report_md, pkg)
    assert rep["ok"] is False
    assert rep["checks"][0]["status"] == "MISMATCH"


def test_report_unknown_fact_flagged(tmp_path):
    pkg = _report_pkg(tmp_path)
    report_md = tmp_path / "report.md"
    report_md.write_text("<!--claim: not_a_fact=1-->")
    rep = VR.check_report(report_md, pkg)
    assert rep["ok"] is False and rep["n_unknown"] == 1


def test_report_ledger_facts_block(tmp_path):
    pkg = _report_pkg(tmp_path)
    facts = VR.canonical_facts(pkg)
    payload = {k: facts[k] for k in ("baseline_b.n", "baseline_b.final_resolved",
                                     "paired_valid_N", "paired_valid_mcnemar_two_sided_p")}
    report_md = tmp_path / "report.md"
    report_md.write_text("```ledger-facts\n" + json.dumps(payload) + "\n```")
    rep = VR.check_report(report_md, pkg)
    assert rep["ok"] is True, rep["checks"]


def test_report_float_tolerance(tmp_path):
    pkg = _report_pkg(tmp_path)
    report_md = tmp_path / "report.md"
    report_md.write_text("<!--claim: paired_valid_mcnemar_two_sided_p=1.0000-->")
    rep = VR.check_report(report_md, pkg)
    assert rep["ok"] is True


def test_report_untagged_warns(tmp_path):
    pkg = _report_pkg(tmp_path)
    report_md = tmp_path / "report.md"
    report_md.write_text("Some prose report with numbers 25/30 in it, untagged.")
    rep = VR.check_report(report_md, pkg)
    assert rep["untagged_warning"] is not None
    assert rep["ok"] is True, "untagged legacy reports warn but do not fail"


# ===========================================================================
# build_package: end-to-end on synthetic data
# ===========================================================================
def test_build_package_three_artifacts(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for i in range(1, 4):
        t = f"task_{i:03d}"
        (raw / f"{t}_{SYS_A}.json").write_text(json.dumps(base_record(t, SYS_A)))
        (raw / f"{t}_{SYS_B}.json").write_text(json.dumps(base_record(t, SYS_B)))
    paths, warnings = BL.build_package("synthetic_smoke", raw_dir=raw,
                                       out_dir=tmp_path / "pkg", skip_manifest_gate=True)
    assert paths["task_ledger"].is_file()
    assert paths["analysis"].is_file()
    assert paths["paired_analysis"].is_file()
    assert warnings == []
    ledger = json.loads(paths["task_ledger"].read_text(encoding="utf-8"))
    assert len(ledger["entries"]) == 6
    pa = json.loads(paths["paired_analysis"].read_text(encoding="utf-8"))
    tv = pa["tiers"]["valid"]
    assert tv["N"] == 3 and tv["outcome_counts"]["both"] == 3
    assert tv["mcnemar_exact_two_sided_p"] == 1.0
    analysis = json.loads(paths["analysis"].read_text(encoding="utf-8"))
    assert analysis["n_runs"] == 6
    assert analysis["retry_budget_disclosure"]["budgets_equal_across_arms"] is False


def test_build_package_aborts_on_failed_manifest_gate(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "task_001_baseline_b.json").write_text(
        json.dumps(base_record("task_001", SYS_B)))
    import verify_manifest as VM2
    monkeypatch.setattr(VM2, "verify_manifest",
                        lambda *a, **k: {"ok": False, "changed": [{"path": "x"}],
                                         "missing": [], "extra": None})
    with pytest.raises(SystemExit, match="frozen benchmark inputs failed"):
        BL.build_package("gate_check", raw_dir=raw, out_dir=tmp_path / "pkg",
                         skip_manifest_gate=False)


def test_build_package_skips_unparseable_raw_with_warning(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "task_001_baseline_b.json").write_text("{not json")
    (raw / "task_001_adaptive_multi_agent.json").write_text(
        json.dumps(base_record("task_001", SYS_A)))
    paths, warnings = BL.build_package("synthetic_bad_json", raw_dir=raw,
                                       out_dir=tmp_path / "pkg", skip_manifest_gate=True)
    assert warnings and "unparseable" in warnings[0]
    ledger = json.loads(paths["task_ledger"].read_text(encoding="utf-8"))
    assert len(ledger["entries"]) == 1


def test_build_package_contamination_precedence_end_to_end(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "task_001_adaptive_multi_agent.json").write_text(json.dumps(
        provider_502_record("task_001", SYS_A, fatal=False)))   # completed, contaminated
    (raw / "task_001_baseline_b.json").write_text(json.dumps(
        base_record("task_001", SYS_B)))
    paths, _ = BL.build_package("synthetic_contamination", raw_dir=raw,
                                out_dir=tmp_path / "pkg", skip_manifest_gate=True)
    pa = json.loads(paths["paired_analysis"].read_text(encoding="utf-8"))
    # valid tier: contaminated adaptive run excluded
    tv = pa["tiers"]["valid"]
    assert tv["N"] == 0 and "task_001" in tv["excluded_tasks"]
    # fatal tier: completed run kept
    assert pa["tiers"]["fatal"]["N"] == 1
    assert pa["tiers"]["fatal"]["outcome_counts"]["baseline_b_only"] == 1
    analysis = json.loads(paths["analysis"].read_text(encoding="utf-8"))
    assert analysis["contamination"]["provider_contaminated_count"] == 1
    assert analysis["contamination"]["genuine_infrastructure_failure_count"] == 0
