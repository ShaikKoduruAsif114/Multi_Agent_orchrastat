"""
agent/localization_v2.py

V2 STAGED LOCALIZATION pipeline (gated by AGENT_LOCALIZATION_V2=1).

V1 root cause (verified against exp_full30_v1 raw results):
  1. The LLM was asked to "Return ONLY the exact file path" but returned
     119-172 tokens of verbose text; the exact-match check
     `selected in all_files` failed and the fallback fired.
  2. The fallback `code_files[:3]` is alphabetically sorted, so
     src/__init__.py is always the first candidate -> 8/30 tasks were
     "fixed" in __init__.py and failed hidden tests.
  3. Retry never revisits research, so mislocalization was unrecoverable.

V2 pipeline (4 stages, all instrumented into EvalContext.extra):
  Stage 1  DETERMINISTIC DISCOVERY - extract explicit paths and symbol
           names from the issue text; score every candidate file by
           token overlap + symbol presence (AST-verified).
  Stage 2  LLM RANKING - LLM ranks candidates with a strict single-line
           format; parsed robustly (strip markdown/quotes; match against
           the real file list so no path can be hallucinated).
  Stage 3  VALIDATION - reject __init__.py / trivial files when a
           substantive implementation candidate exists.
  Stage 4  SYMBOL CONSISTENCY - issue-named symbols must exist in the
           selected file; otherwise demote to the next candidate.
"""
from __future__ import annotations

import ast
import os
import re
import time
from typing import Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage

from agent.instrumentation import get_active_context, tool_timer
from agent.tools import list_repo_files, read_file

V2_ENABLED = os.getenv("AGENT_LOCALIZATION_V2", "").strip() == "1"
V2_RESEARCH_TIMEOUT = float(os.getenv("AGENT_V2_RESEARCH_TIMEOUT", "20"))
V2_TOP_K = int(os.getenv("AGENT_V2_TOP_K", "3"))

_STOP_SYMBOL_WORDS = {
    "the", "and", "for", "not", "with", "should", "must", "does",
    "raises", "returns", "when", "this", "than", "but", "has", "have",
    "was", "are", "you", "your", "its",
}

_STOP_TOKEN_WORDS = {
    "the", "a", "an", "is", "are", "not", "to", "of", "and", "or",
    "for", "with", "that", "this", "it", "in", "on", "at", "be",
    "bug", "report", "file", "src", "py", "com", "github", "http",
    "https", "issue", "expected", "raises", "returns", "should",
    "www", "com", "fix", "code", "error", "errors", "test", "tests",
}


def _extract_issue_signals(issue_text: str) -> dict:
    """Stage 1a: pull explicit paths and symbol names out of the issue text."""
    signals = {"explicit_paths": [], "symbols": []}
    # Backtick-quoted paths like `src/matrix_ops.py`
    for m in re.finditer(r"`([^`\n]+)`", issue_text):
        raw = m.group(1).strip()
        if raw.endswith((".py", ".js", ".ts", ".java")) and "/" in raw:
            signals["explicit_paths"].append(raw)
    # Bold "File:" markers: **File:** src/matrix_ops.py
    for m in re.finditer(r"\*\*File:\*\*\s*`?([^`\n*]+)`?", issue_text, re.IGNORECASE):
        raw = m.group(1).strip()
        if raw:
            signals["explicit_paths"].append(raw)
    # Function/method names followed by parens: matrix_multiply(
    for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(", issue_text):
        name = m.group(1)
        if name.lower() not in _STOP_SYMBOL_WORDS:
            signals["symbols"].append(name)
    # Class-like names mentioned bare (e.g., LRUCache)
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9_]{2,})\b", issue_text):
        signals["symbols"].append(m.group(1))
    # Dedupe while preserving order
    signals["explicit_paths"] = list(dict.fromkeys(signals["explicit_paths"]))
    signals["symbols"] = list(dict.fromkeys(signals["symbols"]))
    return signals


def _file_symbols(content: str) -> set:
    """AST-parse a candidate file and return defined top-level symbols."""
    try:
        tree = ast.parse(content)
    except Exception:
        return set(re.findall(r"\b(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]+)", content))
    syms = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            syms.add(node.name)
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        syms.add(f"{node.name}.{sub.name}")
    return syms


def _symbol_hits(symbols: set, issue_symbols: list) -> list:
    """Issue-named symbols that a file actually defines (incl. methods)."""
    return [s for s in issue_symbols
            if s in symbols or any(fs.endswith("." + s) for fs in symbols)]


def _read_candidate(repo_url: str, token: str, file_path: str) -> str:
    """Read a candidate file; return '' on any failure."""
    try:
        with tool_timer("read_file"):
            content = read_file.invoke({"repo_url": repo_url, "file_path": file_path, "token": token})
        if isinstance(content, str) and not content.startswith("Error"):
            return content
    except Exception:
        pass
    return ""


