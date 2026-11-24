"""
Shared fixtures for the evaluation tooling test suite.

Synthetic raw records mirror the real benchmark schema (adaptive controller
block + baseline repair block). Nothing here touches the real experiment
directories; integration tests that read real artifacts are READ-ONLY.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "evaluation"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

V3_EXP = "nara_laguna_adaptive_v3_final_20260910"
V3_DIR = EVAL_DIR / "results" / V3_EXP
ARCH_EXP = "nara_laguna_archstrong_final30_final_20260910"
ARCH_DIR = EVAL_DIR / "results" / ARCH_EXP

SYSTEMS = ("adaptive_multi_agent", "baseline_b")
TASKS = [f"task_{i:03d}" for i in range(1, 31)]


def base_record(task_id: str, system: str) -> dict:
    """A clean, resolved raw record in the real benchmark schema."""
    rec = {
        "task_id": task_id,
        "system": system,
        "end_to_end_resolved": True,
        "provider": {
            "provider": "nara",
            "requested_model": "laguna-s-2.1",
            "served_models": ["laguna-s-2.1"],
            "contamination_detected": False,
            "contamination": [],
        },
        "localization": {
            "predicted_file": "src/calculator.py",
            "gold_file": "src/calculator.py",
            "top1_correct": True,
            "top3_correct": True,
            "hallucinated_file": False,
            "valid": True,
        },
        "patch": {
            "generated": True,
            "is_placeholder": False,
            "syntax_valid": True,
            "patch_apply_success": True,
        },
        "tests": {
            "generated": True,
            "generated_tests_executed": True,
            "generated_tests_passed": True,
        },
        "regression": {
            "hidden_tests_executed": True,
            "hidden_tests_passed": True,
            "hidden_tests_total": 18,
            "hidden_tests_passed_count": 18,
        },
        "repair": {
            "attempts": 1,
            "first_pass_resolved_hidden": True,
            "retry_budget": 3,
        },
        "execution": {
            "status": "resolved",
            "failure_category": None,
            "latency_seconds": 20.0,
            "llm_calls": 3,
            "input_tokens": 700,
            "output_tokens": 300,
            "total_tokens": 1000,
        },
        "cost": {"estimated_usd": 0.0008},
    }
    if system == "adaptive_multi_agent":
        rec["adaptive"] = {
            "difficulty_score": 3.5,
            "difficulty_class": "simple",
            "initial_path": "PATH_A",
            "final_path": "PATH_A",
            "escalated": False,
            "escalation_reason": None,
            "path_reason": "Simple task",
            "stage_calls": {},
            "first_pass_resolved": True,
            "repair_eligible": False,
            "repair_attempts": 0,
            "repair_recovered": False,
            "final_resolved": True,
        }
        rec["repair"]["retry_budget"] = 1
    return rec


def provider_502_record(task_id: str, system: str, fatal: bool = True) -> dict:
    """Record whose LLM call failed with 'error code: 502'.

    fatal=True  -> execution.status='error' (pipeline died: FATAL_DEATH)
    fatal=False -> run completed (contaminated-but-completed)
    """
    d = base_record(task_id, system)
    d["provider"]["contamination_detected"] = True
    d["provider"]["contamination"] = [{
        "stage": "research",
        "error": "Error code: 502 - upstream temporarily unavailable",
        "failure_category": "provider_server_error",
    }]
    d["end_to_end_resolved"] = False
    d["regression"] = {
        "hidden_tests_executed": False,
        "hidden_tests_passed": None,
        "hidden_tests_total": None,
        "hidden_tests_passed_count": None,
    }
    if fatal:
        d["execution"]["status"] = "error"
        d["execution"]["error_message"] = "Error code: 502 - upstream temporarily unavailable"
        d["execution"]["llm_calls"] = 0
        d["execution"]["total_tokens"] = 0
    return d


def upstream_error_200_record(task_id: str, system: str) -> dict:
    """HTTP-200-wrapped upstream_error payload (V3 task_008/010 class)."""
    d = base_record(task_id, system)
    d["end_to_end_resolved"] = False
    d["execution"]["status"] = "error"
    d["execution"]["error_message"] = (
        '{"error": {"type": "upstream_error", "request_id": "req_test"}, '
        '"message": "model temporarily unavailable"}'
    )
    d["execution"]["llm_calls"] = 0
    d["execution"]["total_tokens"] = 0
    return d


def null_attempts_record(task_id: str, system: str) -> dict:
    """Baseline error run recording repair.attempts=null (must not crash)."""
    d = provider_502_record(task_id, system, fatal=True)
    d["repair"]["attempts"] = None
    d["repair"]["first_pass_resolved_hidden"] = None
    return d


def first_pass_contradiction_record(task_id: str) -> dict:
    """Adaptive record whose controller block claims first_pass_resolved=false
    while hidden tests record a first-pass success (V3 task_001 class)."""
    d = base_record(task_id, "adaptive_multi_agent")
    d["adaptive"]["first_pass_resolved"] = False
    d["adaptive"]["repair_eligible"] = True
    d["adaptive"]["repair_attempts"] = 1
    d["adaptive"]["repair_recovered"] = True
    d["repair"]["first_pass_resolved_hidden"] = True  # canonical source
    return d


def passed_count_conflict_record(task_id: str) -> dict:
    """Run-level passed=true but passed_count=0 (V3 adaptive quirk)."""
    d = base_record(task_id, "adaptive_multi_agent")
    d["regression"]["hidden_tests_passed_count"] = 0
    return d


@pytest.fixture(scope="session")
def eval_dir() -> Path:
    return EVAL_DIR


@pytest.fixture(scope="session")
def v3_dir() -> Path:
    assert V3_DIR.is_dir(), f"missing real V3 experiment dir {V3_DIR}"
    return V3_DIR


@pytest.fixture(scope="session")
def arch_dir() -> Path:
    return ARCH_DIR
