"""Pydantic models shared by every module. Rows, inputs and outputs all live here."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

Category = Literal["gas", "water", "electrical", "heating", "security", "other"]
TicketPriority = Literal["emergency", "urgent", "routine"]


class Building(BaseModel):
    id: str  # "A"
    name: str
    heating: Literal["individual_boiler", "communal"]


class Flat(BaseModel):
    id: str  # "A-3"
    building_id: str


class Tenant(BaseModel):
    id: str  # "T-014"
    name: str
    email: str
    phone: str
    flat_id: str


class Ticket(BaseModel):
    id: str  # "TK-0001"
    flat_id: str
    tenant_id: str
    category: Category
    priority: TicketPriority
    summary: str
    status: Literal["open", "closed"]
    paged_on_call: bool
    cited_clauses: list[str]
    created_at: datetime


class Clause(BaseModel):
    id: str  # "POL2-3.1"
    doc_id: str
    doc_title: str
    building_id: str | None  # None = all buildings
    status: Literal["current", "superseded"]
    heading: str
    text: str


class ClauseHit(BaseModel):
    clause_id: str
    doc_title: str
    building_id: str | None
    status: Literal["current", "superseded"]
    text: str
    distance: float


class Issue(BaseModel):
    category: Category
    priority: Literal["emergency", "urgent", "routine", "none"]
    ticket: Literal["new", "existing", "none"]


class TriageResult(BaseModel):
    issues: list[Issue]  # empty when out of scope or too vague
    cited_clauses: list[str]
    reply: str


# Tools


class ToolContext(BaseModel):
    """Who the agent is acting for. Bound into the tools, never shown to the model."""

    db_path: str
    tenant: Tenant
    flat: Flat
    building: Building
    now: datetime  # fixed per run for reproducible dates
    fail_create_ticket: bool = False  # simulates a ticketing outage


class SearchPoliciesInput(BaseModel):
    query: str = Field(description="What to look up, in plain words")
    k: int = 5


class CheckOpenTicketsInput(BaseModel):
    category: Category | None = None


class OpenTicketView(BaseModel):
    """What the model sees of an open ticket: no tenant, flat or internal fields."""

    ticket_id: str
    category: Category
    priority: TicketPriority
    summary: str
    created_at: datetime


class CreateTicketInput(BaseModel):
    category: Category
    priority: TicketPriority
    summary: str = Field(description="One line describing the problem")
    cited_clauses: list[str] = []


class CreateTicketOutput(BaseModel):
    ticket_id: str
    priority: TicketPriority
    paged_on_call: bool


# Agent runs


def _assume_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class TriageInput(BaseModel):
    message: str
    tenant_id: str
    now: Annotated[datetime, AfterValidator(_assume_utc)]  # naive times are taken as UTC
    fail_create_ticket: bool = False


class ToolStep(BaseModel):
    """One tool call as the model made it and the result it got back."""

    name: str
    args: dict
    output: str  # the tool's JSON string, or the error message
    error: bool = False


class RunRecord(BaseModel):
    agent: str  # registry name of the agent that ran
    result: TriageResult | None
    tickets_created: list[Ticket]  # rows this run added to its database
    tool_calls: list[str]  # tool names in call order
    retrieved: list[str]  # clause ids returned by search_policies
    tool_errors: int = 0  # tool results that came back as errors (bad args, outages)
    steps: list[ToolStep] = []  # the same calls with their inputs and outputs
    error: str | None = None
