import os

from typing import Literal
from agent.state import AgentState

# Retry budget is configurable so evaluation ablations (e.g. no-retry) can
# run the SAME production graph with AGENT_MAX_RETRIES=0.
MAX_RETRIES = int(os.getenv("AGENT_MAX_RETRIES", "3"))


def check_subprocess_tests(state: AgentState) -> Literal["human_approval_node", "code_writer_node", "__end__"]:
    """Conditional edge router following local subprocess test execution.

    Routes:
    - tests_passed == True -> 'human_approval_node'
    - tests_passed == False AND retry_count < MAX_RETRIES -> 'code_writer_node'
    - tests_passed == False AND retry_count >= MAX_RETRIES -> 'human_approval_node'
    """
    tests_passed = state.get("tests_passed", False)
    retry_count = state.get("retry_count", 0)

    if tests_passed:
        print("\n[Subprocess Edge] Automated tests passed! Proceeding to human_approval_node...")
        return "human_approval_node"

    if retry_count >= MAX_RETRIES:
        print(f"\n[Subprocess Edge] Maximum retry limit reached ({MAX_RETRIES}/{MAX_RETRIES}). Proceeding to human_approval_node for review...")
        return "human_approval_node"

    print(f"\n[Subprocess Edge Retry {retry_count}/{MAX_RETRIES}] Tests failed. Returning to code_writer_node with test error feedback...")
    return "code_writer_node"


def check_approval_and_retries(state: AgentState) -> Literal["pr_node", "code_writer_node", "__end__"]:
    """Conditional edge router following human_approval_node.

    Routes:
    - human_approved == True -> 'pr_node'
    - human_approved == False AND retry_count >= MAX_RETRIES -> '__end__'
    - human_approved == False AND retry_count < MAX_RETRIES -> 'code_writer_node'
    """
    human_approved = state.get("human_approved", False)
    retry_count = state.get("retry_count", 0)

    if human_approved:
        return "pr_node"

    if retry_count >= MAX_RETRIES:
        print("\n" + "!"*60)
        print(f"AGENT STOPPED: Retry limit exceeded (maximum {MAX_RETRIES} retries reached).")
        print("!"*60)
        return "__end__"

    print(f"\n[Human Review Retry Attempt {retry_count}/{MAX_RETRIES}] Returning to code_writer_node with human feedback...")
    return "code_writer_node"
