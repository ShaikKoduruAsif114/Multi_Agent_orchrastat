from typing import Literal
from agent.state import AgentState


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
        print("The agent could not produce an approved fix after 3 attempts.")
        print("!"*60)
        return "__end__"

    print(f"\n[Retry Attempt {retry_count}/3] Returning to code_writer_node with feedback...")
    return "code_writer_node"
