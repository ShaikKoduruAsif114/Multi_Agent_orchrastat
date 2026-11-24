# EXPERIMENT EXECUTION PLAN (anti-compaction anchor — update as work completes)

## LOCKED FACTS (verified)
- 30 specs validated 30/30 (validate_specs.py). Task IDs: task_001..task_030.
- Task JSONs in evaluation/benchmark/ (30 files, names task_XXX_slug.json).
- Fixture repos: evaluation/benchmark/fixture_repos/task_001..task_030 (LOCAL dirs).
- Hidden tests: evaluation/hidden_tests/test_eval_task_0NN.py + conftest.py.
- conftest contract: env EVAL_FIX_CODE (agent patch source) + EVAL_FIX_MODULE
  (e.g. "src.pagination") materialize the patch; hidden tests import src.<mod>.
- .env has GROQ_API_KEY (works) + GITHUB_TOKEN. NO GROQ_MODEL set.
- Groq models available on this key: openai/gpt-oss-120b, qwen/qwen3.8-27b,
  qwen/qwen3.6-27b, groq/compound. "llama-3.3-70b-versatile" = 404 (hardcoded
  in both model.py copies + baselines A/B/C -> MUST FIX).
- model.py exists at repo root AND github-issue-agent/model.py.
- edges.py hardcodes retry budget 3 -> need env override for no-retry ablation.
- set_repository_resolver (github-issue-agent/agent/tools.py) NEVER installed
  -> agents would hit GitHub for nonexistent benchmark-fixtures repos. MUST
  install task-aware resolver (fixture_repos/<task_id>) per task in runner.
- baseline_c runs the REAL LangGraph graph (it is the "full system").
- baseline_a = single agent (no retry, no tests), baseline_b = single agent
  + retry loop. baselines A/B call raw Github API -> need local fixture fallback.
- run_benchmark.py: loads config, tasks from JSON files, calls mod.run_task(task),
  writes <results_dir>/<task_id>_<system_name>.json, SKIPS if file exists.
- metrics.py does NOT exist yet -> create it.
- Baselines already updated: run_hidden_tests(..., gold_file) sets EVAL_FIX_MODULE.

## FIX LIST (do in order, py_compile after each)
1. [ ] model.py x2: GROQ_MODEL env override, default "openai/gpt-oss-120b".
2. [ ] edges.py: retry budget from env AGENT_MAX_RETRIES (default 3).
3. [ ] run_benchmark.py: (a) --results-dir CLI + config override; (b) install
       task-aware repository resolver before each run_task (import agent.tools
       after sys.path insert; resolver closure over current task's fixture dir);
       (c) record bug_category/difficulty/workflow fields into result JSON.
4. [ ] baselines A/B: local fixture fallback for list_repo_files/read_file
       (module global CURRENT_FIXTURE_DIR set in run_task from task_id).
5. [ ] baseline_c: ablation hooks via env ORCH_ABLATION (no_research, no_tests);
       no_retry comes free from AGENT_MAX_RETRIES=0.
6. [ ] evaluation/metrics.py: aggregate raw JSONs -> CSV/JSON + failure analysis.
7. [ ] Smoke run 1 task x all systems; verify schema; then full runs in batches.

## KEY DECISIONS
- Model: openai/gpt-oss-120b for ALL systems (fairness). Fallback qwen/qwen3.8-27b.
- Experiment dir: evaluation/results/exp_<date>_full30/ with raw/, aggregates/,
  baselines/, ablations/, failures/, reports/.
- Full system = config system named baseline_c (real graph). Ablations run the
  same module under different system names + env flags so filenames differ.
- Success = hidden tests pass on agent patch (only gate). PR creation is recorded
  but not required (local fixtures -> expect pr_created=0; report honestly).
- Human-in-the-loop: record whatever the graph reports (approval fields) — check
  result schema keys after smoke run.

## PROGRESS LOG
- [DONE] specs 30/30 validated (previous session).
- [DONE] baselines pass gold_file -> EVAL_FIX_MODULE (previous session).
- [IN PROGRESS] Phase 1 fixes.
