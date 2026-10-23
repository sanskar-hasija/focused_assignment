"""Eval dataset schema.

The validators enforce the parts of docs/labelling.md that code can check. Every
error names its rule id (R1 to R19), or "tenant", "clauses" or "slices" for the
data-integrity checks, and one example reports all of its problems at once.
"""

from collections.abc import Callable
from datetime import datetime
from functools import cache
from typing import Literal

from pydantic import BaseModel, model_validator

from app.models import Issue
from app.seed import load_corpus
from app.seed_data import FLATS, TENANTS, TICKETS

Slice = Literal[
    "emergency", "ticket", "reply_only", "self_help", "out_of_scope", "vague",
    "adversarial", "injection", "authority", "outage", "pii", "duplicate",
    "multi_issue", "season", "building_flip", "superseded_trap", "tenant_caused",
    "gas", "water", "electrical", "heating", "security", "other",
    "tricky", "manual_run",
]  # fmt: skip


class ExampleInputs(BaseModel):
    message: str
    tenant_id: str
    now: datetime
    fail_create_ticket: bool = False


class ExampleReference(BaseModel):
    issues: list[Issue]
    gold_clauses: list[str] = []
    forbidden_clauses: list[str] = []
    reply_must_include: list[str] = []
    reply_must_not_include: list[str] = []


class ExampleMetadata(BaseModel):
    slices: list[Slice]
    split: Literal["dev", "heldout"]
    origin: Literal["manual_run", "catalogue", "variant"]
    notes: str  # one line: why this label, with clause ids


class CheckResult(BaseModel):
    key: str
    score: float | None  # None = the check doesn't apply to this example
    comment: str = ""


Outcome = Literal["emergency", "ticket", "reply_only"]


def expected_outcome(reference: ExampleReference) -> Outcome:
    """The prompt's three outcomes. An urgent issue during an outage is still "ticket":
    the right outcome, even though no ticket could be created."""
    priorities = {issue.priority for issue in reference.issues}
    if "emergency" in priorities:
        return "emergency"
    if priorities & {"urgent", "routine"}:
        return "ticket"
    return "reply_only"


class EvalExample(BaseModel):
    id: str  # "D01", "H03"
    inputs: ExampleInputs
    reference: ExampleReference
    metadata: ExampleMetadata

    @model_validator(mode="after")
    def follows_labelling_rules(self) -> "EvalExample":
        problems = [problem for check in CHECKS for problem in check(self)]
        if problems:
            raise ValueError(f"{self.id}: " + "; ".join(problems))
        return self


# Seed data and corpus lookups

TENANT_FLAT = {tenant.id: tenant.flat_id for tenant in TENANTS}
assert set(TENANT_FLAT.values()) <= {flat.id for flat in FLATS}

OPEN_TICKET_CATEGORIES: dict[str, set[str]] = {}
for _ticket in TICKETS:
    if _ticket.status == "open":
        OPEN_TICKET_CATEGORIES.setdefault(_ticket.flat_id, set()).add(_ticket.category)


@cache
def corpus_clause_ids() -> frozenset[str]:
    return frozenset(clause.id for clause in load_corpus())


# Checks: each returns the problems it finds, as messages that start with a rule id.


def check_pairs(ex: EvalExample) -> list[str]:
    """R4, with R12's exception: during an outage a real priority has ticket none."""
    problems = []
    for i, issue in enumerate(ex.reference.issues):
        if issue.priority == "none" and issue.ticket != "none":
            problems.append(f"R4: issue {i} has priority none but ticket {issue.ticket!r}")
        if issue.ticket == "none" and issue.priority != "none" and not ex.inputs.fail_create_ticket:
            problems.append(
                f"R4: issue {i} has ticket none but priority {issue.priority!r}"
                " (only allowed with fail_create_ticket, R12)"
            )
    return problems


def check_emergency_tickets(ex: EvalExample) -> list[str]:
    """R10: an emergency gets a new ticket, unless ticketing is down (R12)."""
    if ex.inputs.fail_create_ticket:
        return []
    return [
        f"R10: issue {i} is an emergency but ticket is {issue.ticket!r}, not 'new'"
        for i, issue in enumerate(ex.reference.issues)
        if issue.priority == "emergency" and issue.ticket != "new"
    ]


