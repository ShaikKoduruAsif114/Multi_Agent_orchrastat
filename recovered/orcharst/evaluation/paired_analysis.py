"""
evaluation/paired_analysis.py

CANONICAL paired analysis for two-system benchmark experiments.

DENOMINATOR RULES ARE CODE, NOT PROSE (see `denominator_rules()`):

  VALID_RUN       entry whose FINAL_CLASSIFICATION is "resolved" or
                  "genuine_agent_failure" (i.e. not provider-failed, not
                  infra-failed, not invalid: the run produced a usable,
                  uncontaminated outcome).
  FATAL_DEATH     run whose execution.status == "error" AND that carries a
                  provider-failure signature: the pipeline died before
                  producing a comparable outcome.
  TIER "valid"    (PRIMARY, canonical clean paired denominator)
                  include task iff BOTH systems' runs are VALID_RUN.
                  Contaminated-but-completed runs are NOT valid -> excluded.
  TIER "fatal"    include task iff NEITHER system's run is a FATAL_DEATH.
                  Runs that recorded a mid-run provider error but still
                  completed are kept as observed outcomes (contamination is
                  disclosed separately in the ledger). This tier answers
                  "who produced a usable outcome on usable-coverage tasks".
  TIER "all"      include every task that has an entry for both systems.
                  DESCRIPTIVE ONLY and CONFOUNDED whenever contamination is
                  asymmetric: provider losses count as agent losses.

McNemar: exact binomial, TWO-SIDED, on the discordant cells of the chosen
tier. One-sided p-values are derived quantities (p_one = p_two / 2) and are
never reported as two-tailed.
"""
from __future__ import annotations

import math

VALID_CLASSES = ("resolved", "genuine_agent_failure")
PRIMARY_TIER = "valid"


# ---------------------------------------------------------------- validity ---
def is_valid_run(entry: dict) -> bool:
    return entry.get("FINAL_CLASSIFICATION") in VALID_CLASSES


def is_fatal_death(entry: dict) -> bool:
    """Pipeline died (execution.status=error) from a provider failure."""
    return entry.get("final_status") == "error" and bool(entry.get("provider_failure"))


