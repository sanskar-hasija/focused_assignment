"""The agent's tools.

Core functions are plain Python, take a ToolContext plus a validated input model,
and open their own connection. make_tools wraps them as LangChain tools with the
context bound in, so the model only ever chooses the fields of the input models:
never the tenant, the flat or the database.
"""

import json
import logging
from contextlib import closing

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel

from app import db
from app.models import (
    CheckOpenTicketsInput,
    ClauseHit,
    CreateTicketInput,
    CreateTicketOutput,
    OpenTicketView,
    SearchPoliciesInput,
    Ticket,
    ToolContext,
)
from app.retrieval import search_clauses

log = logging.getLogger(__name__)


class TicketingUnavailable(RuntimeError):
    pass


# Core functions


def search_policies(
    ctx: ToolContext, inp: SearchPoliciesInput, *, filtered: bool
) -> list[ClauseHit]:
    """With filtered, only current clauses for the tenant's building or all buildings."""
    with closing(db.connect(ctx.db_path)) as conn:
        if filtered:
            return search_clauses(
                conn, inp.query, k=inp.k, building_id=ctx.building.id, current_only=True
            )
        return search_clauses(conn, inp.query, k=inp.k)


def check_open_tickets(ctx: ToolContext, inp: CheckOpenTicketsInput) -> list[Ticket]:
    with closing(db.connect(ctx.db_path)) as conn:
        return db.list_open_tickets(conn, ctx.flat.id, inp.category)


def create_ticket(ctx: ToolContext, inp: CreateTicketInput) -> CreateTicketOutput:
    """Open a ticket for the tenant's flat. Emergencies page the on-call manager."""
    if ctx.fail_create_ticket:
        raise TicketingUnavailable("ticketing system unavailable")

    paged = inp.priority == "emergency"
    with closing(db.connect(ctx.db_path)) as conn, conn:
        # Take the write lock before choosing the id. The agent can call this tool
        # twice in parallel (two issues in one message); with a deferred transaction
        # both calls read the same highest id and the second insert fails.
        conn.execute("BEGIN IMMEDIATE")
        ticket = Ticket(
            id=db.next_ticket_id(conn),
            flat_id=ctx.flat.id,
            tenant_id=ctx.tenant.id,
            category=inp.category,
            priority=inp.priority,
            summary=inp.summary,
            status="open",
            paged_on_call=paged,
            cited_clauses=inp.cited_clauses,  # stored as given; evaluators judge them
            created_at=ctx.now,
        )
        db.insert_ticket(conn, ticket)

    if paged:
        log.warning("PAGED on-call manager for %s", ticket.id)
    return CreateTicketOutput(
        ticket_id=ticket.id, priority=ticket.priority, paged_on_call=paged
    )


# LangChain tools


def _view(ticket: Ticket) -> OpenTicketView:
    return OpenTicketView(
        ticket_id=ticket.id,
        category=ticket.category,
        priority=ticket.priority,
        summary=ticket.summary,
        created_at=ticket.created_at,
    )


def _json(result: BaseModel | list[BaseModel]) -> str:
    if isinstance(result, list):
        return json.dumps([item.model_dump(mode="json") for item in result])
    return result.model_dump_json()


def make_tools(ctx: ToolContext, *, filtered_search: bool = False) -> list[BaseTool]:
    """The three tools for one run, bound to ctx. Each returns a JSON string."""

    def run_search_policies(**kwargs) -> str:
        inp = SearchPoliciesInput.model_validate(kwargs)
        return _json(search_policies(ctx, inp, filtered=filtered_search))

    def run_check_open_tickets(**kwargs) -> str:
        inp = CheckOpenTicketsInput.model_validate(kwargs)
        return _json([_view(ticket) for ticket in check_open_tickets(ctx, inp)])

    def run_create_ticket(**kwargs) -> str:
        inp = CreateTicketInput.model_validate(kwargs)
        try:
            return _json(create_ticket(ctx, inp))
        except TicketingUnavailable as exc:
            raise ToolException(str(exc)) from exc

    return [
        StructuredTool.from_function(
            func=run_search_policies,
            name="search_policies",
            description=(
                "Search the agency's repair policies and building handbooks. "
                "Returns clauses with ids you can cite."
            ),
            args_schema=SearchPoliciesInput,
        ),
        StructuredTool.from_function(
            func=run_check_open_tickets,
            name="check_open_tickets",
            description=(
                "List open repair tickets for the tenant's flat. "
                "Use this before creating a ticket."
            ),
            args_schema=CheckOpenTicketsInput,
        ),
        StructuredTool.from_function(
            func=run_create_ticket,
            name="create_ticket",
            description=(
                "Create a repair ticket for the tenant's flat. "
                "Emergency priority pages the on-call manager."
            ),
            args_schema=CreateTicketInput,
            handle_tool_error=True,
        ),
    ]
