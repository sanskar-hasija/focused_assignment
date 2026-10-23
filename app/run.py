"""Run an agent once and record what it did. Shared by every agent in app/registry.py."""

from contextlib import closing

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


def run_agent(name: str, graph: Runnable, inp: TriageInput, db_path: str) -> RunRecord:
    """Invoke graph with {"input": inp, "db_path": db_path} and record the run.

    The graph's final state must carry the GraphOutput fields. Never raises:
    failures land in RunRecord.error.
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
            graph.invoke({"input": inp, "db_path": db_path}, config)
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
