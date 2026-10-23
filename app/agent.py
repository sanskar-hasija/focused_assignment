"""Triage agent: load the tenant, then one tool-calling agent with structured output.

Registered in app/registry.py as "triage". `make graph` (python -m app.agent) writes
the Mermaid diagram to docs/agent.md.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.context import load_context
from app.models import RunRecord, ToolContext, ToolStep, TriageInput, TriageResult
from app.prompts import render_system_prompt
from app.run import run_agent
from app.tools import make_tools

ROOT = Path(__file__).resolve().parent.parent


class AgentState(BaseModel):
    input: TriageInput
    db_path: str
    context: ToolContext | None = None
    result: TriageResult | None = None
    tool_calls: list[str] = []
    retrieved: list[str] = []
    tool_errors: int = 0
    steps: list[ToolStep] = []


class Trajectory(BaseModel):
    tool_calls: list[str]  # tool names in call order
    retrieved: list[str]  # clause ids from search_policies, first-seen order, no repeats
    tool_errors: int  # tool results with error status
    steps: list[ToolStep]  # every call with its arguments and result, in call order


def build_react_agent(ctx: ToolContext):
    """The inner agent loop: model and tools until it can answer as a TriageResult."""
    tools = make_tools(ctx, filtered_search=False)
    model = init_chat_model(os.environ["AGENT_MODEL"], temperature=0)
    return create_agent(
        model,
        tools,
        system_prompt=render_system_prompt(ctx),
        response_format=TriageResult,
    )


def read_trajectory(messages: list[AnyMessage]) -> Trajectory:
    """What the agent did, read back from its message history."""
    tool_names = {"search_policies", "check_open_tickets", "create_ticket"}
    calls = [
        call
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls
        if call["name"] in tool_names  # skips a structured-output pseudo-tool, if used
    ]
    results = {
        message.tool_call_id: message for message in messages if isinstance(message, ToolMessage)
    }

    steps: list[ToolStep] = []
    retrieved: list[str] = []
    tool_errors = 0
    for call in calls:
        result = results.get(call["id"])
        output = str(result.content) if result else ""
        error = bool(result and result.status == "error")
        steps.append(ToolStep(name=call["name"], args=dict(call["args"]), output=output, error=error))
        if error:
            tool_errors += 1
        elif result and call["name"] == "search_policies":
            for hit in json.loads(output):
                if hit["clause_id"] not in retrieved:
                    retrieved.append(hit["clause_id"])

    return Trajectory(
        tool_calls=[step.name for step in steps], retrieved=retrieved, tool_errors=tool_errors, steps=steps
    )


# Nodes


def load_tenant(state: AgentState) -> dict:
    inp = state.input
    return {
        "context": load_context(
            state.db_path, inp.tenant_id, inp.now, inp.fail_create_ticket
        )
    }


def agent(state: AgentState) -> dict:
    assert state.context is not None
    output = build_react_agent(state.context).invoke(
        {"messages": [HumanMessage(state.input.message)]}
    )
    trajectory = read_trajectory(output["messages"])
    return {"result": output["structured_response"], **trajectory.model_dump()}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("load_tenant", load_tenant)
    graph.add_node("agent", agent)
    graph.add_edge(START, "load_tenant")
    graph.add_edge("load_tenant", "agent")
    graph.add_edge("agent", END)
    return graph.compile()


GRAPH = build_graph()


def run_triage(inp: TriageInput, db_path: str) -> RunRecord:
    """Run the triage agent on db_path. Never raises: failures land in RunRecord.error."""
    return run_agent("triage", GRAPH, inp, db_path)


def write_diagram(path: Path = ROOT / "docs" / "agent.md") -> None:
    """Mermaid for the outer graph and for the agent loop inside the agent node."""
    sample = load_context(
        ROOT / "data" / "harbour.db", "T-001", datetime(2026, 1, 14, tzinfo=UTC)
    )
    inner = build_react_agent(sample).get_graph().draw_mermaid()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Triage agent\n\n"
        "Outer graph: load the tenant's context, then run the agent.\n\n"
        f"```mermaid\n{GRAPH.get_graph().draw_mermaid()}```\n\n"
        "Inside the `agent` node: a `create_agent` loop over search_policies, "
        "check_open_tickets and create_ticket, ending in a TriageResult.\n\n"
        f"```mermaid\n{inner}```\n"
    )
    print(f"Wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    load_dotenv()
    write_diagram()