# ---------------------------------------------------------------- McNemar ----
def mcnemar_exact_two_sided(b: int, c: int) -> float:
    """Exact binomial two-sided McNemar p-value for discordant counts (b, c).

    p = 2 * P(X <= min(b, c); Binomial(n=b+c, p=0.5)), computed via the
    symmetric closed form sum_{i<=k} C(n, i) / 2^(n-1), capped at 1.0.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** (n - 1))
    return min(1.0, p)


# ------------------------------------------------------------- denominator ---
def denominator_rules() -> dict:
    """Machine-readable registry of every paired denominator. CODE = TRUTH."""
    return {
        "VALID_RUN": "FINAL_CLASSIFICATION in {resolved, genuine_agent_failure}",
        "FATAL_DEATH": "execution.status == 'error' AND provider_failure is true",
        "tier:valid": {
            "rule": "task included iff BOTH systems' runs are VALID_RUN",
            "role": "PRIMARY clean paired denominator",
            "excludes": "any provider-contaminated or infra-failed or invalid run on either side",
        },
        "tier:fatal": {
            "rule": "task included iff NEITHER system's run is a FATAL_DEATH",
            "role": "sensitivity tier: contaminated-but-completed runs kept as observed outcomes",
        },
        "tier:all": {
            "rule": "task included iff both systems have any entry for it",
            "role": "DESCRIPTIVE ONLY — confounded under asymmetric contamination",
        },
        "mcnemar": "exact binomial two-sided on discordant cells; one-sided = two_sided / 2",
    }


# --------------------------------------------------------------- indexing ----
def index_entries(entries: list) -> dict:
    """{(task_id, system): entry}; raises on duplicate (task_id, system)."""
    by_key: dict = {}
    for e in entries:
        key = (e.get("task_id"), e.get("system"))
        if key in by_key:
            raise ValueError(f"duplicate ledger entry for {key}")
        by_key[key] = e
    return by_key


def _cell_label(systems: tuple, a_resolved: bool, b_resolved: bool) -> str:
    if a_resolved and b_resolved:
        return "both"
    if a_resolved:
        return f"{systems[0]}_only"
    if b_resolved:
        return f"{systems[1]}_only"
    return "neither"


def build_tier(by_key: dict, systems: tuple, tier: str) -> dict:
    """Compute one inclusion tier. Returns tasks, exclusions with reasons."""
    task_ids = sorted({t for (t, _s) in by_key})
    included: list = []
    excluded: dict = {}
    unpaired: list = []
    for t in task_ids:
        ea, eb = by_key.get((t, systems[0])), by_key.get((t, systems[1]))
        if ea is None or eb is None:
            missing = systems[0] if ea is None else systems[1]
            unpaired.append({"task_id": t, "missing_system": missing})
            excluded[t] = f"missing counterpart run for {missing}"
            continue
        if tier == "valid":
            va, vb = is_valid_run(ea), is_valid_run(eb)
            if va and vb:
                included.append(t)
            else:
                bad = [s for s, v in zip(systems, (va, vb)) if not v]
                reasons = []
                for s, e in zip(systems, (ea, eb)):
                    if not is_valid_run(e):
                        reasons.append(f"{s}: {e.get('FINAL_CLASSIFICATION')}")
                excluded[t] = "; ".join(reasons)
        elif tier == "fatal":
            fa, fb = is_fatal_death(ea), is_fatal_death(eb)
            if not fa and not fb:
                included.append(t)
            else:
                reasons = [f"{s}: fatal provider death (execution.status=error)"
                           for s, f in zip(systems, (fa, fb)) if f]
                excluded[t] = "; ".join(reasons)
        elif tier == "all":
            included.append(t)
        else:
            raise ValueError(f"unknown tier: {tier}")
    return {"tasks": included, "excluded": excluded, "unpaired": unpaired}


# --------------------------------------------------------------- analysis ----
def paired_analysis(entries: list, systems: tuple, tiers=("valid", "fatal", "all"),
                    primary: str = PRIMARY_TIER) -> dict:
    """Canonical paired analysis over the given ledger entries.

    Returns per-tier: task list, exclusion reasons, outcome cells WITH task
    IDs, discordant counts, McNemar exact two-sided p (and one-sided), and
    per-system resolved counts on the tier's denominator.
    """
    if len(systems) != 2:
        raise ValueError("paired analysis requires exactly two systems")
    by_key = index_entries(entries)
    out: dict = {"systems": list(systems), "primary_tier": primary,
                 "mcnemar_method": "exact binomial, two-sided",
                 "denominator_rules": denominator_rules(), "tiers": {}}

    for tier in tiers:
        t = build_tier(by_key, systems, tier)
        tasks = t["tasks"]
        cells: dict = {k: [] for k in
                       ("both", f"{systems[0]}_only", f"{systems[1]}_only", "neither")}
        for task in tasks:
            a = by_key[(task, systems[0])].get("final_resolved") is True
            b = by_key[(task, systems[1])].get("final_resolved") is True
            cells[_cell_label(systems, a, b)].append(task)
        b_disc = len(cells[f"{systems[0]}_only"])   # system 0 wins
        c_disc = len(cells[f"{systems[1]}_only"])   # system 1 wins
        p_two = mcnemar_exact_two_sided(b_disc, c_disc)
        out["tiers"][tier] = {
            "rule": denominator_rules()[f"tier:{tier}"]["rule"],
            "role": denominator_rules()[f"tier:{tier}"]["role"],
            "N": len(tasks),
            "tasks": tasks,
            "excluded_tasks": t["excluded"],
            "unpaired": t["unpaired"],
            "outcome_cells": {k: v for k, v in cells.items()},
            "outcome_counts": {k: len(v) for k, v in cells.items()},
            f"{systems[0]}_resolved": sum(
                1 for task in tasks if by_key[(task, systems[0])].get("final_resolved") is True),
            f"{systems[1]}_resolved": sum(
                1 for task in tasks if by_key[(task, systems[1])].get("final_resolved") is True),
            "discordant": {f"{systems[0]}_only_wins": b_disc,
                           f"{systems[1]}_only_wins": c_disc},
            "mcnemar_exact_two_sided_p": round(p_two, 4),
            "mcnemar_one_sided_p": round(p_two / 2, 4),
        }
    return out


# ------------------------------------------------------- convenience alias ---
def mcnemar_exact(b: int, c: int) -> float:
    """Backwards-compatible alias for evaluation/build_ledger.py's name."""
    return mcnemar_exact_two_sided(b, c)
