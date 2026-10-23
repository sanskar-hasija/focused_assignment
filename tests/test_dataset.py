"""The dataset, its LangSmith payloads and the review sheet. No network, no LLM."""

import uuid
from collections import Counter

from evals.examples import EXAMPLES
from evals.push_dataset import payload, remote_id
from evals.review import render
from evals.schema import expected_outcome


def test_dataset_shape():
    assert len(EXAMPLES) == 44
    assert Counter(e.metadata.split for e in EXAMPLES) == {"dev": 34, "heldout": 10}
    assert sum(expected_outcome(e.reference) == "emergency" for e in EXAMPLES) == 12
    assert all(e.id[0] == {"dev": "D", "heldout": "H"}[e.metadata.split] for e in EXAMPLES)


def test_origins():
    origins = {e.id: e.metadata.origin for e in EXAMPLES}
    assert {i for i, o in origins.items() if o == "manual_run"} == {"D01", "D02", "D03", "D04"}
    assert all(o == "variant" for i, o in origins.items() if i.startswith("H"))


def test_every_time_is_utc():
    assert {e.inputs.now.utcoffset().total_seconds() for e in EXAMPLES} == {0}


def test_remote_ids_are_stable_and_unique():
    ids = [remote_id(e) for e in EXAMPLES]
    assert len(set(ids)) == len(ids)
    d01 = next(e for e in EXAMPLES if e.id == "D01")
    assert remote_id(d01) == uuid.uuid5(uuid.NAMESPACE_URL, "triage-eval/D01")
    assert remote_id(d01, "other") != remote_id(d01)  # ids are unique across datasets


def test_payload_round_trips_to_the_target_inputs():
    d32 = next(e for e in EXAMPLES if e.id == "D32")
    body = payload(d32)
    assert body["inputs"] == {
        "message": "The front door lock is broken and won't lock",
        "tenant_id": "T-015",
        "now": "2026-01-14T19:30:00Z",
        "fail_create_ticket": True,
    }
    assert body["outputs"]["issues"] == [
        {"category": "security", "priority": "urgent", "ticket": "none"}
    ]
    assert body["metadata"]["example_id"] == "D32"
    assert body["split"] == "dev"


def test_outcomes():
    by_id = {e.id: expected_outcome(e.reference) for e in EXAMPLES}
    assert by_id["D02"] == "emergency"
    assert by_id["D34"] == "emergency"  # still an emergency when ticketing is down
    assert by_id["D32"] == "ticket"  # a real repair, even though no ticket can be created
    assert by_id["D24"] == "reply_only"
    assert by_id["D29"] == "reply_only"


def test_review_sheet_has_one_row_per_example_dev_first():
    rows = [line for line in render(EXAMPLES).splitlines() if line.startswith("| **")]
    assert len(rows) == 44
    assert rows[0].startswith("| **D01**") and rows[-1].startswith("| **H10**")
