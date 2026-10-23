"""Deterministic checks, adapters and reports on hand-built runs. No LLM, no network."""

import json
import uuid
from datetime import UTC, datetime

import pytest
from langsmith.schemas import Example, Run

from app.models import Issue, RunRecord, Ticket, TriageResult
from app.seed import load_corpus
from evals import adapters, evaluators as ev
from evals.examples import EXAMPLES
from evals.push_dataset import payload
from evals.reports import ExperimentInfo, RepetitionResult, render_failures, render_summary

CLAUSES = {clause.id: clause for clause in load_corpus()}
BY_ID = {example.id: example for example in EXAMPLES}
NOW = datetime(2026, 1, 14, 19, 30, tzinfo=UTC)


def issue(spec: str) -> Issue:
    category, priority, ticket = spec.split("/")
    return Issue(category=category, priority=priority, ticket=ticket)


def ticket(id: str, category: str, priority: str, flat: str = "A-3", tenant: str = "T-003") -> Ticket:
    return Ticket(
        id=id, flat_id=flat, tenant_id=tenant, category=category, priority=priority,
        summary="test", status="open", paged_on_call=priority == "emergency",
        cited_clauses=[], created_at=NOW,
    )  # fmt: skip


def record(
    issues=(), reply="", cited=(), retrieved=(), tickets=(), tools=("search_policies",)
) -> RunRecord:
    return RunRecord(
        agent="triage",
        result=TriageResult(issues=[issue(s) for s in issues], cited_clauses=list(cited), reply=reply),
        tickets_created=list(tickets),
        tool_calls=list(tools),
        retrieved=list(retrieved),
    )


def check(fn, rec: RunRecord, example_id: str) -> float | None:
    return fn(rec, BY_ID[example_id], CLAUSES).score


# The cases the task lists


def test_d01_missing_issue_fails_the_count():
    assert check(ev.issue_count_match, record(), "D01") == 0
    assert check(ev.issue_count_match, record(["electrical/none/none"]), "D01") == 1


def test_d02_forbidden_clause_and_caught_emergency():
    paged = ticket("TK-0006", "gas", "emergency")
    rec = record(["gas/emergency/new"], reply="Call 0800 111 999.", cited=["EMG-2.1", "EMG-2.2"],
                 retrieved=["EMG-2.1", "EMG-2.2"], tickets=[paged])  # fmt: skip
    assert check(ev.forbidden_cited, rec, "D02") == 0
    assert check(ev.emergency_caught, rec, "D02") == 1
    assert check(ev.ticket_claims_true, rec, "D02") == 1


def test_d03_one_gold_clause_missing():
    rec = record(["water/urgent/new"], cited=["POL2-3.2"], retrieved=["POL2-3.2", "EMG-2.5"],
                 tickets=[ticket("TK-0006", "water", "urgent")])  # fmt: skip
    assert check(ev.gold_retrieved, rec, "D03") == 0.5
    assert check(ev.gold_cited, rec, "D03") == 0.5


def test_d04_existing_ticket_reference_must_be_real():
    rec = record(["water/routine/existing"], reply="This is already logged as TK-0001.")
    assert check(ev.ticket_claims_true, rec, "D04") == 1
    invented = record(["water/routine/existing"], reply="This is already logged as TK-0099.")
    result = ev.ticket_claims_true(invented, BY_ID["D04"], CLAUSES)
    assert result.score == 0 and "TK-0099" in result.comment


def test_outage_logged_claim_fails_with_a_curly_apostrophe():
    rec = record(["security/urgent/none"], reply="I’ve logged this for you.",
                 tools=["search_policies", "check_open_tickets", "create_ticket"])  # fmt: skip
    assert check(ev.ticket_claims_true, rec, "D32") == 0
    honest = record(["security/urgent/none"], reply="I couldn't log this: the system is down.")
    assert check(ev.ticket_claims_true, honest, "D32") == 1


def test_emergency_predicted_routine_costs_100():
    rec = record(["gas/routine/new"], tickets=[ticket("TK-0006", "gas", "routine")])
    assert check(ev.cost, rec, "D02") == 100


# More coverage


def test_emergency_not_paged_is_not_caught():
    rec = record(["gas/emergency/new"])  # said emergency, but no paged row was written
    result = ev.emergency_caught(rec, BY_ID["D02"], CLAUSES)
    assert result.score == 0 and "paged" in result.comment


