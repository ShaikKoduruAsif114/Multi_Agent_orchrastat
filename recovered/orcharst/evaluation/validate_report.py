"""
evaluation/validate_report.py

Check that a results-directory report (markdown) is consistent with the
canonical package (task_ledger.json + analysis.json + paired_analysis.json).

Strategy: the report must either (a) carry a fenced ```ledger-facts block
whose JSON satisfies a provided facts template, or (b) contain explicitly
tagged claims of the form:

    <!--claim: paired_N=22-->
    <!--claim: paired_both=16-->
    <!--claim: mcnemar_two_sided_p=0.146-->

so every headline number in prose is machine-checkable. Untagged headline
numbers are flagged as warnings (not failures) so legacy reports can still be
validated for the subset they tag.

Checks:
  R1  every tagged claim matches the canonical package (hard fail on mismatch)
  R2  every ledger-facts JSON block matches the canonical package (hard fail)
  R3  legacy reports without tags: warns listing untagged headline figures

Usage:
    python evaluation/validate_report.py --experiment <exp> --report FINAL_REPORT.md
    python evaluation/validate_report.py --ledger <dir> --report path.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paired_analysis as PA  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


CLAIM_RE = re.compile(r"<!--\s*claim:\s*([A-Za-z0-9_.]+)\s*=\s*([^>]+?)\s*-->")


def canonical_facts(pkg_dir: Path) -> dict:
    """Every claimable canonical fact, as {name: value}."""
    ledger = _load(pkg_dir / "task_ledger.json")
    analysis = _load(pkg_dir / "analysis.json")
    paired = _load(pkg_dir / "paired_analysis.json")
    entries = ledger["entries"]
    facts: dict = {}

    def add(name: str, value):
        if name in facts:
            raise ValueError(f"duplicate canonical fact {name}")
        facts[name] = value

    for i, s in enumerate(sorted({e["system"] for e in entries})):
        es = [e for e in entries if e["system"] == s]
        add(f"{s}.n", len(es))
        add(f"{s}.final_resolved", sum(1 for e in es if e["final_resolved"] is True))
        add(f"{s}.first_pass_resolved", sum(1 for e in es if e["first_pass_resolved"] is True))
        add(f"{s}.provider_contaminated", sum(1 for e in es if e["provider_failure"]))
        add(f"{s}.infra_failures", sum(
            1 for e in es if e["FINAL_CLASSIFICATION"] == "infrastructure_failure"))
        add(f"{s}.top1_correct", sum(1 for e in es if e["localization_evaluable"]
                                     and e["localization_top1"] is True))
        add(f"{s}.top1_evaluable", sum(1 for e in es if e.get("localization_evaluable")))
        add(f"{s}.hallucinated", sum(1 for e in es if e["hallucinated_file"] is True))

        # efficiency facts on labeled denominators
        eff = (analysis.get("efficiency") or {}).get(s) or {}
        for denom, label in (("runs_with_output", "runs_with_output"),
                             ("valid_only", "valid_only"),
                             ("paired_valid", "paired_valid")):
            b = eff.get(denom) or {}
            add(f"{s}.eff.{label}.n", b.get("n"))
            add(f"{s}.eff.{label}.llm_calls_mean", b.get("llm_calls_mean"))
            add(f"{s}.eff.{label}.total_tokens_mean", b.get("total_tokens_mean"))
            add(f"{s}.eff.{label}.latency_mean_s", b.get("latency_seconds_mean"))
            add(f"{s}.eff.{label}.cost_mean_usd", b.get("cost_mean"))
            add(f"{s}.eff.{label}.total_tokens_sum", b.get("total_tokens_sum"))
            add(f"{s}.eff.{label}.cost_total_usd", b.get("cost_total_usd"))

    tiers = paired.get("tiers") or {}
    for tier, t in tiers.items():
        pre = f"paired_{tier}"
        add(f"{pre}_N", t["N"])
        for cell, tasks in t["outcome_cells"].items():
            add(f"{pre}_{cell}", len(tasks))
        add(f"{pre}_mcnemar_two_sided_p", t["mcnemar_exact_two_sided_p"])
        add(f"{pre}_mcnemar_one_sided_p", t["mcnemar_one_sided_p"])
    facts["_ledger"] = ledger
    facts["_analysis"] = analysis
    facts["_paired"] = paired
    return facts


def extract_claims(text: str) -> list:
    return [(m.group(1), m.group(2).strip()) for m in CLAIM_RE.finditer(text)]


def check_report(report_path: Path, pkg_dir: Path) -> dict:
    facts = canonical_facts(pkg_dir)
    text = report_path.read_text(encoding="utf-8")
    claims = extract_claims(text)

    checks = []
    for name, raw_value in claims:
        if name not in facts:
            checks.append({"claim": f"{name}={raw_value}", "status": "UNKNOWN_FACT",
                           "detail": "not a canonical fact name; see canonical_facts()"})
            continue
        expected = facts[name]
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            try:
                ok = abs(float(raw_value) - float(expected)) < 1e-9
            except (TypeError, ValueError):
                ok = False
        else:
            ok = raw_value == str(expected)
        checks.append({
            "claim": f"{name}={raw_value}",
            "status": "OK" if ok else "MISMATCH",
            "canonical": expected,
        })

    ledger_facts_blocks = re.findall(
        r"```ledger-facts\s*\n(.*?)```", text, flags=re.DOTALL)
    for bi, block in enumerate(ledger_facts_blocks):
        try:
            data = json.loads(block)
        except Exception as exc:
            checks.append({"claim": f"ledger-facts block #{bi + 1}",
                           "status": "UNPARSEABLE", "detail": str(exc)})
            continue
        for k, v in data.items():
            if k not in facts:
                checks.append({"claim": f"facts.{k}={v}", "status": "UNKNOWN_FACT"})
                continue
            exp = facts[k]
            ok = (v == exp) or (isinstance(exp, (int, float))
                                and isinstance(v, (int, float))
                                and abs(v - exp) < 1e-9)
            checks.append({"claim": f"facts.{k}={v}", "status": "OK" if ok else "MISMATCH",
                           "canonical": exp})

    n_checked = len([c for c in checks])
    n_fail = len([c for c in checks if c["status"] == "MISMATCH"])
    n_unk = len([c for c in checks if c["status"] in ("UNKNOWN_FACT", "UNPARSEABLE")])
    untagged_warning = None
    if not claims and not ledger_facts_blocks:
        untagged_warning = (
            "no <!--claim: ...--> tags or ledger-facts blocks found; nothing "
            "machine-checked. Legacy reports can be validated by adding tags.")
    return {
        "report": str(report_path),
        "package": str(pkg_dir),
        "n_claims": len(claims),
        "n_checked": n_checked,
        "n_mismatch": n_fail,
        "n_unknown": n_unk,
        "untagged_warning": untagged_warning,
        "checks": checks,
        "ok": n_fail == 0 and n_unk == 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a report against the canonical package.")
    ap.add_argument("--experiment")
    ap.add_argument("--ledger", default=None, help="package directory (alternative)")
    ap.add_argument("--report", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.experiment:
        pkg_dir = REPO_ROOT / "evaluation" / "results" / args.experiment
    elif args.ledger:
        pkg_dir = Path(args.ledger)
    else:
        ap.error("one of --experiment / --ledger is required")

    report = check_report(Path(args.report), Path(pkg_dir))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"[REPORT] {report['report']}")
        print(f"  claims checked: {report['n_checked']}  mismatches: {report['n_mismatch']}  "
              f"unknown: {report['n_unknown']}  ok={report['ok']}")
        for c in report["checks"]:
            if c["status"] != "OK":
                print(f"  {c['status']}: {c['claim']} "
                      f"(canonical={c.get('canonical')!r})" if "canonical" in c
                      else f"  {c['status']}: {c['claim']}")
        if report["untagged_warning"]:
            print(f"  NOTE: {report['untagged_warning']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
