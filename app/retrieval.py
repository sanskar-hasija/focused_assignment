"""Semantic search over policy clauses."""

import sqlite3

import sqlite_vec

from app.embeddings import embed
from app.models import ClauseHit

# How many nearest clauses to fetch before filtering in Python, so that
# filtering out other buildings' handbooks still leaves k hits to return.
FILTERED_FETCH_K = 20

# vec0 defaults to L2 distance, so we rank by cosine distance explicitly.
# The corpus is a few dozen clauses, so a full scan is instant.
NEAREST_CLAUSES = """
SELECT c.id, c.doc_title, c.building_id, c.status, c.text, v.distance
FROM (
    SELECT rowid, vec_distance_cosine(embedding, :query) AS distance
    FROM vec_clauses
    ORDER BY distance
    LIMIT :limit
) AS v
JOIN clauses AS c ON c.rowid = v.rowid
ORDER BY v.distance
"""


def search_clauses(
    conn: sqlite3.Connection,
    query: str,
    k: int = 5,
    building_id: str | None = None,
    current_only: bool = False,
) -> list[ClauseHit]:
    """The k clauses nearest to query, nearest first.

    distance is cosine distance (1 - cosine similarity), so lower is closer.
    With building_id, clauses for other buildings are dropped (clauses for all
    buildings are kept). With current_only, superseded clauses are dropped.
    """
    filtered = building_id is not None or current_only
    limit = max(k, FILTERED_FETCH_K) if filtered else k

    [vector] = embed([query])
    rows = conn.execute(
        NEAREST_CLAUSES,
        {"query": sqlite_vec.serialize_float32(vector), "limit": limit},
    ).fetchall()

    hits = [
        ClauseHit(
            clause_id=row["id"],
            doc_title=row["doc_title"],
            building_id=row["building_id"],
            status=row["status"],
            text=row["text"],
            distance=row["distance"],
        )
        for row in rows
    ]
    if building_id is not None:
        hits = [hit for hit in hits if hit.building_id in (None, building_id)]
    if current_only:
        hits = [hit for hit in hits if hit.status == "current"]
    return hits[:k]
