import json
import logging
from contextlib import closing
from datetime import UTC, datetime

import pytest

from app import db
from app.context import UnknownTenant, load_context
from app.models import CheckOpenTicketsInput, CreateTicketInput, SearchPoliciesInput
from app.seed import count_rows
from app.tools import (
    TicketingUnavailable,
    check_open_tickets,
    create_ticket,
    make_tools,
    search_policies,
)

NOW = datetime(2026, 2, 3, 14, 30, tzinfo=UTC)

GAS_LEAK = CreateTicketInput(
    category="gas",
    priority="emergency",
    summary="Strong smell of gas in the kitchen",
    cited_clauses=["EMG-1.1", "EMG-2.1"],
)
NO_HEATING = CreateTicketInput(
    category="heating",
    priority="urgent",
    summary="No heating since this morning",
    cited_clauses=["POL2-3.2"],
)


@pytest.fixture
def run_db(offline_db, tmp_path) -> str:
    """A fresh copy of the seeded database for one test, as each agent run gets."""
    return db.fresh_copy(offline_db, tmp_path)


def tool(tools, name):
    return next(t for t in tools if t.name == name)


def ticket_count(path: str) -> int:
    conn = db.connect(path)
    try:
        return count_rows(conn).tickets
    finally:
        conn.close()


def test_load_context(run_db):
    ctx = load_context(run_db, "T-010", NOW)
    assert (ctx.tenant.id, ctx.flat.id, ctx.building.id) == ("T-010", "B-3", "B")
    assert ctx.now == NOW and ctx.fail_create_ticket is False


def test_load_context_rejects_an_unknown_tenant(run_db):
    with pytest.raises(UnknownTenant, match="T-999"):
        load_context(run_db, "T-999", NOW)


def test_check_open_tickets_is_scoped_to_the_tenants_flat(run_db):
    ctx = load_context(run_db, "T-003", NOW)
    assert [t.id for t in check_open_tickets(ctx, CheckOpenTicketsInput())] == ["TK-0001"]
    assert check_open_tickets(ctx, CheckOpenTicketsInput(category="heating")) == []

    # T-006's only ticket, TK-0005, is closed.
    ctx = load_context(run_db, "T-006", NOW)
    assert check_open_tickets(ctx, CheckOpenTicketsInput()) == []


def test_check_open_tickets_tool_returns_a_slim_view(run_db):
    tools = make_tools(load_context(run_db, "T-003", NOW))
    [ticket] = json.loads(tool(tools, "check_open_tickets").invoke({}))
    assert ticket == {
        "ticket_id": "TK-0001",
        "category": "water",
        "priority": "routine",
        "summary": "Kitchen tap dripping constantly",
        "created_at": "2026-01-05T09:00:00Z",
    }


def test_emergency_ticket_pages_on_call(run_db, caplog):
    ctx = load_context(run_db, "T-003", NOW)
    with caplog.at_level(logging.WARNING, logger="app.tools"):
        out = create_ticket(ctx, GAS_LEAK)

    assert out.ticket_id == "TK-0006"
    assert out.priority == "emergency" and out.paged_on_call is True
    assert "PAGED on-call manager for TK-0006" in caplog.text

    conn = db.connect(run_db)
    row = db.get_ticket(conn, "TK-0006")
    conn.close()
    assert row is not None
    assert row.status == "open" and row.paged_on_call is True
    assert row.created_at == NOW
    assert row.cited_clauses == ["EMG-1.1", "EMG-2.1"]


def test_urgent_ticket_does_not_page(run_db, caplog):
    ctx = load_context(run_db, "T-003", NOW)
    with caplog.at_level(logging.WARNING, logger="app.tools"):
        out = create_ticket(ctx, NO_HEATING)
    assert out.paged_on_call is False
    assert "PAGED" not in caplog.text


def test_ticketing_outage_is_an_error_message_and_writes_nothing(run_db):
    ctx = load_context(run_db, "T-003", NOW, fail_create_ticket=True)

    with pytest.raises(TicketingUnavailable):
        create_ticket(ctx, GAS_LEAK)

    result = tool(make_tools(ctx), "create_ticket").invoke(GAS_LEAK.model_dump())
    assert result == "ticketing system unavailable"
    assert ticket_count(run_db) == 5


def test_ticket_always_goes_to_the_contexts_flat(run_db):
    ctx = load_context(run_db, "T-003", NOW)
    create_tool = tool(make_tools(ctx), "create_ticket")

    # Even if a model tried to smuggle in someone else's flat, it is ignored.
    args = NO_HEATING.model_dump() | {"flat_id": "B-1", "tenant_id": "T-008"}
    out = json.loads(create_tool.invoke(args))

    conn = db.connect(run_db)
    row = db.get_ticket(conn, out["ticket_id"])
    conn.close()
    assert (row.flat_id, row.tenant_id) == ("A-3", "T-003")


def test_no_tool_lets_the_model_choose_tenant_flat_or_database(run_db):
    tools = make_tools(load_context(run_db, "T-003", NOW))
    assert [t.name for t in tools] == ["search_policies", "check_open_tickets", "create_ticket"]
    for t in tools:
        for field in t.tool_call_schema.model_json_schema()["properties"]:
            assert not any(word in field for word in ("tenant", "flat", "db", "path", "building")), (
                f"{t.name}.{field}"
            )


def test_filtered_search_for_birch_court_hides_other_buildings(openai_db, tmp_path):
    ctx = load_context(db.fresh_copy(openai_db, tmp_path), "T-010", NOW)  # flat B-3
    queries = [
        "boiler pressure is low",
        "radiator is cold at the top, how do I bleed it",
        "no heating in November, how urgent is that",
        "smoke alarm keeps beeping, who changes the battery",
        "where is the stopcock",
    ]
    excluded = ("HB-A", "HB-C", "POL1")

    unfiltered_ids = set()
    for query in queries:
        inp = SearchPoliciesInput(query=query)
        filtered = [hit.clause_id for hit in search_policies(ctx, inp, filtered=True)]
        assert filtered, query
        assert not [cid for cid in filtered if cid.startswith(excluded)], (query, filtered)
        unfiltered_ids |= {hit.clause_id for hit in search_policies(ctx, inp, filtered=False)}

    # Sanity check that the filter is doing work: unfiltered, these queries do
    # reach other buildings' handbooks and the superseded policy.
    assert any(cid.startswith(excluded) for cid in unfiltered_ids)


def test_parallel_ticket_creation_gets_distinct_ids(offline_db, tmp_path):
    """Two issues in one message make the agent call create_ticket twice at once."""
    from concurrent.futures import ThreadPoolExecutor

    path = db.fresh_copy(offline_db, tmp_path)
    ctx = load_context(path, "T-007", NOW)
    inputs = [
        CreateTicketInput(category="water", priority="routine", summary="shower sealant"),
        CreateTicketInput(category="security", priority="urgent", summary="front door lock"),
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(lambda inp: create_ticket(ctx, inp), inputs))
    assert sorted(o.ticket_id for o in outputs) == ["TK-0006", "TK-0007"]
    with closing(db.connect(path)) as conn:
        assert len(db.list_tickets_after(conn, 5)) == 2
