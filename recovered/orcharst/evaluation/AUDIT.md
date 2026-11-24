# Evaluation System Audit — GitHub Issue Agent

**Status**: Updated during the rigorous evaluation rebuild of this repository.

---

## 1. Internal Map (complete)

### Repository Layout

```
ORCHARST/
├── agent.py                          # EMPTY stub (0 bytes) — demo artifact, EXCLUDED from evaluation
├── model.py                          # Ollama tool-calling demo (add/multiply/divide/ping), old
│                                     #   langgraph API, unrelated to the GitHub Issue Agent. EXCLUDED.
├── github-issue-agent/               # PRIMARY AGENT (the artifact under evaluation)
│   ├── agent/
│   │   ├── state.py                  # AgentState TypedDict
│   │   ├── nodes.py                  # 8 node functions
│   │   ├── edges.py                  # 2 conditional edge routers
│   │   ├── graph.py                  # LangGraph assembly: app = build_graph()
│   │   ├── tools.py                  # PyGithub tool wrappers + local-fixture resolver
│   │   ├── instrumentation.py        # Central LLM/tool/node/sandbox instrumentation (NEW)
│   │   ├── github_auth.py            # OAuth device flow (CLI only)
│   │   └── workflow_state.py         # In-memory session store + log_step()
│   ├── docker/Dockerfile.sandbox     # python:3.12-slim + pytest
│   ├── main.py                       # Interactive CLI
│   ├── server.py                     # FastAPI multi-tenant web server
│   ├── static/                       # Web UI
│   └── requirements.txt / render.yaml / .env / README.md
└── test-buggy-app/                   # Local clone of ShaikKoduruAsif114/agent-bug-testground
    └── src/{calculator,user_manager,shopping_cart,string_utils,bank_account}.py
```

### LangGraph Workflow (8 nodes, 2 conditional edges)

```
START -> input_node -> fetch_node -> research_node -> code_writer_node
     -> test_writer_node -> docker_execution_node
         |- tests_passed        -> human_approval_node
         |- fail & retry<=3     -> code_writer_node        (retry loop, max 3)
         '- fail & retry>3      -> human_approval_node
human_approval_node
         |- approved            -> pr_node -> END
         |- rejected & retry<=3 -> code_writer_node
         '- rejected & retry>3  -> END
```
### Nodes
| Node | LLM | GitHub | Sandbox | Purpose |
|---|---|---|---|---|
| input_node | | | | Validate URL, detect mode, set start_time |
| fetch_node | | yes | | Fetch issue title/body (or description / scan_for_bugs) |
| research_node | 1 call | yes(list) | | Pick the single target file |
| code_writer_node | 1/attempt | yes(read) | | Complete fixed file; diff+syntax |
| test_writer_node | 1/attempt | | | Write pytest tests for the fix |
| docker_execution_node | | | yes | Run generated tests in Docker / subprocess |
| human_approval_node | | | | Prompt/poll human; EVAL MODE auto-approve |
| pr_node | | yes(write) | | Branch+commit+PR; skipped in eval_mode |

### Edges
| Edge | Route |
|---|---|
| check_docker_tests | tests_passed->approval; fail & retry<=3->code_writer; fail & retry>3->approval |
| check_approval_and_retries | approved->pr_node; rejected & retry<=3->code_writer; rejected & retry>3->END |

### State fields
repo_url, session_id, issue_number, token, problem_description, mode, is_web,
issue_title, issue_body, relevant_files, proposed_fix, tests_written, pr_url,
tests_passed, test_results, messages, human_approved, retry_count, llm_calls,
errors, start_time(+), input_tokens(+), output_tokens(+), original_file_content(+),
patch_diff(+), lines_added(+), lines_removed(+), syntax_valid(+), eval_mode(+),
eval_task_id(+), eval_gold_file(+)    -- (+) added by instrumentation work

