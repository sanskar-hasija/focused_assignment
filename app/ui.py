"""Streamlit app: talk to an agent as a tenant and inspect every step it took.

make ui   (streamlit run app/ui.py)

Works on data/ui.db, a fresh copy of data/harbour.db made when the app starts or when
you press Reset, so tickets persist across messages until you reset. Each message is a
separate run; the agent has no memory of earlier messages.
"""

import json
import os
import shutil
import warnings
from contextlib import closing
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from langchain_core.tracers.context import collect_runs
from langsmith import Client

from app import db
from app.models import RunRecord, TriageInput
from app.registry import AGENTS
from app.seed_data import BUILDINGS, FLATS, TENANTS
from evals.examples import EXAMPLES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TEMPLATE_DB = DATA_DIR / "harbour.db"
UI_DB = DATA_DIR / "ui.db"
DEFAULT_NOW = datetime(2026, 1, 14, 19, 30)

_BUILDING = {b.id: b for b in BUILDINGS}
_FLAT = {f.id: f for f in FLATS}
TENANT_LABELS = {
    t.id: f"{t.id} · {t.name} · {t.flat_id} {_BUILDING[_FLAT[t.flat_id].building_id].name}"
    for t in TENANTS
}
EXAMPLE_BY_ID = {e.id: e for e in EXAMPLES}


def reset_db() -> None:
    shutil.copyfile(TEMPLATE_DB, UI_DB)
    st.session_state.history = []


def open_tickets(tenant_id: str):
    with closing(db.connect(UI_DB)) as conn:
        tenant = db.get_tenant(conn, tenant_id)
        return db.list_open_tickets(conn, tenant.flat_id) if tenant else []


def trace_url(run_id) -> str | None:
    if not os.getenv("LANGSMITH_API_KEY") or run_id is None:
        return None
    try:
        client = Client()
        with warnings.catch_warnings():  # get_run_url is deprecated; see evals/run_eval.py
            warnings.simplefilter("ignore", DeprecationWarning)
            return client.get_run_url(
                run=client.read_run(run_id), project_name=os.getenv("LANGSMITH_PROJECT", "triage")
            )
    except Exception:
        return None


def run_once(agent: str, inp: TriageInput, status, reply_box) -> tuple[RunRecord, str | None]:
    """Run the agent; V1 streams progress lines and the reply's tokens as it goes."""
    tokens: list[str] = []

    def on_event(kind: str, payload) -> None:
        if kind == "status":
            status.caption(payload)
        elif kind == "token":
            tokens.append(payload)
            reply_box.markdown("".join(tokens) + "▌")

    run = AGENTS[agent]
    with collect_runs() as runs:
        if agent == "triage_v1":
            record = run(inp, str(UI_DB), on_event)  # type: ignore[call-arg]
        else:
            status.caption("Thinking… (V0 decides its own steps; nothing to stream)")
            record = run(inp, str(UI_DB))
    status.empty()
    reply_box.empty()
    run_id = runs.traced_runs[0].id if runs.traced_runs else None
    return record, trace_url(run_id)


def pretty(text: str) -> str:
    try:
        return json.dumps(json.loads(text), indent=2)
    except (json.JSONDecodeError, TypeError):
        return text


def show_record(record: RunRecord, url: str | None, inp: TriageInput) -> None:
    if record.error:
        st.error(f"Run failed: {record.error}")
    if record.result:
        st.markdown(record.result.reply)
        issues = record.result.issues
        if issues:
            st.table([{"category": i.category, "priority": i.priority, "ticket": i.ticket} for i in issues])
        else:
            st.caption("No issues identified (reply only).")
        st.caption("Cited: " + (", ".join(record.result.cited_clauses) or "nothing"))
    for ticket in record.tickets_created:
        paged = " · on-call manager PAGED" if ticket.paged_on_call else ""
        st.success(f"Created {ticket.id}: {ticket.priority} {ticket.category}{paged}")

    with st.expander(f"Steps: {' → '.join(record.tool_calls) or 'no tool calls'}", expanded=False):
        if not record.steps:
            st.caption("This run made no tool calls.")
        for n, step in enumerate(record.steps, start=1):
            icon = "❌" if step.error else "✅"
            st.markdown(f"**{n}. {icon} `{step.name}`**")
            left, right = st.columns(2)
            with left:
                st.caption("Input")
                st.code(json.dumps(step.args, indent=2), language="json")
            with right:
                st.caption("Output")
                st.code(pretty(step.output), language="json" if not step.error else None)
    if url:
        st.markdown(f"[Open the trace in LangSmith]({url})")


def main() -> None:
    load_dotenv()
    st.set_page_config(page_title="Harbour Lettings triage", page_icon="🔧", layout="wide")
    if "history" not in st.session_state or not UI_DB.exists():
        reset_db()

    with st.sidebar:
        st.title("Harbour Lettings triage")
        agent = st.selectbox("Agent", sorted(AGENTS), index=0)
        example_id = st.selectbox(
            "Load a dataset example",
            ["(none)"] + list(EXAMPLE_BY_ID),
            format_func=lambda i: i if i == "(none)" else f"{i}: {EXAMPLE_BY_ID[i].inputs.message[:48]}",
        )
        example = EXAMPLE_BY_ID.get(example_id)
        tenant_ids = list(TENANT_LABELS)
        tenant = st.selectbox(
            "Tenant", tenant_ids,
            index=tenant_ids.index(example.inputs.tenant_id) if example else 2,
            format_func=TENANT_LABELS.__getitem__,
        )  # fmt: skip
        default_now = example.inputs.now.replace(tzinfo=None) if example else DEFAULT_NOW
        day = st.date_input("Date", default_now.date())
        time = st.time_input("Time", default_now.time())
        outage = st.toggle("Ticketing system down", value=bool(example and example.inputs.fail_create_ticket))
        if st.button("Reset database"):
            reset_db()
            st.rerun()
        st.divider()
        st.caption("Open tickets on this flat")
        tickets = open_tickets(tenant)
        if tickets:
            st.table([{"id": t.id, "category": t.category, "priority": t.priority, "summary": t.summary} for t in tickets])
        else:
            st.caption("none")
        if example:
            ref = example.reference
            st.divider()
            st.caption("Expected (from the dataset)")
            st.write(", ".join(f"{i.category}/{i.priority}/{i.ticket}" for i in ref.issues) or "no issues")
            st.caption(f"gold {', '.join(ref.gold_clauses) or '-'} · forbidden {', '.join(ref.forbidden_clauses) or '-'}")

    st.subheader(f"Talking to `{agent}` as {TENANT_LABELS[tenant]}")
    for past in st.session_state.history:
        with st.chat_message("user"):
            st.write(past["message"])
        with st.chat_message("assistant"):
            show_record(past["record"], past["url"], past["input"])

    send_example = st.button("Send the example message", disabled=not example)
    typed = st.chat_input("Describe the problem in your flat")
    message = typed or (example.inputs.message if send_example and example else None)
    if message:
        inp = TriageInput(
            message=message, tenant_id=tenant,
            now=datetime.combine(day, time), fail_create_ticket=outage,
        )  # fmt: skip
        with st.chat_message("user"):
            st.write(message)
        with st.chat_message("assistant"):
            status, reply_box = st.empty(), st.empty()
            record, url = run_once(agent, inp, status, reply_box)
            show_record(record, url, inp)
        st.session_state.history.append({"message": message, "record": record, "url": url, "input": inp})
        st.rerun()


main()
