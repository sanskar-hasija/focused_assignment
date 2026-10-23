"""Fixed seed rows for buildings, flats, tenants and tickets. No randomness."""

from datetime import UTC, datetime
from typing import Literal

from app.models import Building, Category, Flat, Tenant, Ticket, TicketPriority

BUILDINGS = [
    Building(id="A", name="Alder House", heating="individual_boiler"),
    Building(id="B", name="Birch Court", heating="communal"),
    Building(id="C", name="Cedar Mews", heating="individual_boiler"),
]

FLATS_PER_BUILDING = {"A": 7, "B": 7, "C": 6}

FLATS = [
    Flat(id=f"{building_id}-{n}", building_id=building_id)
    for building_id, count in FLATS_PER_BUILDING.items()
    for n in range(1, count + 1)
]

# One tenant per flat, in flat order: T-001 is in A-1, T-020 is in C-6.
TENANT_NAMES = [
    "Maya Okafor",
    "Tom Hargreaves",
    "Priya Raman",
    "Owen Llewellyn",
    "Grace Achterberg",
    "Samir Haddad",
    "Ellie Brennan",
    "Jonah Whitlock",
    "Aisha Bello",
    "Callum Fraser",
    "Nina Kowalczyk",
    "Reuben Ashdown",
    "Hannah Lindqvist",
    "Kofi Mensah",
    "Isla McAllister",
    "Daniel Ferreira",
    "Leah Thornbury",
    "Marcus Osei",
    "Rosa Delgado",
    "Felix Ngata",
]

TENANTS = [
    Tenant(
        id=f"T-{i:03d}",
        name=name,
        email=f"{name.lower().replace(' ', '.')}@example.com",
        phone=f"07700 900{100 + i:03d}",  # Ofcom drama range, never a real number
        flat_id=flat.id,
    )
    for i, (name, flat) in enumerate(zip(TENANT_NAMES, FLATS, strict=True), start=1)
]

_TENANT_BY_FLAT = {tenant.flat_id: tenant.id for tenant in TENANTS}


def _ticket(
    id: str,
    flat_id: str,
    category: Category,
    priority: TicketPriority,
    summary: str,
    status: Literal["open", "closed"],
    created: str,
) -> Ticket:
    return Ticket(
        id=id,
        flat_id=flat_id,
        tenant_id=_TENANT_BY_FLAT[flat_id],
        category=category,
        priority=priority,
        summary=summary,
        status=status,
        paged_on_call=False,
        cited_clauses=[],
        created_at=datetime.fromisoformat(f"{created}T09:00:00").replace(tzinfo=UTC),
    )


TICKETS = [
    _ticket("TK-0001", "A-3", "water", "routine", "Kitchen tap dripping constantly", "open", "2026-01-05"),
    _ticket("TK-0002", "B-2", "security", "urgent", "Front door lock stiff, hard to lock", "open", "2026-01-08"),
    _ticket("TK-0003", "B-5", "heating", "urgent", "Bedroom radiators cold", "open", "2026-01-09"),
    _ticket("TK-0004", "C-4", "other", "routine", "Bathroom extractor fan noisy", "open", "2026-01-10"),
    _ticket("TK-0005", "A-6", "water", "routine", "Shower sealant replaced", "closed", "2025-12-01"),
]  # fmt: skip
