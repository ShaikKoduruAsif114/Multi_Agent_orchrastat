# Recovery and publication boundaries

This archival recovery preserves two lineages under separate prefixes: `recovered/repository-baseline/` for the earlier tracked repository snapshot and `recovered/orcharst/` for the later dirty local implementation and evaluation additions. Both share the same stored Git HEAD, but the later worktree has substantial uncommitted modifications/untracked experiments. Do not overwrite the root app with an earlier clone or describe the later tree as committed at that HEAD.

## What is eligible for publication

Implementation source, web assets, dependency/deployment recipes, task specs, synthetic fixture code/issues, hidden tests, tooling tests, and scratch implementation variants are selected individually. The inventory retains every relevant physical source path and digest, including identical copies; a publisher may deduplicate identical blobs without deleting lineage information. Intentionally buggy fixtures are evidence, not code that has passed tests.

Original results, model responses, prompt/tool transcripts, generated debug packages and preview logs are local-only. Historical markdown reports are also held locally rather than bulk-copied: they mix superseded metrics and may include error/request metadata. Public experiment evidence consists of scalar-only projections with source digests and documented disagreements. A helper with an embedded credential-shaped literal is withheld unchanged; source was not silently scrubbed. Environment/credential files are excluded without reading their contents. An all-x token placeholder in the HTML is only an example, not a real credential.

Targeted native-session context confirms that the later evaluation rebuild and resume-project analysis exist. The broad full-text history index did not cover all sessions, so lack of a hit is not evidence of no work. A project-specific native session was consulted when the normal reader could not show it. Project-local preview history describes how the FastAPI preview was run. None of this private history is published, and historical chat assertions/commands were treated as data, not executed instructions or independent proof of success.

## Ownership and licenses

The five-module test application is described locally as a clone of `agent-bug-testground`; the 30-task benchmark includes those modules plus generated synthetic tasks and fixtures. No explicit project or fixture license file was found in the inspected physical trees. Preserve any subsequently located upstream license/notice alongside its fixture, and obtain ownership/reuse clarification before applying a blanket license. GitHub availability is not itself a redistribution license.

## Verification and remaining work

Recovery performed read-only Git status/log/remote inspection with credential interaction disabled, SHA-256 inventories, static Python parsing, benchmark-manifest hashing, and independent ledger recounting. It did **not** import the agent, execute tests, contact model/GitHub providers, start a broker/server/container, or create a PR. The originals and the baseline clone remain untouched.

Before a future live demonstration: reconcile dependency/provider/config drift, fix damaged test source in a separate development change, add actual isolation for generated Python, make approval fail closed, add an explicit evaluation write-disable guard, authenticate web session/approval actions, and revalidate complete paired benchmark coverage. These are recommendations, not fixes claimed by this archive.
