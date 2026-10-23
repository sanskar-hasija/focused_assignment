"""Build data/harbour.db from seed_data.py and corpus/*.md. Run with `make seed`."""

import re
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel

from app import db
from app.embeddings import clause_text, embed
from app.models import Clause
from app.seed_data import BUILDINGS, FLATS, TENANTS, TICKETS

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "corpus"
DB_PATH = ROOT / "data" / "harbour.db"

FRONT_MATTER = re.compile(r"\A---\n(?P<meta>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)
CLAUSE_HEADING = re.compile(r"^## (\S+) (.+)$", re.MULTILINE)

EmbedFn = Callable[[list[str]], list[list[float]]]


class DocumentMeta(BaseModel):
    doc_id: str
    title: str
    building_id: str | None
    status: Literal["current", "superseded"]


class SeedCounts(BaseModel):
    buildings: int
    flats: int
    tenants: int
    tickets: int
    open_tickets: int
    documents: int
    clauses: int
    vectors: int


def parse_document(path: Path) -> list[Clause]:
    """Split one corpus file into clauses: YAML-style front matter, then `## ID Heading` sections."""
    match = FRONT_MATTER.match(path.read_text())
    if match is None:
        raise ValueError(f"{path.name}: missing front matter")

    fields = {}
    for line in match["meta"].splitlines():
        key, _, value = line.partition(":")
        value = value.strip().strip("'\"")
        fields[key.strip()] = None if value == "null" else value
    meta = DocumentMeta.model_validate(fields)

    # re.split with two groups yields [preamble, id, heading, text, id, heading, text, ...]
    preamble, *parts = CLAUSE_HEADING.split(match["body"])
    if preamble.strip():
        raise ValueError(f"{path.name}: text before the first clause")

    clauses = []
    for clause_id, heading, text in zip(parts[0::3], parts[1::3], parts[2::3]):
        if not clause_id.startswith(f"{meta.doc_id}-"):
            raise ValueError(f"{path.name}: clause {clause_id} is not in {meta.doc_id}")
        clauses.append(
            Clause(
                id=clause_id,
                doc_id=meta.doc_id,
                doc_title=meta.title,
                building_id=meta.building_id,
                status=meta.status,
                heading=heading.strip(),
                text=" ".join(text.split()),
            )
        )
    return clauses


def load_corpus(corpus_dir: Path = CORPUS_DIR) -> list[Clause]:
    """Every clause in the corpus, in file-name then document order."""
    return [
        clause
        for path in sorted(corpus_dir.glob("*.md"))
        for clause in parse_document(path)
    ]


def build(db_path: str | Path, embed_fn: EmbedFn = embed) -> None:
    """Delete db_path if it exists and rebuild it from scratch."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)

    clauses = load_corpus()
    embeddings = embed_fn([clause_text(clause) for clause in clauses])

    conn = db.connect(db_path)
    try:
        with conn:
            db.create_schema(conn)
            for building in BUILDINGS:
                db.insert_building(conn, building)
            for flat in FLATS:
                db.insert_flat(conn, flat)
            for tenant in TENANTS:
                db.insert_tenant(conn, tenant)
            for ticket in TICKETS:
                db.insert_ticket(conn, ticket)
            for clause, embedding in zip(clauses, embeddings, strict=True):
                rowid = db.insert_clause(conn, clause)
                db.insert_clause_vector(conn, rowid, embedding)
    finally:
        conn.close()


def count_rows(conn: sqlite3.Connection) -> SeedCounts:
    def scalar(sql: str) -> int:
        return conn.execute(sql).fetchone()[0]

    return SeedCounts(
        buildings=scalar("SELECT COUNT(*) FROM buildings"),
        flats=scalar("SELECT COUNT(*) FROM flats"),
        tenants=scalar("SELECT COUNT(*) FROM tenants"),
        tickets=scalar("SELECT COUNT(*) FROM tickets"),
        open_tickets=scalar("SELECT COUNT(*) FROM tickets WHERE status = 'open'"),
        documents=scalar("SELECT COUNT(DISTINCT doc_id) FROM clauses"),
        clauses=scalar("SELECT COUNT(*) FROM clauses"),
        vectors=scalar("SELECT COUNT(*) FROM vec_clauses"),
    )


def main() -> None:
    load_dotenv()
    build(DB_PATH)
    conn = db.connect(DB_PATH)
    try:
        counts = count_rows(conn)
    finally:
        conn.close()
    print(f"Built {DB_PATH.relative_to(ROOT)}")
    for name, value in counts.model_dump().items():
        print(f"  {name:<13}{value}")


if __name__ == "__main__":
    main()