def check_outage(ex: EvalExample) -> list[str]:
    """R12: with fail_create_ticket, no ticket can be new or existing."""
    if not ex.inputs.fail_create_ticket:
        return []
    return [
        f"R12: fail_create_ticket is set but issue {i} has ticket {issue.ticket!r}"
        for i, issue in enumerate(ex.reference.issues)
        if issue.ticket != "none"
    ]


def check_empty_issues(ex: EvalExample) -> list[str]:
    """R3: no issues only for out-of-scope, vague or adversarial messages."""
    allowed = {"out_of_scope", "vague", "adversarial"}
    if ex.reference.issues or allowed & set(ex.metadata.slices):
        return []
    return ["R3: issues is empty but slices has none of out_of_scope, vague, adversarial"]


def check_existing_tickets(ex: EvalExample) -> list[str]:
    """R11, the part code can check: an open seed ticket in the same category on the flat.
    Whether it is the same problem is checked in review."""
    flat_id = TENANT_FLAT.get(ex.inputs.tenant_id)
    if flat_id is None:
        return []  # reported by check_tenant
    open_categories = OPEN_TICKET_CATEGORIES.get(flat_id, set())
    return [
        f"R11: issue {i} is 'existing' but flat {flat_id} has no open {issue.category} ticket"
        for i, issue in enumerate(ex.reference.issues)
        if issue.ticket == "existing" and issue.category not in open_categories
    ]


def check_bare_999(ex: EvalExample) -> list[str]:
    """R17: a bare "999" would also match "0800 111 999"."""
    if any(entry.strip() == "999" for entry in ex.reference.reply_must_not_include):
        return ['R17: reply_must_not_include has a bare "999"; forbid "call 999" instead']
    return []


def check_tenant(ex: EvalExample) -> list[str]:
    if ex.inputs.tenant_id not in TENANT_FLAT:
        return [f"tenant: {ex.inputs.tenant_id!r} is not in the seed data"]
    return []


def check_clauses(ex: EvalExample) -> list[str]:
    """R13 and R14: clause ids exist, and none is both gold and forbidden."""
    ref = ex.reference
    unknown = [c for c in ref.gold_clauses + ref.forbidden_clauses if c not in corpus_clause_ids()]
    overlap = sorted(set(ref.gold_clauses) & set(ref.forbidden_clauses))
    problems = []
    if unknown:
        problems.append(f"clauses: not in the corpus: {', '.join(unknown)}")
    if overlap:
        problems.append(f"clauses: both gold and forbidden: {', '.join(overlap)}")
    return problems


def check_slices(ex: EvalExample) -> list[str]:
    slices = set(ex.metadata.slices)
    issues = ex.reference.issues
    problems = []

    def must_match(slice_name: str, condition: bool, meaning: str) -> None:
        if (slice_name in slices) != condition:
            problems.append(f"slices: {slice_name!r} must be present if and only if {meaning}")

    must_match("emergency", any(i.priority == "emergency" for i in issues), "an issue is an emergency")
    must_match("duplicate", any(i.ticket == "existing" for i in issues), "a ticket is 'existing'")
    must_match("outage", ex.inputs.fail_create_ticket, "fail_create_ticket is set")
    missing = sorted({i.category for i in issues} - slices)
    if missing:
        problems.append(f"slices: missing issue categories {', '.join(missing)}")
    outcomes = [s for s in ("emergency", "ticket", "reply_only") if s in slices]
    if len(outcomes) != 1:
        problems.append(
            "slices: needs exactly one outcome slice of emergency, ticket, reply_only;"
            f" has {', '.join(outcomes) or 'none'}"
        )
    return problems


CHECKS: list[Callable[[EvalExample], list[str]]] = [
    check_pairs,
    check_emergency_tickets,
    check_outage,
    check_empty_issues,
    check_existing_tickets,
    check_bare_999,
    check_tenant,
    check_clauses,
    check_slices,
]
