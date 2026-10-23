"""Shape checks for the agent. Quality is the evaluation's job, not these tests'."""

import json
import os
from datetime import UTC, datetime

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app import db
from app.agent import read_trajectory, run_triage
from app.context import load_context
from app.eval_target import make_target
from app.models import CreateTicketInput, RunRecord, TriageInput, TriageResult
from app.registry import AGENTS
from app.run import run_agent
from app.seed import count_rows
from app.tools import create_ticket, make_tools

NOW = datetime(2026, 1, 14, 19, 30, tzinfo=UTC)

llm = pytest.mark.skipif(
    not (os.getenv("OPENAI_API_KEY") and os.getenv("AGENT_MODEL")),
    reason="OPENAI_API_KEY and AGENT_MODEL are needed",
)


def ticket_count(path: str) -> int:
    conn = db.connect(path)
    try:
        return count_rows(conn).tickets
    finally:
        conn.close()


# No LLM


def test_toolnode_turns_invalid_arguments_into_an_error_message(offline_db, tmp_path):
    path = db.fresh_copy(offline_db, tmp_path)
    # ToolNode needs a graph runtime, so run it as a one-node graph, as create_agent does.
    graph = StateGraph(MessagesState)
    graph.add_node("tools", ToolNode(make_tools(load_context(path, "T-003", NOW))))
    graph.add_edge(START, "tools")
    node = graph.compile()
    call = {
        "name": "create_ticket",
        "args": {"category": "plumbing", "priority": "urgent", "summary": "Leaking pipe"},
        "id": "call_1",
    }

    messages = node.invoke({"messages": [AIMessage(content="", tool_calls=[call])]})["messages"]

    [reply] = [m for m in messages if isinstance(m, ToolMessage)]
    assert reply.status == "error"
    assert "category" in reply.content
    assert ticket_count(path) == 5


def test_read_trajectory():
    messages = [
        AIMessage(content="", tool_calls=[
            {"name": "search_policies", "args": {"query": "gas"}, "id": "1"},
            {"name": "check_open_tickets", "args": {}, "id": "2"},
        ]),
        ToolMessage(name="search_policies", tool_call_id="1", content=json.dumps([
            {"clause_id": "EMG-2.1"}, {"clause_id": "EMG-1.1"},
        ])),
        ToolMessage(name="check_open_tickets", tool_call_id="2", content="[]"),
        AIMessage(content="", tool_calls=[
            {"name": "search_policies", "args": {"query": "meter"}, "id": "3"},
            {"name": "create_ticket", "args": {}, "id": "4"},
        ]),
        ToolMessage(name="search_policies", tool_call_id="3", content=json.dumps([
            {"clause_id": "EMG-1.1"}, {"clause_id": "EMG-3.1"},
        ])),
        ToolMessage(name="create_ticket", tool_call_id="4", status="error",
                    content="ticketing system unavailable"),
    ]  # fmt: skip

    trajectory = read_trajectory(messages)

    assert trajectory.tool_calls == [
        "search_policies", "check_open_tickets", "search_policies", "create_ticket",
    ]  # fmt: skip
    assert trajectory.retrieved == ["EMG-2.1", "EMG-1.1", "EMG-3.1"]
    assert trajectory.tool_errors == 1
    assert [(s.name, s.args, s.error) for s in trajectory.steps] == [
        ("search_policies", {"query": "gas"}, False),
        ("check_open_tickets", {}, False),
        ("search_policies", {"query": "meter"}, False),
        ("create_ticket", {}, True),
    ]
    assert trajectory.steps[1].output == "[]"
    assert trajectory.steps[3].output == "ticketing system unavailable"


def test_run_agent_records_a_graphs_output(offline_db, tmp_path):
    path = db.fresh_copy(offline_db, tmp_path)
    inp = TriageInput(message="tap dripping", tenant_id="T-003", now=NOW)
    result = TriageResult(issues=[], cited_clauses=["POL2-4.1"], reply="Already reported.")
    graph = RunnableLambda(lambda state: {
        "input": state["input"],
        "result": result,
        "tool_calls": ["check_open_tickets"],
        "tool_errors": 1,
    })  # fmt: skip

    record = run_agent("fake", graph, inp, path)

    assert record.agent == "fake"
    assert record.result == result
    assert record.tool_calls == ["check_open_tickets"]
    assert record.retrieved == [] and record.tool_errors == 1
    assert record.tickets_created == [] and record.error is None


def test_run_agent_keeps_tickets_written_before_a_crash(offline_db, tmp_path):
    path = db.fresh_copy(offline_db, tmp_path)
    inp = TriageInput(message="gas smell", tenant_id="T-003", now=NOW)

    def create_then_crash(state):
        ctx = load_context(state["db_path"], "T-003", NOW)
        create_ticket(ctx, CreateTicketInput(category="gas", priority="emergency", summary="Gas"))
        raise RuntimeError("model timed out")

    record = run_agent("fake", RunnableLambda(create_then_crash), inp, path)

    assert record.error == "RuntimeError: model timed out"
    assert record.result is None
    assert [t.id for t in record.tickets_created] == ["TK-0006"]
    assert record.tickets_created[0].paged_on_call is True


def test_registry_and_targets():
    assert AGENTS["triage"] is run_triage
    assert callable(make_target("triage"))
    with pytest.raises(ValueError, match="nope"):
        make_target("nope")


# Real LLM


def run(openai_db, tmp_path, message: str, tenant_id: str, **kwargs) -> tuple[RunRecord, str]:
    path = db.fresh_copy(openai_db, tmp_path)
    inp = TriageInput(message=message, tenant_id=tenant_id, now=NOW, **kwargs)
    return run_triage(inp, path), path


@pytest.mark.llm
@llm
def test_gas_smell_returns_a_triage_result(openai_db, tmp_path):
    record, _ = run(openai_db, tmp_path, "weird eggy smell in the kitchen", "T-003")
    assert record.error is None
    assert isinstance(record.result, TriageResult)


@pytest.mark.llm
@llm
def test_noise_complaint_returns_a_triage_result(openai_db, tmp_path):
    record, _ = run(openai_db, tmp_path, "my neighbour's music is too loud", "T-010")
    assert record.error is None
    assert isinstance(record.result, TriageResult)


@pytest.mark.llm
@llm
def test_ticketing_outage_completes_without_writing(openai_db, tmp_path):
    record, path = run(
        openai_db, tmp_path, "the kitchen tap is dripping", "T-001", fail_create_ticket=True
    )
    assert record.error is None
    assert isinstance(record.result, TriageResult)
    assert record.tickets_created == []
    assert ticket_count(path) == 5
