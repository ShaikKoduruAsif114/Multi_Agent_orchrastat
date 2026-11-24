# Autonomous GitHub Issue Agent — recovered implementations

A Python issue-to-patch prototype using LangGraph, PyGithub, a FastAPI web interface, generated pytest diagnostics, bounded repair, and an approval step before the graph's PR stage. This archive preserves both the earlier eight-node Docker implementation and the later local, instrumented benchmark implementation; they are not interchangeable releases.

## What is preserved

- `recovered/repository-baseline/github-issue-agent/`: earlier eight-node app, CLI, web UI, Docker sandbox, GitHub tools and OAuth flow.
- `recovered/orcharst/github-issue-agent/`: later nine-node graph with an explicit `plan_node`, optional staged localization, strict provider handling and local subprocess diagnostics.
- `recovered/orcharst/evaluation/`: four baseline/controller implementations, benchmark builders, 30 task specifications and fixture snapshots, hidden tests, instrumentation, reporting, paired analysis, lifecycle/merge validation, V3/V4 protocols and evaluation-tooling tests.
- `recovered/orcharst/test-buggy-app/src/`: original five-module buggy application used as early benchmark context. The separate `test-buggy-app/create_issues.py` setup helper contains an embedded credential-shaped literal and is deliberately kept out of the public tree.
- Both root `model.py` variants: a separate tool-calling demonstration, not the issue agent. The baseline's root `agent.py` is an empty stub, not a working entry point.

## Results that can be attributed

The stored strengthened run `nara_laguna_archstrong_final30_final_20260910` uses `laguna-s-2.1`. Its ledger records 17/30 multi-agent resolutions versus 24/30 for baseline B; six multi-agent provider failures make that all-task delta confounded. On 24 clean paired tasks, the counts are **17/24 versus 19/24**, not a demonstrated multi-agent advantage. Localization is **23/23 evaluable multi-agent runs**, not all 30. Genuine first-failure repair recovery is **2/9 multi-agent versus 4/10 baseline**. The 80% resolution and 40% repair figures in this run belong to the baseline, not the orchestrator.

The adaptive V3 run is separate: the corrected primary comparison is **19/22 versus 19/22**; its retry budgets are unequal. Never combine its adaptive controller results with the strengthened graph's results. See `docs/EXPERIMENTS.md` and scalar evidence files for denominators and contradictions in historical reports.

## Requirements and entry points

Historical entry points, from the corresponding `github-issue-agent/` directory:

```bash
python main.py
python -m uvicorn server:api --host 127.0.0.1 --port 8000
```

The earlier implementation expects Groq credentials and a `pytest-sandbox` Docker image. The recovered newer provider uses `NARAROUTER_API_KEY`, optional `NARAROUTER_MODEL` (default `laguna-s-2.1`) and `NARAROUTER_BASE_URL`; GitHub operations require appropriate credentials and repository permissions. Historical `requirements.txt`, deployment files and older benchmark configs may not match the newer code. These commands are documented entry points, **not a claim of a newly deployed or runtime-tested service**.

## Safety and recovery status

This is a source/data recovery, not a successful production security review. The newer runner executes generated Python in a host subprocess with inherited privileges and environment; it is **not an isolation boundary**. CLI approval fails open on input exceptions. Evaluation auto-approval does not itself guard `pr_node`; local fixture tool guards are a separate protection. Do not run against untrusted issues or real repositories without hardening these paths.

Original credential files, raw responses, preview logs and native chat histories are private and excluded. Two auxiliary scripts—`evaluation/benchmark/validate_specs.py` and `test-buggy-app/create_repo.py` within the newer recovered tree—are also kept local because their unchanged source contains private absolute laptop paths. Their exact bytes remain in the ignored local archive; they were not silently rewritten. Historical public-looking reports are retained locally because of mixed metric revisions and possible private metadata; the public evidence is a scalar-only projection, not fabricated output. Source files are preserved without silent rewrites. No explicit project/fixture license was found, so reuse/relicensing needs owner review.

See `docs/IMPLEMENTATION.md`, `docs/EXPERIMENTS.md`, and `docs/RECOVERY.md`.


## Archive safety

Raw assets and original notebooks remain local under `private/`. Credentials are not copied. See [archive safety](docs/ARCHIVE-SAFETY.md) for verification limits and the existing-history warning.
