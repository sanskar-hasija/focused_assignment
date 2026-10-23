"""One passing and one failing example per labelling validator. No LLM calls."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.schema import EvalExample

ROOT = Path(__file__).resolve().parent.parent


def example(
    issues=(("water", "routine", "new"),),
    slices=("ticket", "water"),
    tenant="T-001",
    fail=False,
    gold=("POL2-3.3",),
    forbidden=(),
    must_not=(),
) -> dict:
    """A valid example by default: a dripping tap in A-1, a new routine ticket."""
    return {
        "id": "D01",
        "inputs": {
            "message": "The kitchen tap is dripping",
            "tenant_id": tenant,
            "now": "2026-01-14T19:30:00",
            "fail_create_ticket": fail,
        },
        "reference": {
            "issues": [
                {"category": c, "priority": p, "ticket": t} for c, p, t in issues
            ],
            "gold_clauses": list(gold),
            "forbidden_clauses": list(forbidden),
            "reply_must_not_include": list(must_not),
        },
        "metadata": {
            "slices": list(slices),
            "split": "dev",
            "origin": "catalogue",
            "notes": "A drip is routine, POL2-3.3.",
        },
    }


GAS = {"issues": (("gas", "emergency", "new"),), "slices": ("emergency", "gas"), "gold": ("EMG-2.1",)}

# (rule tag, a valid example, an invalid one)
CASES = [
    ("R4", example(issues=(("electrical", "none", "none"),), slices=("reply_only", "self_help", "electrical")),
           example(issues=(("electrical", "none", "new"),), slices=("reply_only", "self_help", "electrical"))),
    ("R4", example(issues=(("water", "urgent", "none"),), slices=("ticket", "water", "outage"), fail=True),
           example(issues=(("water", "urgent", "none"),), slices=("ticket", "water"))),
    ("R10", example(**GAS),
            example(**GAS | {"issues": (("gas", "emergency", "none"),)})),
    ("R10", example(**GAS | {"issues": (("gas", "emergency", "none"),), "slices": ("emergency", "gas", "outage"), "fail": True}),
            example(**GAS | {"issues": (("gas", "emergency", "existing"),), "slices": ("emergency", "gas", "duplicate")})),
    ("R12", example(issues=(("water", "urgent", "none"),), slices=("ticket", "water", "outage"), fail=True),
            example(issues=(("water", "urgent", "new"),), slices=("ticket", "water", "outage"), fail=True)),
    ("R3", example(issues=(), slices=("reply_only", "out_of_scope"), gold=("FAQ-1.1",)),
           example(issues=(), slices=("reply_only",), gold=("FAQ-1.1",))),
    ("R11", example(issues=(("water", "routine", "existing"),), slices=("ticket", "duplicate", "water"), tenant="T-003"),
            example(issues=(("water", "routine", "existing"),), slices=("ticket", "duplicate", "water"), tenant="T-001")),
    ("R17", example(**GAS, must_not=("call 999",)),
            example(**GAS, must_not=("999",))),
    ("tenant", example(tenant="T-020"),
               example(tenant="T-999")),
    ("clauses", example(gold=("POL2-3.3",), forbidden=("POL1-3.1",)),
                example(gold=("POL3-1.1",))),
    ("clauses", example(**GAS | {"forbidden": ("EMG-2.2",)}),
                example(**GAS | {"forbidden": ("EMG-2.1",)})),
    ("slices", example(**GAS),
               example(**GAS | {"slices": ("ticket", "gas")})),
    ("slices", example(),
               example(slices=("ticket", "water", "emergency"))),
    ("slices", example(issues=(("water", "routine", "existing"),), slices=("ticket", "duplicate", "water"), tenant="T-003"),
               example(issues=(("water", "routine", "existing"),), slices=("ticket", "water"), tenant="T-003")),
    ("slices", example(),
               example(slices=("ticket", "water", "duplicate"))),
    ("slices", example(issues=(("water", "urgent", "none"),), slices=("ticket", "water", "outage"), fail=True),
               example(issues=(("water", "urgent", "none"),), slices=("ticket", "water"), fail=True)),
    ("slices", example(),
               example(slices=("ticket", "water", "outage"))),
    ("slices", example(),
               example(slices=("ticket",))),
    ("slices", example(),
               example(slices=("water",))),
    ("slices", example(),
               example(slices=("ticket", "reply_only", "water"))),
]  # fmt: skip

CASE_IDS = [f"{rule}-{i}" for i, (rule, _, _) in enumerate(CASES)]


@pytest.mark.parametrize("rule, valid, invalid", CASES, ids=CASE_IDS)
def test_valid_example_passes(rule, valid, invalid):
    EvalExample.model_validate(valid)


@pytest.mark.parametrize("rule, valid, invalid", CASES, ids=CASE_IDS)
def test_invalid_example_fails_naming_its_rule(rule, valid, invalid):
    with pytest.raises(ValidationError, match=rf"\b{rule}:"):
        EvalExample.model_validate(invalid)


def test_all_problems_are_reported_together():
    bad = example(issues=(("gas", "emergency", "none"),), slices=("ticket",), tenant="T-999")
    with pytest.raises(ValidationError) as error:
        EvalExample.model_validate(bad)
    for tag in ("R4:", "R10:", "tenant:", "slices:"):
        assert tag in str(error.value)


def test_guide_documents_every_rule():
    guide = (ROOT / "docs" / "labelling.md").read_text()
    assert set(re.findall(r"\*\*(R\d+)\*\*", guide)) == {f"R{n}" for n in range(1, 20)}
