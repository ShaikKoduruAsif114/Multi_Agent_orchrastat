import operator
from typing import Literal
from typing_extensions import TypedDict, Annotated

from langchain.tools import tool
from langchain_ollama import ChatOllama
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, START, END


# ─────────────────────────────────────────
# 1. DEFINE THE MODEL
# ─────────────────────────────────────────

model = ChatOllama(
    model="llama3.2",
    temperature=0
)


# ─────────────────────────────────────────
# 2. DEFINE TOOLS
# ─────────────────────────────────────────

@tool
def multiply(a: int, b: int) -> int:
    """Multiply a and b.

    Args:
        a: First int
        b: Second int
    """
    return a * b


@tool
def add(a: int, b: int) -> int:
    """Adds a and b.

    Args:
        a: First int
        b: Second int
    """
    return a + b


@tool
def divide(a: int, b: int) -> float:
    """Divide a by b.

    Args:
        a: First int
        b: Second int
    """
    if b == 0:
        return "Error: Cannot divide by zero"
    return a / b


# ─────────────────────────────────────────
# 3. BIND TOOLS TO MODEL
# ─────────────────────────────────────────

tools = [add, multiply, divide]
tools_by_name = {tool.name: tool for tool in tools}
model_with_tools = model.bind_tools(tools)


# ─────────────────────────────────────────
# 4. DEFINE STATE
# ─────────────────────────────────────────

class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int


# ─────────────────────────────────────────
# 5. DEFINE NODES
# ─────────────────────────────────────────

def llm_call(state: MessagesState):
    """LLM decides whether to call a tool or not"""

    print("\n--- LLM CALL ---")
    print(f"Total LLM calls so far: {state.get('llm_calls', 0)}")

    response = model_with_tools.invoke(
        [
            SystemMessage(
                content="You are a helpful assistant tasked with performing arithmetic on a set of inputs. You have access to tools for math operations. Always use the tools to calculate, never calculate yourself."
            )
        ]
        + state["messages"]
    )

    print(f"Model responded with: {response.content}")
    if hasattr(response, 'tool_calls') and response.tool_calls:
        print(f"Tool calls requested: {[tc['name'] for tc in response.tool_calls]}")

    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


def tool_node(state: MessagesState):
    """Performs the tool call"""

    print("\n--- TOOL NODE ---")

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        print(f"Running tool: {tool_call['name']} with args: {tool_call['args']}")
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        print(f"Tool result: {observation}")
        result.append(
            ToolMessage(
                content=str(observation),
                tool_call_id=tool_call["id"]
            )
        )

    return {"messages": result}


# ─────────────────────────────────────────
# 6. DEFINE CONDITIONAL EDGE
# ─────────────────────────────────────────

def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    """Decide if we should continue the loop or stop"""

    print("\n--- SHOULD CONTINUE ---")

    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls:
        print("Decision: GO TO TOOL NODE")
        return "tool_node"

    print("Decision: END")
    return END


# ─────────────────────────────────────────
# 7. BUILD THE GRAPH
# ─────────────────────────────────────────

agent_builder = StateGraph(MessagesState)

# Add nodes
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)

# Add edges
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    ["tool_node", END]
)
agent_builder.add_edge("tool_node", "llm_call")

# Compile
agent = agent_builder.compile()

print("Agent compiled successfully")


# ─────────────────────────────────────────
# 8. RUN FUNCTION
# ─────────────────────────────────────────

def run_agent(question: str):
    print("\n" + "="*50)
    print(f"QUESTION: {question}")
    print("="*50)

    messages = [HumanMessage(content=question)]
    result = agent.invoke({"messages": messages})

    print("\n--- FINAL CONVERSATION ---")
    for m in result["messages"]:
        m.pretty_print()

    print(f"\nTotal LLM calls made: {result['llm_calls']}")
    return result


# ─────────────────────────────────────────
# 9. TEST IT
# ─────────────────────────────────────────

if __name__ == "__main__":

    # Test 1: Simple addition
    run_agent("ping 3 and 4.")
