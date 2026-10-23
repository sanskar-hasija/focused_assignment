"""Triage agent V1: the same three tools, in a fixed order, with code around the model.

Six nodes. The LLM makes the judgement calls (decide, reply); code does the rest:

1. intake   load the tenant, redact phone numbers, emails and card numbers, and run a
            keyword safety screen for the five emergency types.
2. gather   always search the policies (filtered to the tenant's building, current
            documents only) and always list the flat's open tickets.
3. decide   one structured LLM call: the issues and the clauses, no reply yet.
4. gate     plain code: a safety-screen hit becomes an emergency even if decide
            disagreed; "existing" only if gather found an open ticket in that category;
            cited clauses must have been retrieved.
5. act      create the tickets marked "new"; if ticketing is down, mark them "none".
6. reply    one LLM call that writes the reply from what actually happened, safety
            steps first on emergencies.

Because the reply is written after the actions, it can only describe tickets that
exist. Registered in app/registry.py as "triage_v1". `python -m app.agent_v1` writes
the Mermaid diagram to docs/agent_v1.md.
"""

import json
import operator
import os
import re
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.tools import BaseTool
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.context import load_context
from app.models import (
    Category,
    ClauseHit,
    CreateTicketOutput,
    Issue,
    OpenTicketView,
    RunRecord,
    ToolContext,
    ToolStep,
    TriageInput,
    TriageResult,
)
from app.prompts import render_decide_prompt, render_reply_prompt
from app.run import OnEvent, run_agent
from app.tools import make_tools

ROOT = Path(__file__).resolve().parent.parent


# Intake helpers: redaction and the safety screen


CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
PHONE = re.compile(r"(?:\+44\s?7|\b07)\d{3}[ -]?\d{3}[ -]?\d{3}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def redact(text: str) -> str:
    """Replace card numbers, UK mobile numbers and emails before anything is traced."""
    text = CARD.sub("[card number removed]", text)
    text = PHONE.sub("[phone number removed]", text)
    return EMAIL.sub("[email removed]", text)


class ScreenRule(BaseModel):
    emergency: str  # as named in EMG-1.1
    category: Category
    pattern: str


SCREEN: list[ScreenRule] = [
    ScreenRule(
        emergency="gas smell", category="gas",
        pattern=r"eggy|sulphur|sulfur|rotten egg|smell(?:s|ing)? (?:of )?gas\b|gas (?:smell|leak)|gassy",
    ),
    ScreenRule(
        emergency="carbon monoxide", category="gas",
        pattern=r"carbon monoxide|\bco (?:alarm|detector)|\bco2? alarm",
    ),
    ScreenRule(
        emergency="fire or smoke", category="other",
        pattern=r"\bfire\b|\bsmoke(?! alarm| detector)|\bflames?\b",
    ),
    ScreenRule(
        emergency="burning smell or sparks from electrics", category="electrical",
        pattern=r"burning smell|smell(?:s|ing)? (?:of )?burning|\bsparks?\b|sparking|scorch",
    ),
    ScreenRule(
        emergency="water near electrics", category="electrical",
        pattern=r"water.{0,40}\b(?:light|socket|switch|electric|fuse|plug)|\b(?:light|socket|switch|fuse box|plug).{0,40}\b(?:water|wet|dripping)",
    ),
    ScreenRule(
        emergency="uncontrolled flooding", category="water",
        pattern=r"flood|pouring|gushing|can'?t stop|cannot stop|filling (?:up )?with water",
    ),
]  # fmt: skip


def screen(text: str) -> list[ScreenRule]:
    """The emergency types whose keywords appear in the message."""
    lowered = text.lower()
    return [rule for rule in SCREEN if re.search(rule.pattern, lowered)]


# State


class DecidedIssue(Issue):
    summary: str  # one line, used as the ticket summary


class Decision(BaseModel):
    issues: list[DecidedIssue]
    cited_clauses: list[str]


class IssueOutcome(BaseModel):
    """What actually happened to one issue, for the reply to describe."""

    issue: DecidedIssue
    ticket_id: str | None = None  # created or existing
    failed: bool = False  # create_ticket raised (ticketing down)


class V1State(BaseModel):
    input: TriageInput
    db_path: str
    context: ToolContext | None = None
    message: str = ""  # redacted
    screen_hits: list[ScreenRule] = []
    clauses: list[ClauseHit] = []
    open_tickets: list[OpenTicketView] = []
    decision: Decision | None = None
    outcomes: list[IssueOutcome] = []  # issues after the gate, then after act
    cited_clauses: list[str] = []
    gate_notes: list[str] = []
    result: TriageResult | None = None
    # gather and act both add to these, so they accumulate instead of overwriting.
    tool_calls: Annotated[list[str], operator.add] = []
    retrieved: list[str] = []
    tool_errors: Annotated[int, operator.add] = 0
    steps: Annotated[list[ToolStep], operator.add] = []


def _tools(ctx: ToolContext) -> dict[str, BaseTool]:
    return {tool.name: tool for tool in make_tools(ctx, filtered_search=True)}


def _model():
    return init_chat_model(os.environ["AGENT_MODEL"], temperature=0)


def _progress(text: str) -> None:
    try:
        get_stream_writer()({"status": text})
    except RuntimeError:  # not running inside a graph stream
        pass


# Nodes


def intake(state: V1State) -> dict:
    inp = state.input
    message = redact(inp.message)
    return {
        "context": load_context(state.db_path, inp.tenant_id, inp.now, inp.fail_create_ticket),
        "message": message,
        "screen_hits": screen(message),
    }


def gather(state: V1State) -> dict:
    assert state.context is not None
    tools = _tools(state.context)
    _progress("Checking the repairs policy and your building's handbook…")
    search_args = {"query": state.message, "k": 6}
    search_out = tools["search_policies"].invoke(search_args)
    clauses = [ClauseHit.model_validate(hit) for hit in json.loads(search_out)]

    _progress("Checking open tickets for your flat…")
    tickets_out = tools["check_open_tickets"].invoke({})
    open_tickets = [OpenTicketView.model_validate(t) for t in json.loads(tickets_out)]

    return {
        "clauses": clauses,
        "open_tickets": open_tickets,
        "steps": [
            ToolStep(name="search_policies", args=search_args, output=search_out),
            ToolStep(name="check_open_tickets", args={}, output=tickets_out),
        ],
        "tool_calls": ["search_policies", "check_open_tickets"],
        "retrieved": [hit.clause_id for hit in clauses],
    }


def decide(state: V1State) -> dict:
    assert state.context is not None
    _progress("Deciding what this is…")
    prompt = render_decide_prompt(state.context, state.message, state.clauses, state.open_tickets)
    decision = _model().with_structured_output(Decision).invoke(prompt)
    return {"decision": Decision.model_validate(decision)}


def gate(state: V1State) -> dict:
    """Code decides what the model is not allowed to get wrong."""
    assert state.decision is not None
    issues = [issue.model_copy() for issue in state.decision.issues]
    notes: list[str] = []
    retrieved = {hit.clause_id for hit in state.clauses}
    open_categories = {t.category for t in state.open_tickets}
    open_by_category = {t.category: t.ticket_id for t in state.open_tickets}

    # 1. The safety screen overrides a non-emergency decision.
    if state.screen_hits and not any(i.priority == "emergency" for i in issues):
        hit = state.screen_hits[0]
        match = next((i for i in issues if i.category == hit.category), None)
        if match is not None:
            notes.append(f"screen: {hit.emergency!r} upgraded {match.category} {match.priority} to emergency")
            match.priority, match.ticket = "emergency", "new"
        else:
            notes.append(f"screen: {hit.emergency!r} added an emergency issue the model did not raise")
            issues.append(
                DecidedIssue(
                    category=hit.category, priority="emergency", ticket="new",
                    summary=f"Possible {hit.emergency} reported: {state.message[:80]}",
                )  # fmt: skip
            )

    outcomes: list[IssueOutcome] = []
    for issue in issues:
        # 2. "existing" needs an open ticket in that category on this flat.
        if issue.ticket == "existing" and issue.category not in open_categories:
            notes.append(f"{issue.category}: no open ticket in this category, 'existing' became 'new'")
            issue.ticket = "new"
        # 3. Pairing rules: none with none; an emergency always gets a ticket.
        if issue.priority == "none" and issue.ticket != "none":
            notes.append(f"{issue.category}: priority none, so ticket became none")
            issue.ticket = "none"
        if issue.priority != "none" and issue.ticket == "none":
            notes.append(f"{issue.category}: priority {issue.priority} with no ticket, so ticket became new")
            issue.ticket = "new"
        if issue.priority == "emergency" and issue.ticket != "new":
            notes.append(f"{issue.category}: emergency, so ticket became new")
            issue.ticket = "new"
        ticket_id = open_by_category.get(issue.category) if issue.ticket == "existing" else None
        outcomes.append(IssueOutcome(issue=issue, ticket_id=ticket_id))

    # 4. Only clauses that search returned can be cited.
    cited = [c for c in state.decision.cited_clauses if c in retrieved]
    dropped = [c for c in state.decision.cited_clauses if c not in retrieved]
    if dropped:
        notes.append(f"dropped citations not returned by search: {', '.join(dropped)}")

    return {"outcomes": outcomes, "cited_clauses": cited, "gate_notes": notes}


def act(state: V1State) -> dict:
    assert state.context is not None
    tools = _tools(state.context)
    steps, calls, errors = [], [], 0
    outcomes = []
    for outcome in state.outcomes:
        issue = outcome.issue
        if issue.ticket != "new":
            outcomes.append(outcome)
            continue
        _progress("Logging the repair…")
        args = {
            "category": issue.category, "priority": issue.priority,
            "summary": issue.summary, "cited_clauses": state.cited_clauses,
        }  # fmt: skip
        out = tools["create_ticket"].invoke(args)
        calls.append("create_ticket")
        try:
            created = CreateTicketOutput.model_validate_json(out)
            steps.append(ToolStep(name="create_ticket", args=args, output=out))
            outcomes.append(outcome.model_copy(update={"ticket_id": created.ticket_id}))
        except ValueError:  # the tool returned its error message instead of JSON
            errors += 1
            steps.append(ToolStep(name="create_ticket", args=args, output=out, error=True))
            failed = issue.model_copy(update={"ticket": "none"})
            outcomes.append(IssueOutcome(issue=failed, failed=True))
    return {"outcomes": outcomes, "steps": steps, "tool_calls": calls, "tool_errors": errors}


def reply(state: V1State) -> dict:
    assert state.context is not None
    _progress("Writing the reply…")
    prompt = render_reply_prompt(state.context, state.message, state.outcomes, state.clauses, state.cited_clauses)
    text = _model().invoke(prompt).text
    issues = [Issue(category=o.issue.category, priority=o.issue.priority, ticket=o.issue.ticket) for o in state.outcomes]
    return {"result": TriageResult(issues=issues, cited_clauses=state.cited_clauses, reply=text)}


# Graph


def build_graph():
    graph = StateGraph(V1State)
    for name, node in [
        ("intake", intake), ("gather", gather), ("decide", decide),
        ("gate", gate), ("act", act), ("reply", reply),
    ]:  # fmt: skip
        graph.add_node(name, node)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "gather")
    graph.add_edge("gather", "decide")
    graph.add_edge("decide", "gate")
    graph.add_edge("gate", "act")
    graph.add_edge("act", "reply")
    graph.add_edge("reply", END)
    return graph.compile()


GRAPH = build_graph()


def run_triage_v1(inp: TriageInput, db_path: str, on_event: OnEvent | None = None) -> RunRecord:
    """Run V1 on db_path. Redacts before the graph so the trace root never holds PII.
    With on_event, progress and the reply's tokens stream to the listener."""
    safe = inp.model_copy(update={"message": redact(inp.message)})
    return run_agent("triage_v1", GRAPH, safe, db_path, on_event)


def write_diagram(path: Path = ROOT / "docs" / "agent_v1.md") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Triage agent V1\n\n"
        "Six nodes in a fixed order. The LLM runs in `decide` and `reply`; the other four are code.\n\n"
        f"```mermaid\n{GRAPH.get_graph().draw_mermaid()}```\n"
    )
    print(f"Wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    load_dotenv()
    write_diagram()
