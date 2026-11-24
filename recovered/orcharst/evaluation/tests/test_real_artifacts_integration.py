"""
Integration tests against the REAL Adaptive V3 artifacts.

These tests are strictly READ-ONLY: they validate the production tooling
against the real experiment package and prove the immutable record has not
been touched by the tooling. Nothing is rebuilt, nothing is rerun.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_ledger as BL                      # noqa: E402
import paired_analysis as PA                   # noqa: E402
import validate_ledger as VL                   # noqa: E402
from conftest import V3_DIR, V3_EXP            # noqa: E402

SYS_A = "adaptive_multi_agent"
SYS_B = "baseline_b"

# Pre-tooling snapshot taken before any evaluation/ tool was written
# (evaluation/tmp/v3_pre_tooling_hashes.json): file -> sha256.
SNAPSHOT = json.loads(
    (Path(__file__).resolve().parents[2] / "evaluation" / "tmp" /
     "v3_pre_tooling_hashes.json").read_text(encoding="utf-8"))


def test_v3_package_exists():
    for name in ("task_ledger.json", "FINAL_REPORT_CORRECTED.md",
                 "resume_metrics_corrected.md"):
        assert (V3_DIR / name).is_file(), f"missing corrected artifact {name}"


def test_v3_corrected_report_numbers_reproduce_from_raw():
    """The corrected report's headline numbers must reproduce from the raw
    JSONs through the PRODUCTION modules (not the forensic scripts)."""
    ledger = json.loads((V3_DIR / "task_ledger.json").read_text(encoding="utf-8"))
    entries = ledger["entries"]
    pa = PA.paired_analysis(entries, (SYS_A, SYS_B))
    tiers = pa["tiers"]

    # primary (fatal tier in corrected report; N=22)
    tf = tiers["fatal"]
    assert tf["N"] == 22
    assert tf["outcome_counts"] == {"both": 16, SYS_A + "_only": 3,
                                    SYS_B + "_only": 3, "neither": 0}
    assert tf["mcnemar_exact_two_sided_p"] == 1.0
    # strict tier (valid-only; N=21)
    tv = tiers["valid"]
    assert tv["N"] == 21
    assert tv["outcome_counts"] == {"both": 16, SYS_A + "_only": 3,
                                    SYS_B + "_only": 2, "neither": 0}
    # all-30 confounded descriptive
    assert tiers["all"]["outcome_counts"] == {"both": 16, SYS_A + "_only": 9,
                                              SYS_B + "_only": 3, "neither": 2}
    assert round(tiers["all"]["mcnemar_exact_two_sided_p"], 3) == 0.146

    # excluded task IDs exactly as documented
    assert sorted(tiers["valid"]["excluded_tasks"]) == [
        "task_003", "task_004", "task_008", "task_010", "task_017", "task_018",
        "task_020", "task_023", "task_024"]


def test_v3_efficiency_numbers_reproduce_from_raw():
    ledger = json.loads((V3_DIR / "task_ledger.json").read_text(encoding="utf-8"))
    entries = ledger["entries"]
    valid_tasks = set(PA.paired_analysis(entries, (SYS_A, SYS_B))
                      ["tiers"]["fatal"]["tasks"])
    analysis = BL.efficiency_block(entries, valid_tasks, valid_tasks)
    a = analysis[SYS_A]["runs_with_output"]
    b = analysis[SYS_B]["runs_with_output"]
    assert a["llm_calls_mean"] == pytest.approx(2.107, abs=5e-4)
    assert b["llm_calls_mean"] == pytest.approx(2.696, abs=5e-4)
    assert a["total_tokens_mean"] == pytest.approx(1112.6, abs=0.05)
    assert b["total_tokens_mean"] == pytest.approx(1160.5, abs=0.05)
    assert a["latency_seconds_mean"] == pytest.approx(17.37, abs=5e-3)
    assert b["latency_seconds_mean"] == pytest.approx(20.91, abs=5e-3)
    assert a["cost_mean"] == pytest.approx(0.000714, abs=1e-6)
    assert b["cost_mean"] == pytest.approx(0.000766, abs=1e-6)


def test_v3_contamination_counts():
    ledger = json.loads((V3_DIR / "task_ledger.json").read_text(encoding="utf-8"))
    entries = ledger["entries"]
    contaminated = [(e["task_id"], e["system"]) for e in entries if e["provider_failure"]]
    assert len(contaminated) == 10, "10/60 provider-contaminated runs (V3 audit)"
    infra = [e for e in entries if e["FINAL_CLASSIFICATION"] == "infrastructure_failure"]
    assert infra == [], "zero genuine infrastructure failures (V3 audit)"


def test_v3_original_dir_has_no_canonical_analysis_artifacts():
    """True finding from the V3 audit: only the forensic task_ledger.json was
    ever written; analysis.json / paired_analysis.json do not exist."""
    assert (V3_DIR / "task_ledger.json").is_file()
    assert not (V3_DIR / "analysis.json").is_file()
    assert not (V3_DIR / "paired_analysis.json").is_file()


def test_v3_rebuilt_package_fails_with_known_v3_defects(tmp_path):
    """Rebuild the package from the real V3 raw JSONs into a temp dir with the
    PRODUCTION builder, then validate: it must fail for exactly the documented
    V3 defects — the runtime check that would have caught them before publish."""
    paths, _ = BL.build_package(V3_EXP, raw_dir=V3_DIR / "raw",
                                out_dir=tmp_path / "pkg")
    report = VL.validate_package(paths["task_ledger"].parent,
                                 expected_task_count=30)
    codes = {e.split(":")[0] for e in report["errors"]}
    assert "V04" in codes, "unequal retry budgets must be detected"
    assert "V06" in codes, "first-pass contradictions must be detected"
    assert "V07" in codes, "recovery-without-failure inconsistencies must be detected"
    unexpected = codes - {"V04", "V06", "V07"}
    assert not unexpected, f"unexpected validation errors: {report['errors'][:5]}"
    # and the passed-count quirk must surface as a disclosed warning
    assert any(w.startswith("V10") for w in report["warnings"])
    # rebuilt tier numbers must equal the forensic ledger's
    pa = json.loads(paths["paired_analysis"].read_text(encoding="utf-8"))
    assert pa["tiers"]["fatal"]["N"] == 22
    assert pa["tiers"]["fatal"]["outcome_counts"] == {
        "both": 16, SYS_A + "_only": 3, SYS_B + "_only": 3, "neither": 0}


def test_v3_immutability_all_files_byte_identical():
    """Every V3 artifact file is byte-identical to the pre-tooling snapshot."""
    mismatches = []
    current = {}
    repo_root = Path(__file__).resolve().parents[2]
    for p in sorted(V3_DIR.rglob("*")):
        if p.is_file():
            rel = p.relative_to(repo_root).as_posix()
            current[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    for f, digest in SNAPSHOT.items():
        if f not in current:
            mismatches.append(f"MISSING {f}")
        elif current[f] != digest:
            mismatches.append(f"CHANGED {f}")
    for f in current:
        if f not in SNAPSHOT:
            mismatches.append(f"ADDED {f}")
    assert not mismatches, \
        f"immutable V3 record was touched: {mismatches[:10]}"


def test_archstrong_package_ledger_agrees_with_report_values():
    """The archstrong final30 ledger (canonical 20260910 run) must reproduce
    its audited headline numbers: 17/30 vs 24/30, paired N=24, p=0.625."""
    arch = Path(__file__).resolve().parents[1] / "results" / \
        "nara_laguna_archstrong_final30_final_20260910"
    ledger = json.loads((arch / "task_ledger.json").read_text(encoding="utf-8"))
    entries = ledger["entries"]
    systems = tuple(sorted({e["system"] for e in entries}))
    assert systems == ("baseline_b", "multi_agent")
    ma = [e for e in entries if e["system"] == "multi_agent"]
    bb = [e for e in entries if e["system"] == "baseline_b"]
    assert sum(1 for e in ma if e["final_resolved"]) == 17
    assert sum(1 for e in bb if e["final_resolved"]) == 24
    pa = PA.paired_analysis(entries, systems)
    tv = pa["tiers"]["valid"]
    assert tv["N"] == 24
    counts = tv["outcome_counts"]
    assert counts["both"] == 16 and counts["neither"] == 4
    assert tv["mcnemar_exact_two_sided_p"] == 0.625
    assert tv["mcnemar_one_sided_p"] == 0.3125
