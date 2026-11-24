# Experiment lineage and metric attribution

No experiment was rerun during recovery. `METRIC_EVIDENCE.json` is an allowlisted scalar projection of two stored ledgers; `METRIC_RECOUNT.json` independently counts those projections' source records. Original raw outputs remain private. The projection preserves contradictions rather than rewriting source data.

## Distinct evidence families

The earlier eight-node app is a source snapshot, not by itself a benchmark record. The later evaluation tree has 39 physical result-family directories, including smokes, provider/model trials, full 30-task runs, adaptive revisions and incomplete V4 work. A `full30` name does not establish complete coverage.

- `exp_full30_v1`: stored aggregate counts are baseline A 6/30, baseline B 26/30, multi-agent 15/30. This is an older protocol, not the strengthened run below.
- `exp_full30_v2_20260909`: aggregate counts are baseline B 0/30 and multi-agent 2/30; its report/provider problems must remain attached to that run, not erased by newer successful runs.
- `nara_qwen38_v2_vs_baseline_full30_20260909`: 59 direct raw records plus quarantine artifacts, not a complete uncontaminated 60-record comparison.
- Other archived families include Laguna V2, adaptive V1/V2/V3, strengthened V1/V2/final, Orca DeepSeek V4 Flash trials, Kios smokes, and timestamped attempts.
- `exp_20260911_014541_full30` has 25 direct raw records; `exp_20260911_030238_full30` has 33. V4 config/protocol, lifecycle/merge code and a run manifest exist, but no completed valid V4 headline is inferred from these partial directories.

The complete physical family inventory is kept in the local audit. Revisions sharing a filename in Git history are not necessarily independently recoverable experiment snapshots; the dirty later source cannot be uniquely pinned by the earlier commit ID alone.

## Strengthened graph, final archived run

Run identity: `nara_laguna_archstrong_final30_final_20260910`; ledger and reports under `recovered/orcharst/evaluation/results/<run>/`. Provider label `nara`, requested/served model label `laguna-s-2.1`; report declares matched retry budget 2 and local subprocess execution. The benchmark is 30 synthetic Python single-file issue tasks, not SWE-bench or a sample of arbitrary real GitHub issues.

| Measure | multi_agent | baseline_b |
|---|---:|---:|
| Stored ledger entries | 30 | 30 |
| Full-30 final resolution | 17/30 | 24/30 |
| Provider-failure class | 6/30 | 0/30 |
| Clean paired resolution (N=24) | 17/24 | 19/24 |
| Top-1 localization, evaluable only | 23/23 | 30/30 |
| Genuine clean repair recovery | 2/9 | 4/10 |

The paired report records discordant cells 1 multi-agent-only versus 3 baseline-only, exact two-sided McNemar p=0.625; no superiority claim is supported. The full-30 delta is provider-confounded. The 80% resolution and 40% recovery figures belong to **baseline B** in this run. Claiming all three as an orchestrator result would mix denominators and systems.

Ledger caveat: `repair_eligible=true` appears on 15 multi-agent entries if counted blindly; restricting to clean genuine outcomes excludes the six provider failures and yields the report's denominator 9. Localization excludes seven pipeline failures. The report itself discloses a syntax-gate failure despite a later zero-syntax-failure headline, inconsistent per-test counts, and a task_009 smoke record overwritten before resume. Use stored run-level booleans and disclose limits; do not imply pristine independent execution from the report alone.

## Adaptive V3: corrected but still confounded

Run: `nara_laguna_adaptive_v3_final_20260910`, same stored `laguna-s-2.1` model label. The original report is superseded by `FINAL_REPORT_CORRECTED.md`, but the corrected prose still contains internal counting/wording inconsistencies. The ledger recount supports:

- All-30 final-resolution fields: adaptive 25/30, baseline 19/30. Classification counts: adaptive 25 resolved / 3 provider / 2 genuine failures; baseline 19 / 7 / 4.
- Stored **primary** flags retain 22 pairs: 19/22 versus 19/22. This inclusion rule retains adaptive task_020 despite a nonfatal provider error; it is not a fully uncontaminated set.
- Strict contamination-free pairing: 21 pairs, adaptive 19/21 versus baseline 18/21.
- Adaptive repair block: 3/3 recorded recoveries; baseline 2/6 before paired filtering. Adaptive path retry budgets were 1 or 2, versus baseline 3. These are not matched repair comparisons.
- The corrected report retracts the earlier +20 percentage-point superiority story, mislabeled one-sided significance, stale V2 cost/token numbers, and claimed successful escalations. Its primary and strict paired tests are reported as p=1.00.

The historical 100% localization statements depend on evaluability and contamination filtering. Raw flags in the projected V3 ledger are adaptive 27 correct among 28 evaluable, baseline 23/23; stricter clean-only reporting must be explicitly labeled. Its controller-level first-pass fields disagree with repair-level fields for some tasks. Never pool this run's efficiency or repair numbers with the strengthened graph's 30-task results.

## Benchmark versioning and reporting rules

The stored manifest declares 182 inputs: 30 task JSONs, 31 hidden-test files, 120 fixture files and one configuration. The current recovery snapshot has **179 matching files and three missing canonical fixture sources**: task_021 `src/ledger.py`, task_024 `src/lru_cache.py`, and task_025 `src/slugify.py`. All three have byte-identical SHA-256 matches under preserved `evaluation/tmp/fixtures/` alternatives; see `FIXTURE_RECOVERY.json`. No originals were repaired. Historical statements of a clean 182/182 gate are not a substitute for the present snapshot check. Benchmark builders, specs, temporary fixtures and hidden suites are preserved so later drift can be investigated.

Generated diagnostic-test success is not resolution. Hidden-test resolution is specific to each run/protocol. Provider errors are not model reasoning failures, no prediction is not automatically a hallucinated file, estimated costs are not invoices, and no stored patch/test statistic proves that a real approved PR was opened. Original resume claims without a pinned run and denominator remain historical claims rather than independently established measurements.