def _score_candidates(code_files: list, issue_text: str,
                      repo_url: str, token: str) -> tuple[list, dict]:
    """
    Stage 1: deterministic scoring of every candidate file.

    Returns (ranked_candidates, stage_info); each candidate is
    {file, score, reasons} sorted by score desc, then alphabetically.
    """
    signals = _extract_issue_signals(issue_text)
    issue_tokens = set(re.findall(r"[a-z0-9]+", issue_text.lower()))
    issue_tokens = {t for t in issue_tokens if len(t) > 2 and t not in _STOP_TOKEN_WORDS}

    candidates = []
    for f in code_files:
        reasons = []
        score = 0.0
        base = f.rsplit("/", 1)[-1]
        stem = base.removesuffix(".py").removesuffix(".js").removesuffix(".ts")

        # (a) Explicit path mention in the issue (strongest signal)
        for p in signals["explicit_paths"]:
            if p == f or p.endswith("/" + base) or f.endswith(p):
                score += 10.0
                reasons.append(f"explicit_path:{p}")
                break

        # (b) Filename-token overlap with issue text
        fname_tokens = set(re.findall(r"[a-z0-9]+", stem.lower()))
        if fname_tokens:
            overlap = issue_tokens & fname_tokens
            if overlap:
                score += min(6.0, 2.0 * len(overlap))
                reasons.append(f"filename_overlap:{sorted(overlap)}")

        # (c) Symbol presence (AST-verified) + substance — .py files only
        if f.endswith(".py"):
            content = _read_candidate(repo_url, token, f)
            if content:
                file_syms = _file_symbols(content)
                hit = _symbol_hits(file_syms, signals["symbols"])
                if hit:
                    score += min(8.0, 2.0 * len(hit))
                    reasons.append(f"symbol_hit:{hit[:5]}")
                n_lines = len(content.splitlines())
                n_defs = len([s for s in file_syms if "." not in s])
                if n_defs == 0:
                    score -= 4.0
                    reasons.append("no_defs")
                elif n_lines < 5:
                    score -= 4.0
                    reasons.append("trivial_file")
                else:
                    score += 1.0
                    reasons.append(f"research_substantive:{n_defs}defs/{n_lines}lines")

        # (d) Penalize __init__.py / setup / config files
        if base == "__init__.py":
            score -= 6.0
            reasons.append("init_penalty")
        if base.startswith(("setup.", "conftest.", "config", "settings")):
            score -= 3.0
            reasons.append("config_penalty")

        candidates.append({"file": f, "score": round(score, 2), "reasons": reasons})

    candidates.sort(key=lambda c: (-c["score"], c["file"]))
    stage_info = {
        "stage1_signals": {
            "explicit_paths": signals["explicit_paths"],
            "symbols": signals["symbols"][:12],
        },
        "stage1_ranking": [{"file": c["file"], "score": c["score"]} for c in candidates],
    }
    return candidates, stage_info


def _parse_llm_ranking(raw: str, code_files: list) -> list:
    """
    Stage 2 helper: robustly parse the LLM's ranking response.

    Accepts verbose text; extracts file paths that match a real candidate
    (exact, suffix, or basename match). Never fabricates paths — only
    files present in code_files can be returned.
    """
    if not raw:
        return []
    text = raw.replace("```", "").replace("*", "").replace("`", "")
    ranked = []
    seen = set()
    for m in re.finditer(r"[\w./\\-]+\.[A-Za-z]{1,4}", text):
        tok = m.group(0).strip().strip('.,;:!?"\'').replace("\\", "/")
        for cf in code_files:
            if cf in seen:
                continue
            if (tok == cf or cf.endswith("/" + tok) or tok.endswith("/" + cf)
                    or tok == cf.rsplit("/", 1)[-1]):
                ranked.append(cf)
                seen.add(cf)
                break
    return ranked


def _llm_rank(candidates: list, issue_text: str, timeout_sec: float) -> tuple[list, int, int, str]:
    """
    Stage 2: LLM ranks the Top-K candidates.

    Returns (llm_ranked_files, input_tokens, output_tokens, raw_response).
    The prompt lists candidates WITH their deterministic scores/reasons so
    the LLM can only re-rank real files, never hallucinate new ones.
    """
    cand_lines = "\n".join(
        f"- {c['file']}  (score {c['score']}: {', '.join(c['reasons'])})"
        for c in candidates[:max(V2_TOP_K * 2, 6)]
    )
    prompt = f"""Given this GitHub Issue:
{issue_text[:600]}

And these candidate files (pre-scored by static analysis):
{cand_lines}

Rank the files by likelihood of being THE file that must be edited to fix this issue.
Return your answer as a single line of file paths, most likely first, separated by commas.
Return ONLY file paths from the list above. No explanations, no markdown, no numbering.

Format: path1, path2, path3"""

    from agent.nodes import invoke_llm_with_timeout
    raw, i_tok, o_tok = invoke_llm_with_timeout(
        [SystemMessage(content="You are an expert developer. You return only a comma-separated list of exact file paths. No markdown, no explanations, no numbering."),
         HumanMessage(content=prompt)],
        timeout_sec=timeout_sec,
        stage="research",
    )
    ranked = _parse_llm_ranking(raw, [c["file"] for c in candidates])
    return ranked, i_tok, o_tok, raw


