from langgraph.graph import StateGraph, START, END

from agent.state import AgentState
from agent.nodes import (
    input_node,
    fetch_node,
    research_node,
    code_writer_node,
    test_writer_node,
    docker_execution_node,
    human_approval_node,
    pr_node,
)
from agent.edges import check_docker_tests, check_approval_and_retries


def build_graph():
    """Assemble and compile the complete GitHub Issue Agent LangGraph workflow with Docker execution."""
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("input_node", input_node)
    workflow.add_node("fetch_node", fetch_node)
    workflow.add_node("research_node", research_node)
    workflow.add_node("code_writer_node", code_writer_node)
    workflow.add_node("test_writer_node", test_writer_node)
    workflow.add_node("docker_execution_node", docker_execution_node)
    workflow.add_node("human_approval_node", human_approval_node)
    workflow.add_node("pr_node", pr_node)

    # Entry edge
    workflow.add_edge(START, "input_node")

    # Linear workflow steps
    workflow.add_edge("input_node", "fetch_node")
    workflow.add_edge("fetch_node", "research_node")
    workflow.add_edge("research_node", "code_writer_node")
    workflow.add_edge("code_writer_node", "test_writer_node")
    workflow.add_edge("test_writer_node", "docker_execution_node")

    # Conditional edge following Docker test execution
    workflow.add_conditional_edges(
        "docker_execution_node",
        check_docker_tests,
        {
            "human_approval_node": "human_approval_node",
            "code_writer_node": "code_writer_node",
            "__end__": END,
        }
    )

    # Conditional edge following human approval
    workflow.add_conditional_edges(
        "human_approval_node",
        check_approval_and_retries,
        {
            "pr_node": "pr_node",
            "code_writer_node": "code_writer_node",
            "__end__": END,
        }
    )

    # Terminal edge from PR node
    workflow.add_edge("pr_node", END)

    return workflow.compile()


app = build_graph()
