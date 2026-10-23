"""Build the ToolContext for one agent run: who the tenant is and where they live."""

from contextlib import closing
from datetime import datetime
from pathlib import Path

from app import db
from app.models import ToolContext


class UnknownTenant(LookupError):
    pass


def load_context(
    db_path: str | Path,
    tenant_id: str,
    now: datetime,
    fail_create_ticket: bool = False,
) -> ToolContext:
    with closing(db.connect(db_path)) as conn:
        tenant = db.get_tenant(conn, tenant_id)
        if tenant is None:
            raise UnknownTenant(f"No tenant with id {tenant_id!r} in {db_path}")
        flat = db.get_flat(conn, tenant.flat_id)
        assert flat is not None  # guaranteed by the tenants.flat_id foreign key
        building = db.get_building(conn, flat.building_id)
        assert building is not None  # guaranteed by the flats.building_id foreign key

    return ToolContext(
        db_path=str(db_path),
        tenant=tenant,
        flat=flat,
        building=building,
        now=now,
        fail_create_ticket=fail_create_ticket,
    )
