"""
evaluation/fixture_router.py

Task-aware repository fixture routing for the benchmark.

The benchmark tasks reference fixture repositories that only exist locally
under evaluation/benchmark/fixture_repos/task_NNN. This module:

  1. Keeps the "current task" so the resolver is deterministic even though
     the five seed task JSONs all point at one shared placeholder URL.
  2. resolve_fixture_path() maps (current task, repository URL) -> fixture dir.
  3. install_agent_resolver() installs it as the production agent's
     repository resolver (agent.tools.set_repository_resolver), so the real
     LangGraph workflow runs its genuine research/localization tools against
     local fixtures instead of querying GitHub for nonexistent repos.
  4. Exposes local_repo_files()/local_read_file() so the isolated baselines
     (which use the GitHub REST API directly) read the SAME fixture content,
     keeping every system on identical repository state.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
FIXTURE_ROOT = EVAL_DIR / "benchmark" / "fixture_repos"

_current_task_id = None


def set_current_task(task_id) -> None:
    """Pin the active benchmark task (e.g. 'task_015' or 'task_015_pagination')."""
    global _current_task_id
    _current_task_id = task_id


def _task_dir_from_id(value):
    if not value:
        return None
    m = re.search(r"task[_-]?(\d+)", str(value))
    if not m:
        return None
    candidate = FIXTURE_ROOT / ("task_%03d" % int(m.group(1)))
    return candidate if candidate.is_dir() else None


def resolve_fixture_path(repo_url=None):
    """Return the local fixture directory for the active task / URL, else None."""
    local = _task_dir_from_id(_current_task_id)
    if local:
        return str(local)
    local = _task_dir_from_id(repo_url)
    if local:
        return str(local)
    return None


def local_repo_files(repo_url=None):
    """File listing of the local fixture as POSIX-style relative paths."""
    local = resolve_fixture_path(repo_url)
    if not local:
        return []
    files = []
    for p in Path(local).rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts and p.name != ".gitkeep":
            files.append(p.relative_to(local).as_posix())
    return sorted(files)


def local_read_file(repo_url, file_path):
    """Read a file from the local fixture. Mirrors GitHub read_file semantics."""
    local = resolve_fixture_path(repo_url)
    if not local:
        return "Error: no local fixture resolved for %r" % (repo_url,)
    parts = str(file_path).replace("\\", "/").split("/")
    full = Path(local).joinpath(*parts)
    if full.is_file():
        return full.read_text(encoding="utf-8", errors="replace")
    return "Error: file not found in fixture: %s" % file_path


def install_agent_resolver() -> bool:
    """Install the fixture resolver into the production agent's tools."""
    repo_root = EVAL_DIR.parent
    agent_pkg_dir = repo_root / "github-issue-agent"
    # The agent package lives in github-issue-agent/. Never put repo_root
    # itself on sys.path: stray root-level agent.py / model.py files shadow
    # the real package (observed failure: "'agent' is not a package").
    if agent_pkg_dir.is_dir() and str(agent_pkg_dir) not in sys.path:
        sys.path.insert(0, str(agent_pkg_dir))
    # Purge any shadowed non-package 'agent' module cached by earlier imports.
    mod = sys.modules.get("agent")
    if mod is not None and not hasattr(mod, "__path__"):
        for key in [k for k in list(sys.modules) if k == "agent" or k.startswith("agent.")]:
            del sys.modules[key]
    try:
        from agent.tools import set_repository_resolver
    except Exception:
        return False
    set_repository_resolver(resolve_fixture_path)
    return True
