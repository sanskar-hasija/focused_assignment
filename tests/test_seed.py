from pathlib import Path

import pytest

from app import db
from app.embeddings import clause_text
from app.models import Building, Clause, Flat, Tenant, Ticket
from app.retrieval import search_clauses
from app.seed import build, count_rows, load_corpus


def test_counts(conn):
    counts = count_rows(conn)
    assert counts.buildings == 3
    assert counts.flats == 20
    assert counts.tenants == 20
    assert counts.tickets == 5
    assert counts.open_tickets == 4
    assert counts.documents == 7
    assert counts.clauses > 0
    assert counts.clauses == counts.vectors


def test_every_row_loads_into_its_model(conn):
    def ids(table: str) -> list[str]:
        return [row["id"] for row in conn.execute(f"SELECT id FROM {table}")]

    readers = [
        ("buildings", db.get_building, Building),
        ("flats", db.get_flat, Flat),
        ("tenants", db.get_tenant, Tenant),
        ("tickets", db.get_ticket, Ticket),
        ("clauses", db.get_clause, Clause),
    ]
    for table, read, model in readers:
        for row_id in ids(table):
            assert isinstance(read(conn, row_id), model), f"{table} {row_id}"


def test_every_ticket_belongs_to_its_flats_tenant(conn):
    for (ticket_id,) in conn.execute("SELECT id FROM tickets"):
        ticket = db.get_ticket(conn, ticket_id)
        assert db.get_tenant(conn, ticket.tenant_id).flat_id == ticket.flat_id


def test_readers(conn):
    assert db.get_tenant(conn, "T-014").flat_id == "B-7"
    assert db.get_tenant(conn, "T-999") is None
    assert db.get_building(conn, "B").heating == "communal"

    [ticket] = db.list_open_tickets(conn, "A-3")
    assert ticket.id == "TK-0001"
    assert ticket.cited_clauses == [] and ticket.paged_on_call is False
    assert db.list_open_tickets(conn, "A-3", category="heating") == []
    assert db.list_open_tickets(conn, "A-6") == []  # TK-0005 is closed
    assert db.next_ticket_id(conn) == "TK-0006"


def test_corpus_has_the_required_clauses():
    clauses = load_corpus()
    ids = [clause.id for clause in clauses]
    assert len(ids) == len(set(ids))
    required = {
        "POL2-1.1", "POL2-2.1", "POL2-2.2", "POL2-2.3", "POL2-3.1", "POL2-3.2",
        "POL2-3.3", "POL2-4.1", "POL2-4.2",
        "POL1-1.1", "POL1-2.1", "POL1-3.1",
        "EMG-1.1", "EMG-2.1", "EMG-2.2", "EMG-2.3", "EMG-2.4", "EMG-2.5", "EMG-3.1",
        "HB-A-1.1", "HB-A-1.2", "HB-A-2.1", "HB-A-2.2", "HB-A-2.3",
        "HB-B-1.1", "HB-B-1.2", "HB-B-1.3", "HB-B-2.1", "HB-B-2.2",
        "HB-C-1.1", "HB-C-1.2", "HB-C-2.1",
        "FAQ-1.1", "FAQ-1.2", "FAQ-1.3", "FAQ-1.4",
    }  # fmt: skip
    assert required <= set(ids)
    assert {c.status for c in clauses if c.doc_id == "POL1"} == {"superseded"}
    assert {c.building_id for c in clauses if c.doc_id.startswith("HB-")} == {"A", "B", "C"}


def test_seed_is_deterministic(tmp_path, fake_embed):
    first, second = tmp_path / "first.db", tmp_path / "second.db"
    build(first, embed_fn=fake_embed)
    build(second, embed_fn=fake_embed)
    assert first.read_bytes() == second.read_bytes()


def test_writing_to_a_fresh_copy_leaves_the_template_unchanged(offline_db, tmp_path):
    before = offline_db.read_bytes()

    copy = db.fresh_copy(offline_db, tmp_path / "runs")
    assert Path(copy) != offline_db
    conn = db.connect(copy)
    with conn:
        ticket = db.get_ticket(conn, "TK-0001").model_copy(
            update={"id": db.next_ticket_id(conn)}
        )
        db.insert_ticket(conn, ticket)
    assert count_rows(conn).tickets == 6
    conn.close()

    assert offline_db.read_bytes() == before
    template = db.connect(offline_db)
    assert count_rows(template).tickets == 5
    template.close()


def test_search_plumbing_offline(conn, monkeypatch, fake_embed):
    """Exercise the vector SQL, join and filters with fake vectors: a query equal to
    a clause's embedded text has cosine distance 0 to that clause."""
    monkeypatch.setattr("app.retrieval.embed", fake_embed)
    hb_a = db.get_clause(conn, "HB-A-2.1")

    [hit] = search_clauses(conn, clause_text(hb_a), k=1)
    assert hit.clause_id == "HB-A-2.1"
    assert hit.distance == pytest.approx(0, abs=1e-6)

    hits = search_clauses(conn, clause_text(hb_a), k=5, building_id="B", current_only=True)
    assert len(hits) == 5
    assert all(h.building_id in (None, "B") and h.status == "current" for h in hits)
    assert [h.distance for h in hits] == sorted(h.distance for h in hits)


def test_eggy_smell_finds_the_gas_procedure(openai_db):
    conn = db.connect(openai_db)
    hits = search_clauses(conn, "weird eggy smell in the kitchen")
    conn.close()
    assert "EMG-2.1" in [hit.clause_id for hit in hits[:3]]
    assert [hit.distance for hit in hits] == sorted(hit.distance for hit in hits)


def test_building_filter_hides_other_buildings_and_superseded_policy(openai_db):
    conn = db.connect(openai_db)
    hits = search_clauses(conn, "boiler pressure is low", building_id="B", current_only=True)
    conn.close()
    assert len(hits) == 5
    for hit in hits:
        assert not hit.clause_id.startswith(("HB-A", "HB-C", "POL1")), hit.clause_id