def test_outage_emergency_needs_no_page():
    assert check(ev.emergency_caught, record(["gas/emergency/none"]), "D34") == 1


def test_false_emergency_counts_pages_too():
    assert check(ev.false_emergency, record(["electrical/none/none"]), "D01") == 1
    assert check(ev.false_emergency, record(["electrical/emergency/new"]), "D01") == 0
    page_only = record(["electrical/none/none"], tickets=[ticket("TK-0006", "electrical", "emergency")])
    assert check(ev.false_emergency, page_only, "D01") == 0
    assert check(ev.false_emergency, record(), "D02") is None


def test_unsafe_advice_depends_on_the_building():
    advice = record(["heating/none/none"], reply="Top up the pressure with the filling loop.")
    assert check(ev.no_unsafe_advice, advice, "D24") == 1  # Alder House: allowed
    assert check(ev.no_unsafe_advice, advice, "D14") == 0  # Birch Court: not allowed
    assert check(ev.no_unsafe_advice, record(reply="Relight the pilot light."), "D24") == 0


def test_unaccounted_and_unclaimed_tickets():
    extra = record(["water/routine/existing"], tickets=[ticket("TK-0006", "water", "routine")])
    assert check(ev.ticket_claims_true, extra, "D04") == 0
    missing = record(["water/urgent/new"])
    assert check(ev.ticket_claims_true, missing, "D03") == 0


def test_pairing_by_category_for_priority_ticket_and_cost():
    # D15 expects water/routine/new and security/urgent/new.
    rec = record(["security/routine/new", "heating/urgent/new"])
    assert check(ev.priority_match, rec, "D15") == 0  # water missing, security wrong
    assert check(ev.ticket_match, rec, "D15") == 0.5
    # water routine as none (3) + security urgent as routine (10) + extra heating urgent (2)
    assert check(ev.cost, rec, "D15") == 15


def test_empty_reference():
    assert check(ev.priority_match, record(), "D29") == 1
    assert check(ev.priority_match, record(["other/routine/new"]), "D29") == 0
    assert check(ev.cost, record(["other/routine/new"]), "D29") == 1


def test_citations_and_retrieval_scope():
    rec = record(cited=["HB-A-2.1"], retrieved=["HB-A-2.1", "HB-B-1.2", "POL1-3.1", "POL2-3.2"])
    assert check(ev.citations_retrieved, rec, "D24") == 1
    assert check(ev.retrieval_in_scope, rec, "D24") == 0.5  # HB-B and POL1 are out
    assert check(ev.citations_retrieved, record(cited=["EMG-2.1"]), "D24") == 0
    assert check(ev.citations_retrieved, record(), "D24") is None
    assert check(ev.retrieval_in_scope, record(), "D24") is None


def test_reply_checks_are_case_insensitive_and_normalised():
    rec = record(reply="Call 0800 111 999 from outside.")
    assert check(ev.reply_includes, rec, "D02") == 1
    assert check(ev.reply_excludes, record(reply="Please CALL 999"), "D02") == 0
    assert check(ev.reply_excludes, record(reply="Ring 0800 111 999."), "D02") == 1
    assert check(ev.reply_includes, rec, "D12") is None


def test_trajectory_checks():
    checked = record(tools=["search_policies", "check_open_tickets", "create_ticket"],
                     tickets=[ticket("TK-0006", "water", "urgent")])  # fmt: skip
    unchecked = record(tools=["search_policies", "create_ticket"],
                       tickets=[ticket("TK-0006", "water", "urgent")])  # fmt: skip
    emergency_only = record(tools=["search_policies", "create_ticket"],
                            tickets=[ticket("TK-0006", "gas", "emergency")])  # fmt: skip
    assert check(ev.checked_before_write, checked, "D03") == 1
    assert check(ev.checked_before_write, unchecked, "D03") == 0
    assert check(ev.checked_before_write, emergency_only, "D02") is None
    assert check(ev.searched, record(tools=[]), "D01") == 0
    assert check(ev.tool_calls, checked, "D03") == 3


def test_every_check_runs_on_a_run_with_no_result():
    errored = RunRecord(agent="triage", result=None, tickets_created=[], tool_calls=[],
                        retrieved=[], error="RuntimeError: boom")  # fmt: skip
    results = ev.run_checks(errored, BY_ID["D02"], CLAUSES)
    assert [r.key for r in results] == [c.__name__ for c in ev.CHECKS]
    assert next(r for r in results if r.key == "emergency_caught").score == 0


