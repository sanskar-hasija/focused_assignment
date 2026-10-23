"""SQLite access: connection, schema, and typed readers and writers.

Every function takes or returns Pydantic models, never raw rows.
"""

import json
import shutil
import sqlite3
import uuid
from pathlib import Path

import sqlite_vec

from app.embeddings import EMBEDDING_DIM
from app.models import Building, Clause, Flat, Tenant, Ticket

SCHEMA = f"""
CREATE TABLE buildings (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    heating TEXT NOT NULL
);

CREATE TABLE flats (
    id          TEXT PRIMARY KEY,
    building_id TEXT NOT NULL REFERENCES buildings(id)
);

CREATE TABLE tenants (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    email   TEXT NOT NULL,
    phone   TEXT NOT NULL,
    flat_id TEXT NOT NULL REFERENCES flats(id)
);

CREATE TABLE tickets (
    id            TEXT PRIMARY KEY,
    flat_id       TEXT NOT NULL REFERENCES flats(id),
    tenant_id     TEXT NOT NULL REFERENCES tenants(id),
    category      TEXT NOT NULL,
    priority      TEXT NOT NULL,
    summary       TEXT NOT NULL,
    status        TEXT NOT NULL,
    paged_on_call INTEGER NOT NULL,  -- 0 or 1
    cited_clauses TEXT NOT NULL,     -- JSON array of clause ids
    created_at    TEXT NOT NULL      -- ISO 8601
);

CREATE INDEX tickets_by_flat ON tickets(flat_id, status);

CREATE TABLE clauses (
    rowid      INTEGER PRIMARY KEY,  -- equals vec_clauses.rowid
    id         TEXT NOT NULL UNIQUE,
    doc_id     TEXT NOT NULL,
    doc_title  TEXT NOT NULL,
    building_id TEXT REFERENCES buildings(id),  -- NULL = all buildings
    status     TEXT NOT NULL,
    heading    TEXT NOT NULL,
    text       TEXT NOT NULL
);

CREATE VIRTUAL TABLE vec_clauses USING vec0(embedding float[{EMBEDDING_DIM}]);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a database with sqlite-vec loaded and rows addressable by column name."""
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def fresh_copy(template_path: str | Path, dest_dir: str | Path) -> str:
    """Copy the seeded database to a new, uniquely named file and return its path."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"harbour-{uuid.uuid4().hex[:12]}.db"
    shutil.copyfile(template_path, path)
    return str(path)


# Writers


def insert_building(conn: sqlite3.Connection, building: Building) -> None:
    conn.execute(
        "INSERT INTO buildings (id, name, heating) VALUES (:id, :name, :heating)",
        building.model_dump(),
    )


def insert_flat(conn: sqlite3.Connection, flat: Flat) -> None:
    conn.execute(
        "INSERT INTO flats (id, building_id) VALUES (:id, :building_id)",
        flat.model_dump(),
    )


def insert_tenant(conn: sqlite3.Connection, tenant: Tenant) -> None:
    conn.execute(
        "INSERT INTO tenants (id, name, email, phone, flat_id)"
        " VALUES (:id, :name, :email, :phone, :flat_id)",
        tenant.model_dump(),
    )


def insert_ticket(conn: sqlite3.Connection, ticket: Ticket) -> None:
    row = ticket.model_dump()
    row["paged_on_call"] = int(ticket.paged_on_call)
    row["cited_clauses"] = json.dumps(ticket.cited_clauses)
    row["created_at"] = ticket.created_at.isoformat()
    conn.execute(
        "INSERT INTO tickets (id, flat_id, tenant_id, category, priority, summary,"
        " status, paged_on_call, cited_clauses, created_at)"
        " VALUES (:id, :flat_id, :tenant_id, :category, :priority, :summary,"
        " :status, :paged_on_call, :cited_clauses, :created_at)",
        row,
    )


def insert_clause(conn: sqlite3.Connection, clause: Clause) -> int:
    """Insert a clause and return its integer rowid, the key for its vector."""
    cursor = conn.execute(
        "INSERT INTO clauses (id, doc_id, doc_title, building_id, status, heading, text)"
        " VALUES (:id, :doc_id, :doc_title, :building_id, :status, :heading, :text)",
        clause.model_dump(),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def insert_clause_vector(
    conn: sqlite3.Connection, rowid: int, embedding: list[float]
) -> None:
    conn.execute(
        "INSERT INTO vec_clauses (rowid, embedding) VALUES (?, ?)",
        (rowid, sqlite_vec.serialize_float32(embedding)),
    )


# Readers


def _ticket(row: sqlite3.Row) -> Ticket:
    data = dict(row)
    data["paged_on_call"] = bool(data["paged_on_call"])
    data["cited_clauses"] = json.loads(data["cited_clauses"])
    return Ticket.model_validate(data)


def get_building(conn: sqlite3.Connection, building_id: str) -> Building | None:
    row = conn.execute("SELECT * FROM buildings WHERE id = ?", (building_id,)).fetchone()
    return Building.model_validate(dict(row)) if row else None


def get_flat(conn: sqlite3.Connection, flat_id: str) -> Flat | None:
    row = conn.execute("SELECT * FROM flats WHERE id = ?", (flat_id,)).fetchone()
    return Flat.model_validate(dict(row)) if row else None


def get_tenant(conn: sqlite3.Connection, tenant_id: str) -> Tenant | None:
    row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    return Tenant.model_validate(dict(row)) if row else None


def get_ticket(conn: sqlite3.Connection, ticket_id: str) -> Ticket | None:
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return _ticket(row) if row else None


def get_clause(conn: sqlite3.Connection, clause_id: str) -> Clause | None:
    row = conn.execute(
        "SELECT id, doc_id, doc_title, building_id, status, heading, text"
        " FROM clauses WHERE id = ?",
        (clause_id,),
    ).fetchone()
    return Clause.model_validate(dict(row)) if row else None


def list_clauses(conn: sqlite3.Connection) -> list[Clause]:
    rows = conn.execute(
        "SELECT id, doc_id, doc_title, building_id, status, heading, text"
        " FROM clauses ORDER BY rowid"
    ).fetchall()
    return [Clause.model_validate(dict(row)) for row in rows]


def list_open_tickets(
    conn: sqlite3.Connection, flat_id: str, category: str | None = None
) -> list[Ticket]:
    """Open tickets for a flat, oldest first, optionally narrowed to one category."""
    sql = "SELECT * FROM tickets WHERE flat_id = ? AND status = 'open'"
    params: list[str] = [flat_id]
    if category is not None:
        sql += " AND category = ?"
        params.append(category)
    rows = conn.execute(sql + " ORDER BY created_at, id", params).fetchall()
    return [_ticket(row) for row in rows]


def highest_ticket_number(conn: sqlite3.Connection) -> int:
    """The NNNN of the highest TK-NNNN in use, or 0 when there are no tickets."""
    (highest,) = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 4) AS INTEGER)) FROM tickets"
    ).fetchone()
    return highest or 0


def next_ticket_id(conn: sqlite3.Connection) -> str:
    """The id the next ticket should get: one past the highest TK-NNNN in use."""
    return f"TK-{highest_ticket_number(conn) + 1:04d}"


def list_tickets_after(conn: sqlite3.Connection, number: int) -> list[Ticket]:
    """Tickets numbered above TK-<number>, in id order: the ones added since then."""
    rows = conn.execute(
        "SELECT * FROM tickets WHERE CAST(SUBSTR(id, 4) AS INTEGER) > ? ORDER BY id",
        (number,),
    ).fetchall()
    return [_ticket(row) for row in rows]
