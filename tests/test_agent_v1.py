"""V1's code nodes (intake, gate, act) without an LLM, plus one shape test with the model."""

import os
from datetime import UTC, datetime

import pytest

from app import db
from app.agent_v1 import (
    DecidedIssue,
    Decision,
    IssueOutcome,
    V1State,
    act,
    gate,
    intake,
    redact,
    run_triage_v1,
    screen,
)
from app.context import load_context
from app.models import ClauseHit, OpenTicketView, TriageInput, TriageResult
from app.seed import count_rows

NOW = datetime(2026, 1, 14, 19, 30, tzinfo=UTC)

llm = pytest.mark.skipif(
    not (os.getenv("OPENAI_API_KEY") and os.getenv("AGENT_MODEL")),
    reason="OPENAI_API_KEY and AGENT_MODEL are needed",
)


def hit(clause_id: str, building: str | None = None) -> ClauseHit:
    return ClauseHit(clause_id=clause_id, doc_title="t", building_id=building, status="current", text="x", distance=0.1)


def decided(spec: str, summary: str = "s") -> DecidedIssue:
    category, priority, ticket = spec.split("/")
    return DecidedIssue(category=category, priority=priority, ticket=ticket, summary=summary)


def state(db_path, tenant="T-003", message="x", decision=None, clauses=(), open_tickets=(), **kw) -> V1State:
    inp = TriageInput(message=message, tenant_id=tenant, now=NOW, **kw)
    return V1State(
        input=inp, db_path=str(db_path), context=load_context(db_path, tenant, NOW, inp.fail_create_ticket),
        message=message, screen_hits=screen(message), decision=decision,
        clauses=list(clauses), open_tickets=list(open_tickets),
    )  # fmt: skip


# Intake


def test_redaction_removes_cards_phones_and_emails_but_not_the_gas_number():
    text = "My number is 07700 900123 and my card is 4111 1111 1111 1111, email me@example.com. Call 0800 111 999."
    out = redact(text)
    assert "07700" not in out and "4111" not in out and "example.com" not in out
    assert "[phone number removed]" in out and "[card number removed]" in out and "[email removed]" in out
    assert "0800 111 999" in out


@pytest.mark.parametrize(
    "message, emergencies",
    [
        ("weird eggy smell in the kitchen", ["gas smell"]),
        ("Small thing, no rush - slight smell of gas by the hob", ["gas smell"]),
        ("The carbon monoxide alarm is going off", ["carbon monoxide"]),
        ("Smoke is coming out of the bin store", ["fire or smoke"]),
        ("The smoke alarm beeps once every minute", []),
        ("burning smell near the fuse box", ["burning smell or sparks from electrics"]),
        ("Water is dripping out of the ceiling light", ["water near electrics"]),
        ("The basement store is filling up with water", ["uncontrolled flooding"]),
        ("My gas bill seems far too high this month", []),
        ("the kitchen tap is still dripping", []),
    ],
)
def test_safety_screen(message, emergencies):
    assert [rule.emergency for rule in screen(message)] == emergencies


def test_intake_loads_context_and_redacts(offline_db):
    out = intake(V1State(input=TriageInput(message="ring 07700 900123, gas smell", tenant_id="T-010", now=NOW), db_path=str(offline_db)))
    assert out["context"].building.id == "B"
    assert "07700" not in out["message"]
    assert [r.category for r in out["screen_hits"]] == ["gas"]


# Gate


def test_gate_promotes_a_screen_hit_the_model_missed(offline_db):
    st = state(offline_db, message="weird eggy smell in the kitchen", decision=Decision(issues=[], cited_clauses=[]))
    out = gate(st)
    [outcome] = out["outcomes"]
    assert (outcome.issue.category, outcome.issue.priority, outcome.issue.ticket) == ("gas", "emergency", "new")
    assert out["gate_notes"][0].startswith("screen: 'gas smell' added")


def test_gate_upgrades_a_matching_issue_instead_of_adding_one(offline_db):
    decision = Decision(issues=[decided("gas/routine/new")], cited_clauses=[])
    out = gate(state(offline_db, message="slight smell of gas, no rush", decision=decision))
    [outcome] = out["outcomes"]
    assert outcome.issue.priority == "emergency" and outcome.issue.ticket == "new"


def test_gate_leaves_a_real_emergency_alone(offline_db):
    decision = Decision(issues=[decided("gas/emergency/new")], cited_clauses=[])
    out = gate(state(offline_db, message="smell of gas", decision=decision))
    assert out["gate_notes"] == []


