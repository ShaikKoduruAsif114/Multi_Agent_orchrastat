import os
import sys
from pathlib import Path


def test_research_node_v2_prefers_matrix_ops(monkeypatch):
    os.environ["AGENT_LOCALIZATION_V2"] = "1"

    project_root = Path(__file__).resolve().parent
    agent_dir = project_root / "github-issue-agent"
    if str(agent_dir) not in sys.path:
        sys.path.insert(0, str(agent_dir))

    import agent.localization_v2 as localization_v2
    import agent.nodes as nodes

    repo_files = [
        "src/__init__.py",
        "src/matrix_ops.py",
        "src/other_helper.py",
    ]

    class FakeTool:
        def __init__(self, result_fn):
            self.result_fn = result_fn

        def invoke(self, payload):
            return self.result_fn(payload)

    def fake_list_repo_files(payload):
        return repo_files

    def fake_read_file(payload):
        path = payload["file_path"]
        if path == "src/__init__.py":
            return '"""Top level package."""\n__all__ = []\n'
        if path == "src/matrix_ops.py":
            return (
                "def matrix_multiply(A, B):\n"
                "    if not A or not B:\n"
                "        return []\n"
                "    if len(A[0]) != len(B):\n"
                "        raise ValueError('shape mismatch')\n"
                "    return [[sum(...) for ... in zip(*B)]]\n\n"
                "def transpose(M):\n"
                "    if not M:\n"
                "        return []\n"
                "    return [[row[i] for row in M] for i in range(len(M[0]))]\n"
            )
        return ""

    def fake_invoke_llm(messages, timeout_sec=30.0, stage="research"):
        return "src/matrix_ops.py, src/__init__.py", 10, 5

    monkeypatch.setattr(localization_v2, "list_repo_files", FakeTool(fake_list_repo_files))
    monkeypatch.setattr(localization_v2, "read_file", FakeTool(fake_read_file))
    monkeypatch.setattr(nodes, "invoke_llm_with_timeout", fake_invoke_llm)

    state = {
        "repo_url": "https://example.com/repo",
        "token": "",
        "issue_title": "Bug: matrix_multiply() silently computes garbage on shape mismatch and transpose() crashes on empty matrices",
        "issue_body": "## Bug Report\n**File:** `src/matrix_ops.py`\n`matrix_multiply` does not validate shape mismatch.",
        "session_id": "t009",
        "llm_calls": 0,
    }

    result = localization_v2.research_node_v2(state)
    assert result["relevant_files"][0] == "src/matrix_ops.py"

    monkeypatch.delenv("AGENT_LOCALIZATION_V2", raising=False)