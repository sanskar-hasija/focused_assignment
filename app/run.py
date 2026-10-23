"""Run an agent once and record what it did. Shared by every agent in app/registry.py."""

from collections.abc import Callable
from contextlib import closing
from typing import Any

from langchain_core.runnables import Runnable
from pydantic import BaseModel

from app import db
from app.models import RunRecord, ToolStep, TriageInput, TriageResult


class GraphOutput(BaseModel):
    """The fields run_agent reads from an agent graph's final state."""

    result: TriageResult | None = None
    tool_calls: list[str] = []
    retrieved: list[str] = []
    tool_errors: int = 0
    steps: list[ToolStep] = []


def _building_id(db_path: str, tenant_id: str) -> str | None:
    with closing(db.connect(db_path)) as conn:
        tenant = db.get_tenant(conn, tenant_id)
        flat = db.get_flat(conn, tenant.flat_id) if tenant else None
        return flat.building_id if flat else None


OnEvent = Callable[[str, Any], None]  # kind ("status" or "token") and its payload


def _invoke(graph: Runnable, state: dict, config: dict, on_event: OnEvent | None) -> dict:
    """graph.invoke, or graph.stream when a listener wants progress and reply tokens."""
    if on_event is None:
        return graph.invoke(state, config)
    final: dict = {}
    for mode, chunk in graph.stream(state, config, stream_mode=["custom", "messages", "values"]):
        if mode == "values":
            final = chunk
        elif mode == "custom" and isinstance(chunk, dict) and "status" in chunk:
            on_event("status", chunk["status"])
        elif mode == "messages":
            message, metadata = chunk
            if metadata.get("langgraph_node") == "reply" and getattr(message, "text", ""):
                on_event("token", message.text)
    return final


def run_agent(
    name: str, graph: Runnable, inp: TriageInput, db_path: str, on_event: OnEvent | None = None
) -> RunRecord:
    """Invoke graph with {"input": inp, "db_path": db_path} and record the run.

    The graph's final state must carry the GraphOutput fields. Never raises:
    failures land in RunRecord.error. With on_event, the graph is streamed and the
    listener gets ("status", text) from nodes that report progress and ("token", text)
    for each token of a node named "reply".
    """
    with closing(db.connect(db_path)) as conn:
        before = db.highest_ticket_number(conn)

    config = {
        "run_name": name,
        "metadata": {
            "agent": name,
            "tenant_id": inp.tenant_id,
            "building_id": _building_id(db_path, inp.tenant_id),
        },
    }
    try:
        output = GraphOutput.model_validate(
            _invoke(graph, {"input": inp, "db_path": db_path}, config, on_event)
        )
        error = None
    except Exception as exc:
        output = GraphOutput()
        error = f"{type(exc).__name__}: {exc}"

    # Read side effects from the database even after a failure: a run can
    # create a ticket and then crash.
    with closing(db.connect(db_path)) as conn:
        tickets_created = db.list_tickets_after(conn, before)

    return RunRecord(
        agent=name,
        result=output.result,
        tickets_created=tickets_created,
        tool_calls=output.tool_calls,
        retrieved=output.retrieved,
        tool_errors=output.tool_errors,
        steps=output.steps,
        error=error,
    )