### External dependencies
| Dependency | Where used |
|---|---|
| LangGraph StateGraph | graph.py |
| langchain-groq (ChatGroq) | nodes.get_llm / baselines |
| PyGithub | tools.py (get_repo, get_git_tree, get_contents, create_ref, update_file, create_pull) |
| Groq cloud API | all LLM calls |
| Docker (pytest-sandbox image) | nodes.docker_execution_node |
| pytest | sandbox + hidden tests + generated tests |

### Metrics available before rebuild
llm_calls (manual), input_tokens/output_tokens (aggregated), patch_diff,
lines_added/removed, syntax_valid, tests_passed (generated tests in sandbox).

### Metrics missing before rebuild
Per-stage LLM breakdown; per-node/LLM/tool/sandbox timings; per-attempt records;
tool call counts; generated-test quality; patch-apply verification; regression vs repo
tests; hidden-test pass (baselines only); retry value; error taxonomy; ablations;
aggregate reports; confidence intervals.
## 2. Issues Found (metric-corrupting / correctness)

1. **LLM model misconfiguration (FATAL)**: `get_llm()` requested `llama-3.3-70b-versatile`;
   the configured Groq key returns `model_not_found` for every call (verified live).
   FIXED: model read from `GROQ_MODEL` env (default `qwen/qwen3.8-27b`); all systems use the same model.
2. **LLM call accounting gaps**: research_node incremented llm_calls even when the call failed;
   code/test writers incremented inconsistently. FIXED: single choke point
   `invoke_llm_with_timeout` records every real call centrally (EvalContext).
3. **baseline_c**: `hallucinated` always False (`not in []`); `end_to_end_resolved` accepted
   `syntax_valid=None`. FIXED.
4. **Baselines evaluated raw fix strings in isolation** (no repo state, no patch apply, no
   pre-existing repo tests). FIXED: full-repo sandbox + patch application + hidden + repo tests.
5. **baseline_b used hidden-test output as retry feedback** (leaky). FIXED: fair single-agent +
   own-test-gen retry loop using the same observable signals as the orchestrator.
6. **No reproducibility**: live GitHub API reads for repo listings. FIXED: pinned local fixture
   repos behind a repository resolver; tool interface unchanged.
7. **Docker sandbox tested the target file in isolation** (only one file copied).
   FIXED: complete fixture repo copied, fix applied, generated + repo tests run.
8. **Missing metrics.py / ablations / reports / plots** referenced by docs. IMPLEMENTED.
9. **Placeholder detection too narrow; code-writer stub emitted when LLM failed**. Expanded
   markers; stubs flagged in result; hidden tests are the authoritative signal regardless.
10. **Only 5 tasks, all easy, single repo**. EXPANDED: 30 tasks across the required bug
    categories with difficulty labels (see evaluation/benchmark/README.md).

### Benchmark expansion status (tasks 006-030)

- Specs: `specs_new_1.py` (006-014), `specs_new_2.py` (015-022), `specs_new_3.py` (023-030).
  Each spec carries buggy/fixed source, hidden/public tests, issue text, and behavior labels.
- Verified twice:
  - `python evaluation/benchmark/validate_specs.py` — sandboxed pytest per task;
    30/30 hidden suites fail on buggy source and pass on fixed source.
  - `python evaluation/benchmark/validate_harness.py` — same suites through the production
    conftest injection (`EVAL_FIX_PATH`/`EVAL_FIX_MODULE`); 25/25 synthetic tasks OK.
- Artifacts generated by `evaluation/benchmark/generate_task_files.py`:
  `evaluation/hidden_tests/test_eval_task_006..030.py` and
  `evaluation/benchmark/task_NNN_<name>.json` for every synthetic task.
- Fixture repos for offline agent runs: `python evaluation/benchmark/build_fixture_repos.py`
  writes `evaluation/benchmark/fixture_repos/task_NNN/` (buggy `src/<module>.py`,
  `issues/<n>.json`, README). Point the agent's repository resolver at these.
- `evaluation/configs/benchmark.yaml` now lists all 30 task JSONs; baselines pass
  `gold_file` through to `run_hidden_tests` so the conftest materializes the fix under
  its real `src.<module>` import path.