def _merge_rankings(det_candidates: list, llm_ranked: list, top_k: int) -> list:
    """
    Stage 2b: merge LLM + deterministic rankings.

    LLM gets priority (it sees issue semantics), but any file the LLM
    omitted is appended from the deterministic ranking so Top-K is always
    full when enough candidates exist.
    """
    merged = list(llm_ranked[:top_k])
    for c in det_candidates:
        f = c["file"]
        if f not in merged:
            merged.append(f)
        if len(merged) >= top_k:
            break
    return merged


def _validate_and_select(candidates: list, merged: list, issue_text: str,
                         repo_url: str, token: str) -> tuple[list, dict]:
    """
    Stage 3+4: validation (reject __init__.py / trivial files when a
    substantive candidate exists) + symbol consistency (issue-named
    symbols must exist in the selected file).

    Returns (final_relevant_files, stage_info).
    """
    signals = _extract_issue_signals(issue_text)
    cand_by_file = {c["file"]: c for c in candidates}
    stage_info = {"stage3_rejections": [], "stage4_demotions": []}

    # Pre-compute substance + symbols for every merged candidate
    info = {}
    for f in merged:
        entry = {"file": f, "substantive": True, "symbols": set(), "n_defs": 0, "n_lines": 0}
        if f.endswith(".py"):
            content = _read_candidate(repo_url, token, f)
            if content:
                file_syms = _file_symbols(content)
                entry["symbols"] = file_syms
                entry["n_defs"] = len([s for s in file_syms if "." not in s])
                entry["n_lines"] = len(content.splitlines())
                entry["substantive"] = (entry["n_defs"] > 0 and entry["n_lines"] >= 5)
        info[f] = entry

    # Stage 3: validation pass — demote non-substantive files
    validated = []
    for f in merged:
        if not info[f]["substantive"]:
            if any(info[x]["substantive"] for x in merged if x != f):
                stage_info["stage3_rejections"].append(
                    {"file": f, "reason": "not_substantive"})
                continue
        validated.append(f)

    # Stage 4: symbol consistency — the issue names symbols; the selected
    # file should define them. Demote the top pick when it defines none of
    # the issue-named symbols but a lower candidate defines at least one.
    final = []
    for f in validated:
        sym_hits = _symbol_hits(info[f]["symbols"], signals["symbols"])
        info[f]["symbol_hits"] = sym_hits
        if signals["symbols"] and not sym_hits and f == validated[0]:
            for other in validated[1:]:
                o_hits = _symbol_hits(info[other]["symbols"], signals["symbols"])
                if o_hits:
                    stage_info["stage4_demotions"].append(
                        {"from": f, "to": other, "symbols": o_hits[:5]})
                    final = [other] + [x for x in validated if x != other]
                    return final, stage_info
        final.append(f)

    return final, stage_info


def _record_metrics(metrics: dict) -> None:
    """Write localization metrics into the active EvalContext.extra."""
    ctx = get_active_context()
    if ctx is not None:
        loc = ctx.extra.setdefault("localization", {})
        if "history" not in loc:
            loc["history"] = []
        loc["history"].append(metrics)
        loc.update(metrics)


def _llm_call_count(state: dict) -> int:
    """Authoritative LLM call count from central instrumentation."""
    ctx = get_active_context()
    return ctx.total_llm_calls() if ctx is not None else state.get("llm_calls", 0)