# Adapters


def _langsmith_pair(rec: RunRecord, example_id: str) -> tuple[Run, Example]:
    body = payload(BY_ID[example_id])
    example = Example(id=body["id"], dataset_id=uuid.uuid4(), inputs=body["inputs"],
                      outputs=body["outputs"], metadata=body["metadata"] | {"dataset_split": ["dev"]},
                      created_at=NOW)  # fmt: skip
    run = Run(id=uuid.uuid4(), name="triage", start_time=NOW, run_type="chain",
              inputs=body["inputs"], outputs=rec.model_dump(mode="json"), trace_id=uuid.uuid4())  # fmt: skip
    return run, example


def test_adapter_scores_and_skips():
    run, example = _langsmith_pair(record(cited=["EMG-2.2"]), "D02")
    forbidden = adapters.as_evaluator(ev.forbidden_cited, CLAUSES)
    assert forbidden.__name__ == "forbidden_cited"
    assert forbidden(run, example) == {"key": "forbidden_cited", "score": 0, "comment": "cited EMG-2.2"}
    assert adapters.as_evaluator(ev.false_emergency, CLAUSES)(run, example) == adapters.NO_FEEDBACK


def test_example_round_trips_through_langsmith():
    _, example = _langsmith_pair(record(), "D34")
    assert adapters.example_from_langsmith(example) == BY_ID["D34"]


def test_summary_evaluators():
    caught = record(["gas/emergency/new"], tickets=[ticket("TK-0006", "gas", "emergency")])
    missed = record(["gas/routine/new"], tickets=[ticket("TK-0006", "gas", "routine")])
    false_alarm = record(["electrical/emergency/new"], tickets=[ticket("TK-0006", "electrical", "emergency")])
    pairs = [_langsmith_pair(caught, "D02"), _langsmith_pair(missed, "D02"), _langsmith_pair(false_alarm, "D01")]
    runs, examples = [p[0] for p in pairs], [p[1] for p in pairs]
    summary = {fn.__name__: fn(runs, examples) for fn in adapters.summary_evaluators(CLAUSES)}
    assert summary["emergencies_caught"]["comment"] == "1 of 2"
    assert summary["false_emergencies"]["score"] == 1
    assert summary["mean_cost"]["score"] == pytest.approx((0 + 100 + 5) / 3)
    assert summary["hard_gate_failures"]["score"] >= 2


# Reports


def _rep(example_id: str, number: int, rec: RunRecord) -> RepetitionResult:
    return RepetitionResult(
        example_id=example_id, repetition=number, run_id=str(uuid.uuid4()),
        trace_url=f"https://example.test/{example_id}/{number}", record=rec,
        checks=ev.run_checks(rec, BY_ID[example_id], CLAUSES),
    )  # fmt: skip


INFO = ExperimentInfo(name="test-triage-dev", url="https://example.test/exp", agent="triage",
                      split="dev", repetitions=2, git_sha="no-git", prompt_sha="abc")  # fmt: skip


def test_reports_mark_flaky_examples_and_list_hard_gates_first():
    good = record(["electrical/none/none"], cited=["POL2-2.2"], retrieved=["POL2-2.2"])
    bad = record([], cited=["POL1-2.1"], retrieved=["POL1-2.1"])
    noise = record(cited=["FAQ-1.1"], retrieved=["FAQ-1.1"])
    results = [_rep("D01", 1, good), _rep("D01", 2, bad), _rep("D29", 1, noise), _rep("D29", 2, noise)]
    examples = {"D01": BY_ID["D01"], "D29": BY_ID["D29"]}

    failures = render_failures(INFO, examples, results)
    assert "## D01 FLAKY:" in failures
    assert "https://example.test/D01/2" in failures
    assert "## D29" not in failures  # D29's checks all passed

    summary = render_summary(INFO, examples, results)
    assert summary.index("## Hard gates") < summary.index("## Every check") < summary.index("## By slice")
    assert "| superseded_trap | 1 |" in summary
    assert summary.rstrip().endswith("https://example.test/exp")
    json.dumps([r.model_dump(mode="json") for r in results])  # results.json is serialisable
