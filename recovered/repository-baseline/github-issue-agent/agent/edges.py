from typing import Literal
from agent.state import AgentState


def check_docker_tests(state: AgentState) -> Literal["human_approval_node", "code_writer_node", "__end__"]:
    """Conditional edge router following docker_execution_node.
    
    Routes:
    - tests_passed == True -> 'human_approval_node'
    - tests_passed == False AND retry_count <= 3 -> 'code_writer_node'
    - tests_passed == False AND retry_count > 3 -> 'human_approval_node'
    """
    tests_passed = state.get("tests_passed", False)
    retry_count = state.get("retry_count", 0)

    if tests_passed:
        print("\n[Docker Edge] Automated tests passed! Proceeding to human_approval_node...")
        return "human_approval_node"

    if retry_count > 3:
        print("\n[Docker Edge] Maximum retry limit reached (3/3). Proceeding to human_approval_node for review...")
        return "human_approval_node"

    print(f"\n[Docker Edge Retry {retry_count}/3] Tests failed. Returning to code_writer_node with test error feedback...")
    return "code_writer_node"


def check_approval_and_retries(state: AgentState) -> Literal["pr_node", "code_writer_node", "__end__"]:
    """Conditional edge router following human_approval_node.
    
    Routes:
    - human_approved == True -> 'pr_node'
    - human_approved == False AND retry_count > 3 -> '__end__'
    - human_approved == False AND retry_count <= 3 -> 'code_writer_node'
    """
    human_approved = state.get("human_approved", False)
    retry_count = state.get("retry_count", 0)

    if human_approved:
        return "pr_node"

    if retry_count > 3:
        print("\n" + "!"*60)
        print("AGENT STOPPED: Retry limit exceeded (maximum 3 retries reached).")
        print("!"*60)
        return "__end__"

    print(f"\n[Human Review Retry Attempt {retry_count}/3] Returning to code_writer_node with human feedback...")
    return "code_writer_node"