def test_gate_existing_needs_an_open_ticket_in_that_category(offline_db):
    open_tap = OpenTicketView(ticket_id="TK-0001", category="water", priority="routine", summary="tap", created_at=NOW)
    decision = Decision(issues=[decided("water/routine/existing"), decided("security/urgent/existing")], cited_clauses=[])
    out = gate(state(offline_db, decision=decision, open_tickets=[open_tap]))
    water, security = out["outcomes"]
    assert water.issue.ticket == "existing" and water.ticket_id == "TK-0001"
    assert security.issue.ticket == "new" and security.ticket_id is None


def test_gate_pairing_rules(offline_db):
    decision = Decision(
        issues=[decided("electrical/none/new"), decided("water/urgent/none"), decided("gas/emergency/existing")],
        cited_clauses=[],
    )
    out = gate(state(offline_db, decision=decision))
    assert [o.issue.ticket for o in out["outcomes"]] == ["none", "new", "new"]


def test_gate_drops_citations_that_were_not_retrieved(offline_db):
    decision = Decision(issues=[], cited_clauses=["POL2-3.2", "POL1-3.1"])
    out = gate(state(offline_db, decision=decision, clauses=[hit("POL2-3.2")]))
    assert out["cited_clauses"] == ["POL2-3.2"]
    assert "POL1-3.1" in out["gate_notes"][-1]


# Act


def test_act_creates_tickets_for_new_issues_only(offline_db, tmp_path):
    path = db.fresh_copy(offline_db, tmp_path)
    st = state(path)
    st.outcomes = [
        IssueOutcome(issue=decided("water/urgent/new", "bath tap leaking")),
        IssueOutcome(issue=decided("electrical/none/none")),
        IssueOutcome(issue=decided("gas/emergency/new", "gas smell")),
    ]
    st.cited_clauses = ["POL2-3.2"]
    out = act(st)
    assert [o.ticket_id for o in out["outcomes"]] == ["TK-0006", None, "TK-0007"]
    assert out["tool_calls"] == ["create_ticket", "create_ticket"]
    assert out["tool_errors"] == 0
    with db.connect(path) as conn:
        assert count_rows(conn).tickets == 7
        assert db.get_ticket(conn, "TK-0007").paged_on_call is True


def test_act_marks_issues_none_when_ticketing_is_down(offline_db, tmp_path):
    path = db.fresh_copy(offline_db, tmp_path)
    st = state(path, fail_create_ticket=True)
    st.outcomes = [IssueOutcome(issue=decided("security/urgent/new", "lock"))]
    out = act(st)
    [outcome] = out["outcomes"]
    assert outcome.failed and outcome.issue.ticket == "none" and outcome.issue.priority == "urgent"
    assert out["tool_errors"] == 1 and out["steps"][0].error
    with db.connect(path) as conn:
        assert count_rows(conn).tickets == 5


# With the model


@pytest.mark.llm
@llm
def test_v1_gas_smell_is_an_emergency_by_construction(openai_db, tmp_path):
    path = db.fresh_copy(openai_db, tmp_path)
    record = run_triage_v1(TriageInput(message="weird eggy smell in the kitchen", tenant_id="T-003", now=NOW), path)
    assert record.error is None
    assert isinstance(record.result, TriageResult)
    assert any(i.priority == "emergency" for i in record.result.issues)
    assert record.tool_calls[:2] == ["search_policies", "check_open_tickets"]
    assert [t.paged_on_call for t in record.tickets_created] == [True]


def test_run_agent_streams_status_and_reply_tokens(offline_db, tmp_path):
    """A listener gets progress from get_stream_writer and tokens from a node named reply."""
    from langchain_core.messages import AIMessageChunk
    from langchain_core.runnables import RunnableGenerator
    from langgraph.config import get_stream_writer
    from langgraph.graph import START, END, StateGraph
    from pydantic import BaseModel

    from app.run import run_agent

    class S(BaseModel):
        input: TriageInput
        db_path: str
        result: TriageResult | None = None

    def work(state: S) -> dict:
        get_stream_writer()({"status": "Checking…"})
        return {}

    def reply_node(state: S) -> dict:
        # "messages" mode only streams chat-model tokens, which need a real model; this
        # generator stands in so the node runs, and the status event is what is asserted.
        def chunks(_):
            yield AIMessageChunk(content="Hel")
            yield AIMessageChunk(content="lo")

        text = "".join(c.text for c in RunnableGenerator(chunks).stream(None))
        return {"result": TriageResult(issues=[], cited_clauses=[], reply=text)}

    g = StateGraph(S)
    g.add_node("work", work)
    g.add_node("reply", reply_node)
    g.add_edge(START, "work"); g.add_edge("work", "reply"); g.add_edge("reply", END)
    events = []
    record = run_agent("fake", g.compile(), TriageInput(message="m", tenant_id="T-003", now=NOW),
                       db.fresh_copy(offline_db, tmp_path), on_event=lambda k, v: events.append((k, v)))
    assert record.result.reply == "Hello"
    assert ("status", "Checking…") in events
