# Implementation and safety audit

All paths below are relative to the named recovered implementation. Findings are from source inspection, not runtime verification.

## Earlier repository baseline

`recovered/repository-baseline/github-issue-agent/agent/graph.py` assembles eight nodes:

`input_node → fetch_node → research_node → code_writer_node → test_writer_node → docker_execution_node → human_approval_node → pr_node`.

Conditional edges loop failed diagnostics or rejected proposals back to code generation within the configured budget. `main.py` is the interactive CLI; `server.py` exposes FastAPI and `static/` contains the web interface. `agent/tools.py` wraps GitHub issue reads, repository listing/content, branch creation, commits and pull requests. `agent/github_auth.py` implements a CLI OAuth device flow.

The baseline `agent/nodes.py` Docker command really supplies `--network none`, `--memory 256m`, and `--cpus 0.5`. These are source-level controls, not verified container runtime behavior. `docker/Dockerfile.sandbox` has no non-root `USER` directive, so do not describe it as a non-root sandbox. Later host-subprocess behavior must not inherit the Docker safety claims. The stored baseline uses a Groq-backed model request for `llama-3.3-70b-versatile`; names in comments/UI are not a reliable model manifest.

## Later local implementation

`recovered/orcharst/github-issue-agent/agent/graph.py:20–82` registers **nine**, not eight, nodes:

`input_node → fetch_node → research_node → plan_node → code_writer_node → test_writer_node → subprocess_execution_node → human_approval_node → pr_node`.

`AGENT_LOCALIZATION_V2=1` replaces the registered research function with `agent/localization_v2.py:research_node_v2`. Staged AST discovery, shortlisted LLM ranking and validation are distinct from the earlier filename choice. `agent/state.py` adds planning, patch provenance and evaluation fields. `agent/instrumentation.py` and `evaluation/instrumentation.py` record different layers of LLM/tool/node/test activity. `agent/provider.py` accepts only provider `nara`, with explicit provider failure classification, no client retries, and a default model label of `laguna-s-2.1`.

`agent/nodes.py:624–722` writes a target file and generated diagnostic tests into a temporary directory and runs `sys.executable -m pytest ...` with a 60-second timeout. It does not copy an entire repository in this production diagnostic path. If generated tests are absent, it writes an AST syntax smoke test using a truncated source string. Passing this fallback is not evidence that an issue is resolved. The hidden benchmark evaluator is separate.

### Boundaries that matter

- **No host-code isolation:** no subprocess network denial, user separation, CPU/memory limits, environment filtering or filesystem confinement is implemented in this path. The temporary directory and timeout are not a security sandbox. `target_file` is joined into the temporary path without an explicit containment check.
- **Approval is not reliably fail-closed:** `agent/nodes.py:768–775` catches input exceptions and sets the answer to `yes`. The web path polls an in-memory decision. `server.py` approval/session access should not be assumed tenant-authenticated just because sessions have IDs.
- **Failed diagnostics can still reach approval:** `agent/edges.py:26–28` routes exhausted test failures to human review; approval alone then routes to the PR stage.
- **Evaluation auto-approves:** `agent/nodes.py:738–740`. Despite stale documentation saying PR creation is skipped, `pr_node` itself has no `eval_mode` check. The benchmark's local resolver makes branch/commit/PR wrappers return read-only errors, and a missing token stops the PR node. These are distinct guards; do not use eval mode alone as a write-disable switch.
- **PR result handling:** `pr_node` checks branch errors but does not inspect the returned commit result before requesting a PR. It stringifies the PR result, so an error string is not proof of a created PR. `tools.py` also ASCII-normalizes committed source content, potentially changing Unicode source.

## Evaluation alternatives

`recovered/orcharst/evaluation/baselines/` preserves `baseline_a_single_agent.py`, `baseline_b_single_retry.py`, `baseline_c_multi_agent.py`, and `baseline_adaptive.py`. Adaptive PATH_A/B/C is a controller variant, not evidence that every path was exercised or that the production graph has the same shape. `evaluation/run_benchmark.py`, `fixture_router.py`, `metrics.py`, `build_ledger.py`, `paired_analysis.py`, `preflight_v4.py`, `validate_ledger.py`, `validate_report.py`, `verify_manifest.py`, `lifecycle.py`, and `merge_arms.py` implement the surrounding experiment toolchain. Historical scratch audit scripts and fixture variants under `evaluation/tmp/` are preserved separately rather than silently merged into the canonical benchmark.

`evaluation/tests/test_lifecycle.py` is syntactically damaged at line 282 (and nearby concatenated statements). Static parsing found this without importing or running the test suite. Existing requirements/deployment/config artifacts include older Docker/Groq assumptions and need reconciliation before any future execution.
