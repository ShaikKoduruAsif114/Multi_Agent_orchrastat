# Adaptive V4 Controlled Experiment — Pre-Registered Protocol

**Status:** FROZEN before the run. This document, `benchmark_v4.yaml`, the
preflight run manifest, and the canonical evaluator (`build_ledger.py`,
`validate_ledger.py`, `paired_analysis.py`) together define the experiment.
No change after data collection begins without an explicit amendment note.

**Research question.** Under corrected experimental controls, does the
adaptive multi-agent controller resolve more tasks than baseline_b?

**What V4 does NOT change.** The adaptive controller logic is V3-preserved
(difficulty estimator, path selection, escalation, failure classification —
pinned by preflight check P10). V4 isolates the effect of corrected controls
and the permanent evaluation tooling. No controller optimization before V5.

---

## 1. Frozen configuration

| Element | Value |
|---|---|
| Tasks | 30 frozen benchmark tasks (`task_001`…`task_030`) |
| Provider / model | NaraRouter / `laguna-s-2.1` only (strict LLM mode) |
| Arms | `adaptive_multi_agent` vs `baseline_b` |
| Retry budget | **2 — IDENTICAL for both arms** (`AGENT_REPAIR_BUDGET=2` pins adaptive; `AGENT_MAX_RETRIES=2` drives baseline_b) |
| Execution environment | identical env_overrides both arms; `NARA_LLM_TIMEOUT=120`; sandbox `subprocess`; temperature 0 |
| Hidden tests | identical frozen set (182-input manifest gate, before AND after the run) |
| Approval mode | identical: eval_mode, no human-in-the-loop, either arm |
| Timeout policy | identical: per-call 30s code/repair stages, 120s task-level LLM timeout, hidden-test subprocess 30s |
| Post-run pipeline | mandatory `--evaluate` (runner refuses V4 runs without it) |
| Preflight | mandatory current run manifest (P01–P10) |

Retry budget note: V3's flaw was asymmetric budgets (adaptive per-path 1/2/3
vs baseline 3). The adaptive budget pin (`AGENT_REPAIR_BUDGET`) is env-gated:
unset = exact V3 behavior (historical comparability), set = pinned controlled
budget. Preflight P10 verifies both properties.

## 2. Primary evaluation (defined BEFORE the run)

Primary denominator — **clean paired set (tier `valid`)**: tasks where BOTH
arms' runs have `FINAL_CLASSIFICATION ∈ {resolved, genuine_agent_failure}`
(i.e., uncontaminated usable outcomes). Contaminated-but-completed runs are
kept only in the separately-labeled `fatal` sensitivity tier; the confounded
`all` tier is descriptive only.

| Metric | Definition / denominator |
|---|---|
| Final resolution (PRIMARY) | resolved count on clean paired set; exact two-sided McNemar on discordant cells |
| First-pass resolution | `repair.first_pass_resolved_hidden` (true first-pass outcome; V3 contradiction fixed at source); among valid runs, budget 2 both arms |
| LLM calls | mean over `runs_with_output` (≥1 LLM call) |
| Tokens | mean/total over `runs_with_output` |
| Latency | mean/median over `runs_with_output` (all-runs means forbidden — dead error runs pollute them) |
| Cost | mean/total over `runs_with_output`; cost-per-resolved over valid resolved runs |
| Localization | top-1 correct among evaluable runs (prediction recorded); hallucinations counted separately |
| Provider contamination | separate class, beats generic runner/infra labels; includes `provider.contamination`-only records and HTTP-200-wrapped `upstream_error`; fatal (died) vs completed runs distinguished |
| Repair recovery | recovered / repair-eligible, among valid runs |
| Statistical test | exact binomial McNemar, two-sided (one-sided = p/2, never mislabeled) |

All denominators are labeled in code (`paired_analysis.denominator_rules()`);
every outcome cell carries explicit task IDs.

## 3. Fail-closed rules (evaluator, V01–V10)

The experiment is INVALID if any of:
- **V01/V02/V03** — missing/duplicate task IDs or a missing counterpart run
- **V04** — retry-budget mismatch across arms (invalidates the paired comparison)
- **V05** — served model ≠ `laguna-s-2.1`
- **V06** — contradictory first-pass fields (reported; canonical =
  `repair.first_pass_resolved_hidden`)
- **V07** — inconsistent outcome fields (e.g., resolved but hidden tests not executed)
- **V08** — undefined paired denominator / artifact disagreement
- **V09** — stale aggregates or forensic-generator ledgers
- provider contamination classified as infrastructure failure (precedence rule in code)
- **No report is final** unless `task_ledger.json` + `analysis.json` +
  `paired_analysis.json` validate AND the report's tagged claims match the
  canonical package (`validate_report.py`).

Disclosed-warnings class (does not invalidate): V10 passed-count vs run-level
boolean discrepancies — recorded, never altered.

## 4. Run procedure (when approved)

```bash
# 1. preflight + run manifest (must print READY)
python evaluation/preflight_v4.py --generate-manifest

# 2. the single controlled run (refuses without --evaluate and current manifest)
python evaluation/run_benchmark.py --config evaluation/configs/benchmark_v4.yaml --evaluate
```

- One run only; resume-on-rerun is supported by the runner for interrupted
  executions, but partial re-execution after analysis has begun requires an
  amendment note.
- Post-run, `--evaluate` re-verifies the 182-input manifest (any drift
  aborts the ledger) and validates the package; exit code 0 = publishable.
- Historical result directories are never modified. V3 artifacts remain
  byte-identical (enforced by `evaluation/tests/test_real_artifacts_integration.py`).

## 5. Amendment log

- 2026-09-11 — Protocol frozen (initial version). Retry budget 2/2 selected:
  matches V3's baseline_b budget (3) only in spirit of "a real second chance"
  while cutting wasted dead attempts; equal across arms is the controlling
  constraint. Adaptive controller untouched (V3 logic preserved).
