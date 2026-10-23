"""The LLM judge: applicability, prompt contents, caching and the adapter. No LLM unless marked."""

import os
from datetime import UTC, datetime

import pytest
from langchain_core.runnables import RunnableLambda

from app.models import Issue, RunRecord, Ticket, TriageResult
from app.seed import load_corpus
from evals import adapters
from evals.examples import EXAMPLES
from evals.judge import JUDGE_KEYS, Judge, JudgeVerdict, build_prompt, not_applicable
from evals.push_dataset import payload

CLAUSES = {clause.id: clause for clause in load_corpus()}
BY_ID = {example.id: example for example in EXAMPLES}
NOW = datetime(2026, 1, 14, 19, 30, tzinfo=UTC)

llm = pytest.mark.skipif(
    not (os.getenv("OPENAI_API_KEY") and (os.getenv("JUDGE_MODEL") or os.getenv("AGENT_MODEL"))),
    reason="OPENAI_API_KEY and JUDGE_MODEL are needed",
)


def record(issues=(), reply="A reply.", cited=(), tickets=(), tools=("search_policies",)) -> RunRecord:
    return RunRecord(
        agent="triage",
        result=TriageResult(
            issues=[Issue(**dict(zip(("category", "priority", "ticket"), s.split("/")))) for s in issues],
            cited_clauses=list(cited),
            reply=reply,
        ),
        tickets_created=list(tickets),
        tool_calls=list(tools),
        retrieved=[],
    )


def paged_ticket() -> Ticket:
    return Ticket(
        id="TK-0006", flat_id="A-3", tenant_id="T-003", category="gas", priority="emergency",
        summary="gas smell", status="open", paged_on_call=True, cited_clauses=[], created_at=NOW,
    )  # fmt: skip


class FakeModel:
    """Counts calls and answers with a fixed verdict."""

    def __init__(self, passed: bool, reasoning: str = "because"):
        self.verdict = JudgeVerdict(reasoning=reasoning, passed=passed)
        self.calls = 0

    def as_runnable(self):
        def respond(messages):
            self.calls += 1
            return self.verdict

        return RunnableLambda(respond)


def test_safety_first_only_applies_to_emergencies():
    assert not_applicable("safety_first", record(), BY_ID["D01"]) == "not an emergency"
    assert not_applicable("safety_first", record(), BY_ID["D02"]) is None
    assert not_applicable("tone", record(), BY_ID["D01"]) is None
    assert not_applicable("grounded", record(reply="   "), BY_ID["D01"]) == "no reply"
    no_result = RunRecord(agent="triage", result=None, tickets_created=[], tool_calls=[], retrieved=[])
    assert all(not_applicable(k, no_result, BY_ID["D02"]) == "no reply" for k in JUDGE_KEYS)


def test_prompt_carries_message_reply_clause_text_and_run_facts():
    rec = record(["gas/emergency/new"], reply="Leave the flat now.", cited=["EMG-2.1", "NOPE-1"], tickets=[paged_ticket()])
    system, human = build_prompt("grounded", rec, BY_ID["D02"], CLAUSES)
    assert system[0] == "system" and "grounded" in system[1]
    text = human[1]
    assert "weird eggy smell in the kitchen" in text
    assert "Leave the flat now." in text
    assert CLAUSES["EMG-2.1"].text in text
    assert "NOPE-1: (no such clause)" in text
    assert "TK-0006 (gas, emergency, on-call manager paged)" in text
    assert "TK-0001 (water, routine): Kitchen tap dripping constantly" in text  # A-3's open ticket
    assert "search_policies" in text
    assert "A-3 in Alder House (each flat has its own boiler)" in text


def test_outage_is_stated_in_the_facts():
    _, human = build_prompt("grounded", record(["security/urgent/none"]), BY_ID["D32"], CLAUSES)
    assert "ticketing system was DOWN" in human[1]


def test_verdict_becomes_a_check_result_and_is_cached():
    fake = FakeModel(passed=False, reasoning="Safety steps come after the apology.")
    judge = Judge(model=fake.as_runnable())
    rec = record(["gas/emergency/new"], reply="Sorry about that. Leave the flat.", tickets=[paged_ticket()])

    first = judge.judge("safety_first", rec, BY_ID["D02"], CLAUSES)
    assert (first.key, first.score, first.comment) == ("safety_first", 0.0, "Safety steps come after the apology.")
    assert judge.judge("safety_first", rec, BY_ID["D02"], CLAUSES) == first
    assert fake.calls == 1  # cached

    judge.judge("safety_first", record(["gas/emergency/new"], reply="Different reply."), BY_ID["D02"], CLAUSES)
    assert fake.calls == 2  # a different record is a different call

    results = judge.run(rec, BY_ID["D02"], CLAUSES)
    assert [r.key for r in results] == JUDGE_KEYS
    assert fake.calls == 4  # safety_first cached, tone and grounded new


def test_not_applicable_makes_no_call():
    fake = FakeModel(passed=True)
    judge = Judge(model=fake.as_runnable())
    result = judge.judge("safety_first", record(), BY_ID["D01"], CLAUSES)
    assert result.score is None and fake.calls == 0


def test_judge_error_is_reported_not_raised():
    def boom(messages):
        raise RuntimeError("model down")

    judge = Judge(model=RunnableLambda(boom))
    result = judge.judge("tone", record(), BY_ID["D01"], CLAUSES)
    assert result.score is None
    assert result.comment.startswith("judge error: RuntimeError")


def test_checks_plug_into_the_langsmith_adapter():
    from langsmith.schemas import Example, Run
    import uuid

    judge = Judge(model=FakeModel(passed=True, reasoning="Kind and clear.").as_runnable())
    rec = record(["electrical/none/none"], reply="Pop a new bulb in; let us know if it keeps blowing.")
    example = BY_ID["D01"]
    body = payload(example)
    ls_example = Example(id=body["id"], dataset_id=uuid.uuid4(), inputs=body["inputs"], outputs=body["outputs"],
                         metadata=body["metadata"] | {"dataset_split": ["dev"]}, created_at=NOW)  # fmt: skip
    run = Run(id=uuid.uuid4(), name="triage", start_time=NOW, run_type="chain", inputs=body["inputs"],
              outputs=rec.model_dump(mode="json"), trace_id=uuid.uuid4())  # fmt: skip

    by_name = {check.__name__: adapters.as_evaluator(check, CLAUSES) for check in judge.checks}
    assert set(by_name) == set(JUDGE_KEYS)
    assert by_name["tone"](run, ls_example) == {"key": "tone", "score": 1.0, "comment": "Kind and clear."}
    assert by_name["safety_first"](run, ls_example) == adapters.NO_FEEDBACK


@pytest.mark.llm
@llm
def test_real_judge_fails_a_reply_that_buries_the_safety_steps():
    judge = Judge()
    rec = record(
        ["gas/emergency/new"],
        reply=(
            "Thanks for getting in touch, and sorry to hear about the smell. I've raised ticket "
            "TK-0006 for you and our on-call manager has been paged; they'll be in touch to "
            "arrange a visit. We take all reports seriously and aim to respond within 24 hours. "
            "In the meantime, be careful."
        ),
        cited=["EMG-2.1"],
        tickets=[paged_ticket()],
    )
    assert judge.judge("safety_first", rec, BY_ID["D02"], CLAUSES).score == 0
