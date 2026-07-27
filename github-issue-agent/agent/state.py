from typing import TypedDict, Annotated, List, Any
import operator
from langchain_core.messages import AnyMessage


class AgentState(TypedDict):
    # User inputs
    repo_url: str
    session_id: str
    issue_number: int
    token: str
    problem_description: str
    mode: str                    # "issue" or "smart"
    is_web: bool                 # Web UI session flag

    # Fetched from GitHub
    issue_title: str
    issue_body: str

    # Agent outputs
    relevant_files: list[str]
    proposed_fix: str
    tests_written: str
    pr_url: str

    # Automated Docker Verification
    tests_passed: bool
    test_results: str

    # Control
    messages: Annotated[list[AnyMessage], operator.add]
    human_approved: bool
    retry_count: int
    llm_calls: int
    errors: list[str]
