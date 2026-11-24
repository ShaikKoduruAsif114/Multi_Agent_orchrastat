"""
Tests for the Adaptive V4 preflight gate, frozen config contract, run
manifest, and fail-closed runner enforcement.

These tests run NO benchmark tasks and touch NO historical result
directories; the runner-enforcement test exits before any execution.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import preflight_v4 as PF                       # noqa: E402

REPO = Path(__file__).resolve().parents[2]
V4_CONFIG = REPO / "evaluation" / "configs" / "benchmark_v4.yaml"


# ===========================================================================
# Preflight on the real V4 config: every check passes
# ===========================================================================
def test_v4_preflight_all_pass():
    ok, results, ctx = PF.run_preflight()
    assert ok, [r for r in results if not r["ok"]]
    codes = {r["code"] for r in results}
    assert codes >= {"P01", "P02", "P03", "P04", "P05", "P06", "P07", "P08",
                     "P09", "P10"}
    assert ctx["retry_budget"] == 2
    assert ctx["execution_mode"] == "subprocess"
    assert ctx["timeout_seconds"] == 120
    assert ctx["code_commit_sha"]
    assert len(ctx["benchmark_manifest_sha256"]) == 64


def test_v4_preflight_retry_budget_identical():
    ok, results, _ = PF.run_preflight()
    p05 = next(r for r in results if r["code"] == "P05")
    assert p05["ok"] is True
    assert "IDENTICAL" in p05["detail"]


def test_v4_preflight_records_dirty_git_state():
    ok, results, ctx = PF.run_preflight()
    assert "git_dirty_tracked_files" in ctx
    assert ctx["git_dirty_tracked_files"] is not None  # informational


# ===========================================================================
# Frozen config contract
# ===========================================================================
def _load_v4_config():
    return yaml.safe_load(V4_CONFIG.read_text(encoding="utf-8"))


def test_v4_config_thirty_tasks():
    config = _load_v4_config()
    assert len(config["tasks"]) == 30
    assert all(t.startswith("task_") for t in config["tasks"])


def test_v4_config_two_enabled_systems():
    config = _load_v4_config()
    enabled = [s["name"] for s in config["systems"] if s.get("enabled", True)]
    assert sorted(enabled) == ["adaptive_multi_agent", "baseline_b"]


def test_v4_config_identical_budget_both_arms():
    config = _load_v4_config()
    env = config["env_overrides"]
    assert config["execution_settings"]["retry_budget"] == 2
    assert env["AGENT_MAX_RETRIES"] == "2"      # baseline_b
    assert env["AGENT_REPAIR_BUDGET"] == "2"    # adaptive pin
    assert env["AGENT_MAX_RETRIES"] == env["AGENT_REPAIR_BUDGET"]


def test_v4_config_model_pin():
    config = _load_v4_config()
    assert config["model"] == {"provider": "nara", "name": "laguna-s-2.1",
                               "temperature": 0}
    env = config["env_overrides"]
    assert env["PROVIDER"] == "nara"
    assert env["NARAROUTER_MODEL"] == "laguna-s-2.1"
    assert env["AGENT_STRICT_LLM"] == "1"


def test_v4_config_requires_evaluate_and_gate():
    config = _load_v4_config()
    es = config["evaluation_settings"]
    assert es["require_preflight"] is True
    assert es["require_manifest_gate"] is True
    assert es["require_evaluate"] is True
    assert es["evaluator_version"] == "1.0.0"


def test_v4_config_timeout_policy_identical():
    config = _load_v4_config()
    assert config["execution_settings"]["timeout_seconds"] == 120
    assert config["env_overrides"]["NARA_LLM_TIMEOUT"] == "120"


# ===========================================================================
# Run manifest generation + verification
# ===========================================================================
def test_v4_run_manifest_generated_and_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(PF, "V4_MANIFEST_PATH", tmp_path / "v4_run_manifest.json")
    ok, results, ctx = PF.run_preflight()
    assert ok
    manifest = PF.generate_manifest(ctx)
    for field in ("provider", "model", "retry_budget", "benchmark_manifest_sha256",
                  "code_commit_sha", "execution_mode", "timeout_seconds",
                  "evaluator_version", "primary_evaluation", "fail_closed_rules"):
        assert field in manifest, f"run manifest missing {field}"
    assert manifest["model"] == "laguna-s-2.1"
    assert manifest["provider"] == "nara"
    assert manifest["retry_budget"]["adaptive_multi_agent"] == 2
    assert manifest["retry_budget"]["baseline_b"] == 2
    assert manifest["retry_budget"]["identical"] is True
    assert manifest["benchmark_manifest_entries"] == 182
    # primary evaluation defined BEFORE the run
    pe = manifest["primary_evaluation"]
    assert "clean_paired_set" in pe and "tier:valid" in pe["clean_paired_set"]
    assert "McNemar exact two-sided" in pe["primary_endpoint"]
    assert len(pe["secondary"]) == 8


def test_v4_run_manifest_verification(tmp_path, monkeypatch):
    monkeypatch.setattr(PF, "V4_MANIFEST_PATH", tmp_path / "v4_run_manifest.json")
    ok, results, ctx = PF.run_preflight()
    PF.generate_manifest(ctx)
    m_ok, detail = PF.verify_manifest_file()
    assert m_ok is True, detail


def test_v4_run_manifest_detects_commit_change(tmp_path, monkeypatch):
    monkeypatch.setattr(PF, "V4_MANIFEST_PATH", tmp_path / "v4_run_manifest.json")
    ok, results, ctx = PF.run_preflight()
    PF.generate_manifest(ctx)
    # simulate a commit change
    manifest = json.loads((tmp_path / "v4_run_manifest.json").read_text(encoding="utf-8"))
    manifest["code_commit_sha"] = "0" * 40
    (tmp_path / "v4_run_manifest.json").write_text(json.dumps(manifest))
    m_ok, detail = PF.verify_manifest_file()
    assert m_ok is False
    assert "code commit changed" in detail


def test_v4_run_manifest_detects_budget_change(tmp_path, monkeypatch):
    monkeypatch.setattr(PF, "V4_MANIFEST_PATH", tmp_path / "v4_run_manifest.json")
    ok, results, ctx = PF.run_preflight()
    PF.generate_manifest(ctx)
    manifest = json.loads((tmp_path / "v4_run_manifest.json").read_text(encoding="utf-8"))
    manifest["retry_budget"]["adaptive_multi_agent"] = 3
    (tmp_path / "v4_run_manifest.json").write_text(json.dumps(manifest))
    m_ok, _ = PF.verify_manifest_file()
    assert m_ok is False


def test_v4_run_manifest_missing_fails_verification(tmp_path, monkeypatch):
    monkeypatch.setattr(PF, "V4_MANIFEST_PATH", tmp_path / "v4_run_manifest.json")
    m_ok, detail = PF.verify_manifest_file()
    assert m_ok is False and "no V4 run manifest" in detail


# ===========================================================================
# Preflight failure detection on mutated configs
# ===========================================================================
def _preflight_config(tmp_path, mutate):
    config = _load_v4_config()
    mutate(config)
    p = tmp_path / "mutated_v4.yaml"
    p.write_text(yaml.safe_dump(config), encoding="utf-8")
    return p


def test_preflight_fails_on_budget_mismatch(tmp_path):
    def mutate(c):
        c["env_overrides"]["AGENT_MAX_RETRIES"] = "3"   # baseline gets 3
    ok, results, _ = PF.run_preflight(_preflight_config(tmp_path, mutate))
    assert ok is False
    p05 = next(r for r in results if r["code"] == "P05")
    assert p05["ok"] is False
    assert "MISMATCH INVALIDATES" in p05["detail"]


def test_preflight_fails_on_missing_task_file(tmp_path):
    def mutate(c):
        c["tasks"][0] = "task_999_nonexistent.json"
    ok, results, _ = PF.run_preflight(_preflight_config(tmp_path, mutate))
    assert ok is False
    assert any(r["code"] == "P03" and not r["ok"] for r in results)


def test_preflight_fails_on_wrong_model(tmp_path):
    def mutate(c):
        c["env_overrides"]["NARAROUTER_MODEL"] = "some-other-model"
    ok, results, _ = PF.run_preflight(_preflight_config(tmp_path, mutate))
    assert ok is False
    assert any(r["code"] == "P04" and not r["ok"] for r in results)


def test_preflight_fails_on_third_system(tmp_path):
    def mutate(c):
        c["systems"].append({"name": "baseline_a", "module": "x.py", "enabled": True})
    ok, results, _ = PF.run_preflight(_preflight_config(tmp_path, mutate))
    assert ok is False
    assert any(r["code"] == "P02" and not r["ok"] for r in results)


def test_preflight_fails_on_missing_config(tmp_path):
    ok, results, _ = PF.run_preflight(tmp_path / "nope.yaml")
    assert ok is False
    assert results[0]["code"] == "P01" and results[0]["ok"] is False


# ===========================================================================
# Adaptive controller: budget pin + V3 preservation
# ===========================================================================
def test_adaptive_budget_pin_roundtrip():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "baseline_adaptive_pin_test", REPO / "evaluation" / "baselines" / "baseline_adaptive.py")
    # importing the full module pulls the agent package; instead verify the
    # pin logic textually + pin semantics via a minimal stub harness:
    src = (REPO / "evaluation" / "baselines" / "baseline_adaptive.py").read_text(encoding="utf-8")
    assert 'pinned = os.getenv("AGENT_REPAIR_BUDGET", "").strip()' in src
    assert "if pinned:\n            return int(pinned)" in src
    # V3 per-path fallback intact (preserved behavior when pin unset)
    assert 'if self.final_path == "PATH_A":\n            return 1' in src
    assert 'elif self.final_path == "PATH_B":\n            return 2' in src
    assert 'os.getenv("AGENT_MAX_RETRIES", "3")' in src


def test_adaptive_pin_semantics_via_stub(monkeypatch):
    """Exercise the pinned max_repair_attempts decision in isolation."""
    # replicate the pinned method exactly as implemented
    import os
    def max_repair_attempts(self=None, final_path="PATH_A"):
        pinned = os.getenv("AGENT_REPAIR_BUDGET", "").strip()
        if pinned:
            return int(pinned)
        if final_path == "PATH_A":
            return 1
        elif final_path == "PATH_B":
            return 2
        return int(os.getenv("AGENT_MAX_RETRIES", "3"))

    monkeypatch.setenv("AGENT_REPAIR_BUDGET", "2")
    assert max_repair_attempts(final_path="PATH_A") == 2
    assert max_repair_attempts(final_path="PATH_B") == 2
    assert max_repair_attempts(final_path="PATH_C") == 2
    monkeypatch.delenv("AGENT_REPAIR_BUDGET")
    monkeypatch.setenv("AGENT_MAX_RETRIES", "3")
    assert max_repair_attempts(final_path="PATH_A") == 1   # V3 behavior
    assert max_repair_attempts(final_path="PATH_B") == 2   # V3 behavior
    assert max_repair_attempts(final_path="PATH_C") == 3   # V3 behavior


def test_adaptive_first_pass_true_recording():
    src = (REPO / "evaluation" / "baselines" / "baseline_adaptive.py").read_text(encoding="utf-8")
    assert 'first_pass_resolved_hidden": initial_hidden_passed' in src


# ===========================================================================
# Runner enforcement (fail closed, no execution)
# ===========================================================================
def test_runner_refuses_v4_without_evaluate_flag(tmp_path):
    """run_benchmark.py must exit(1) on the V4 config without --evaluate.

    Safety: the config copy has NO valid task file, so even if the gate
    failed this test could never launch a real run (no tasks -> exit 1).
    """
    import subprocess
    import yaml as _yaml
    guard_cfg = tmp_path / "benchmark_v4_guard.yaml"
    cfg = _yaml.safe_load(V4_CONFIG.read_text(encoding="utf-8"))
    cfg["tasks"] = ["task_000_guard_no_such_file.json"]
    guard_cfg.write_text(_yaml.safe_dump(cfg), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(REPO / "evaluation" / "run_benchmark.py"),
         "--config", str(guard_cfg)],
        capture_output=True, text=True, timeout=60)
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "REQUIRES the canonical evaluation pipeline" in combined
    assert "BENCHMARK:" not in combined, "runner started a run without --evaluate!"


def test_runner_refuses_v4_with_stale_manifest(tmp_path, monkeypatch, capsys):
    """With --evaluate but a stale/missing run manifest, the runner must
    exit(1) before executing anything. In-process with the manifest check
    monkeypatched to fail: NO benchmark task can ever start here."""
    import run_benchmark as RB
    import preflight_v4 as PF2

    def _no_run_allowed(*a, **k):
        raise AssertionError("run_benchmark() was reached — enforcement regressed!")

    monkeypatch.setattr(RB, "run_benchmark", _no_run_allowed)
    monkeypatch.setattr(PF2, "verify_manifest_file",
                        lambda: (False, "simulated stale manifest"))
    monkeypatch.setattr(sys, "argv",
                        ["run_benchmark.py",
                         "--config", "evaluation/configs/benchmark_v4.yaml",
                         "--evaluate"])
    with pytest.raises(SystemExit) as exc_info:
        RB.main()
    assert exc_info.value.code == 1
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "run manifest not current" in out
    assert "simulated stale manifest" in out