def research_node_v2(state) -> Dict[str, Any]:
    """Node 3 (V2): staged Top-K localization with validation."""
    session_id = state.get("session_id", "default")
    repo_url = state["repo_url"]
    token = state.get("token", "")
    input_tokens = state.get("input_tokens", 0)
    output_tokens = state.get("output_tokens", 0)
    localization_attempts = state.get("localization_attempts", 0) + 1
    localization_revisit = localization_attempts > 1

    from agent.workflow_state import log_step
    log_step("Step 3/8: [V2] Staged localization: deterministic discovery -> LLM ranking -> validation", "sys", session_id)

    t0 = time.monotonic()
    metrics = {
        "v2": True,
        "localization_attempts": localization_attempts,
        "localization_revisit": localization_revisit,
        "research_timeout_count": 0,
        "research_retry_count": 0,
        "research_success_after_timeout": False,
    }

    with tool_timer("list_repo_files"):
        all_files = list_repo_files.invoke({"repo_url": repo_url, "token": token})
    if not isinstance(all_files, list) or (all_files and all_files[0].startswith("Error")):
        all_files = []

    code_files = [
        f for f in all_files
        if f.endswith(('.py', '.js', '.ts', '.java'))
        and not f.startswith('.')
        and 'test' not in f.lower()
    ]

    issue_text = state.get("issue_title", "") + "\n" + state.get("issue_body", "")

    if not code_files:
        metrics.update({"stage_reached": "no_code_files", "candidates": [],
                        "selected": "", "research_latency": round(time.monotonic() - t0, 3)})
        relevant_files = ["src/main.py"]
        _record_metrics(metrics)
        return {"relevant_files": relevant_files,
                "localization_candidates": [],
                "localization_stage": "no_code_files",
                "localization_attempts": localization_attempts,
                "localization_revisit": localization_revisit,
                "llm_calls": _llm_call_count(state),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens}

    # ---- Stage 1: deterministic discovery -------------------------------
    candidates, stage_info = _score_candidates(code_files, issue_text, repo_url, token)
    metrics["stage1_ranking"] = stage_info["stage1_ranking"]
    metrics["stage1_signals"] = stage_info["stage1_signals"]

    # ---- Stage 2: LLM ranking (with one retry on empty parse) -----------
    llm_ranked = []
    raw_first = ""
    for attempt in range(2):
        llm_ranked, i_tok, o_tok, raw_first = _llm_rank(candidates, issue_text, V2_RESEARCH_TIMEOUT)
        input_tokens += i_tok
        output_tokens += o_tok
        if llm_ranked:
            metrics["research_success_after_timeout"] = attempt > 0
            break
        metrics["research_timeout_count"] += 1
        if attempt == 0:
            metrics["research_retry_count"] += 1
            log_step("[V2] Research LLM call returned no usable ranking; retrying once", "sys", session_id)

    metrics["llm_ranking"] = llm_ranked
    metrics["llm_ranking_raw_len"] = len(raw_first)

    # ---- Stage 2b: merge deterministic + LLM rankings --------------------
    merged = _merge_rankings(candidates, llm_ranked, V2_TOP_K)

    # ---- Stage 3+4: validation + symbol consistency ---------------------
    final, val_info = _validate_and_select(candidates, merged, issue_text, repo_url, token)
    metrics["stage3_rejections"] = val_info["stage3_rejections"]
    metrics["stage4_demotions"] = val_info["stage4_demotions"]

    relevant_files = final if final else ["src/main.py"]

    # Evidence: include source excerpts of the selected file and the strongest
    # runner-up so the planning/codegen stages reason over real code, not just
    # file names. Only issue-named symbol definitions + a bounded excerpt are
    # included to avoid repository-wide context bloat.
    evidence_excerpts = {}
    signals = stage_info["stage1_signals"]
    for f in relevant_files[:2]:
        content = _read_candidate(repo_url, token, f)
        if not content:
            continue
        excerpt = {
            "excerpt": content[:2000],
            "n_lines": len(content.splitlines()),
        }
        hits = _symbol_hits(_file_symbols(content), signals["symbols"])
        if hits:
            excerpt["issue_symbol_hits"] = hits
        evidence_excerpts[f] = excerpt

    metrics.update({
        "candidates": [{"file": c["file"], "score": c["score"], "reasons": c["reasons"]} for c in candidates],
        "selected": relevant_files[0] if relevant_files else "",
        "top_k": relevant_files[:V2_TOP_K],
        "stage_reached": "complete",
        "research_latency": round(time.monotonic() - t0, 3),
    })
    _record_metrics(metrics)

    log_step(f"[V2] Localization complete. Selected: {relevant_files[0] if relevant_files else 'none'} "
             f"(top candidates: {', '.join(relevant_files)})", "info", session_id)

    return {
        "relevant_files": relevant_files,
        "localization_candidates": metrics["candidates"],
        "localization_evidence": {
            "issue": issue_text,
            "target_file": relevant_files[0] if relevant_files else "",
            "issue_signals": signals,
            "source_excerpts": evidence_excerpts,
            "target_source_excerpt": evidence_excerpts.get(relevant_files[0], {}).get("excerpt", "") if relevant_files else "",
            "repository_candidates": metrics["candidates"],
            "ranking": metrics.get("llm_ranking", []),
            "validation": {
                "rejections": metrics.get("stage3_rejections", []),
                "demotions": metrics.get("stage4_demotions", []),
            },
        },
        "localization_stage": "complete",
        "localization_attempts": localization_attempts,
        "localization_revisit": localization_revisit,
        "llm_calls": _llm_call_count(state),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
