"""
evaluation/hidden_tests/conftest.py

Pytest fixtures that inject the agent's proposed fix code into hidden tests.

The agent's proposed fix is provided as a Python source string via the
EVAL_FIX_CODE environment variable. This conftest.py compiles that code
into a temporary module and exposes it as a pytest fixture.

Usage (called by run_hidden_tests.py):
    EVAL_FIX_CODE="<python source>" pytest evaluation/hidden_tests/test_eval_task_001.py

The hidden tests use parametric fixtures named after each task's module.
"""
import os
import sys
import types
import importlib
import importlib.util
import tempfile
import pytest


# ---------------------------------------------------------------------------
# src-module materialization (tasks 006-030)
#
# The newer hidden test files import the fix under its real package path,
# e.g. `from src.pagination import paginate`. When EVAL_FIX_MODULE is set
# (e.g. "src.pagination") the fix source (EVAL_FIX_CODE) is written to a
# temporary src/<module>.py layout that is prepended to sys.path, so the
# imports resolve against the agent's proposed fix instead of GitHub.
# ---------------------------------------------------------------------------
def _materialize_fix_as_src_module() -> None:
    module_path = os.environ.get("EVAL_FIX_MODULE", "").strip()
    if not module_path:
        return
    source = _get_fix_source()
    if not source:
        return
    parts = module_path.split(".")
    if len(parts) < 2 or parts[0] != "src":
        raise RuntimeError(
            f"EVAL_FIX_MODULE must look like 'src.<module>', got {module_path!r}"
        )
    tmpdir = tempfile.mkdtemp(prefix="eval_fix_src_")
    pkg_dir = os.path.join(tmpdir, "src")
    os.makedirs(pkg_dir, exist_ok=True)
    with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(pkg_dir, parts[1] + ".py"), "w", encoding="utf-8") as f:
        f.write(source)
    # Also expose it as the agent_fix module for the fixed_* fixtures.
    os.environ["EVAL_FIX_PATH"] = os.path.join(pkg_dir, parts[1] + ".py")
    if tmpdir not in sys.path:
        sys.path.insert(0, tmpdir)


def _load_module_from_source(source_code: str, module_name: str):
    """Compile and load a Python source string as a temporary module."""
    mod = types.ModuleType(module_name)
    mod.__file__ = f"<eval_fix:{module_name}>"
    try:
        code = compile(source_code, mod.__file__, "exec")
        exec(code, mod.__dict__)
    except SyntaxError as e:
        raise RuntimeError(f"SyntaxError in agent fix: {e}") from e
    except Exception as e:
        raise RuntimeError(f"RuntimeError loading agent fix: {e}") from e
    return mod


def _get_fix_source() -> str:
    """Get the agent's proposed fix source code from environment."""
    source = os.environ.get("EVAL_FIX_CODE", "")
    if not source:
        # Also try reading from a temp file path
        fix_path = os.environ.get("EVAL_FIX_PATH", "")
        if fix_path and os.path.exists(fix_path):
            with open(fix_path, "r", encoding="utf-8") as f:
                source = f.read()
    return source


@pytest.fixture(scope="session")
def _fix_module():
    """Load the agent's proposed fix as a module (session-scoped for speed)."""
    source = _get_fix_source()
    if not source:
        pytest.skip("No fix code provided (EVAL_FIX_CODE or EVAL_FIX_PATH not set)")
    return _load_module_from_source(source, "agent_fix")


# ---------------------------------------------------------------------------
# Task-specific fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fixed_calculator(_fix_module):
    """Fixture exposing the fixed calculator module."""
    return _fix_module


@pytest.fixture
def fixed_user_manager(_fix_module):
    """Fixture exposing the fixed user_manager module."""
    return _fix_module


@pytest.fixture
def clean_db(fixed_user_manager):
    """Reset users_db before each test that touches user_manager."""
    if hasattr(fixed_user_manager, "users_db"):
        fixed_user_manager.users_db.clear()
    yield
    if hasattr(fixed_user_manager, "users_db"):
        fixed_user_manager.users_db.clear()


@pytest.fixture
def fixed_shopping_cart(_fix_module):
    """Fixture exposing the fixed shopping_cart module."""
    return _fix_module


@pytest.fixture
def fixed_string_utils(_fix_module):
    """Fixture exposing the fixed string_utils module."""
    return _fix_module


@pytest.fixture
def fixed_bank_account(_fix_module):
    """Fixture exposing the fixed bank_account module."""
    return _fix_module


# ---------------------------------------------------------------------------
# Activate src-module materialization for tasks 006-030 (must run after
# _get_fix_source is defined).
# ---------------------------------------------------------------------------
_materialize_fix_as_src_module()
