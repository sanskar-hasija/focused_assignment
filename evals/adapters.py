"""LangSmith adapters for the checks in evals/evaluators.py.

Each adapter rebuilds the RunRecord from the run's outputs and the EvalExample from the
dataset example, then runs one check. Summary evaluators aggregate across every run
in the experiment, repetitions included.
"""

from collections.abc import Callable
from statistics import mean

from langsmith.schemas import Example, Run

from app.models import Clause, RunRecord
from evals.evaluators import GATE_KEYS, Check, cost, emergency_caught, false_emergency, run_checks
from evals.schema import EvalExample

# Checked against langsmith 0.14.11: an evaluator that returns None raises ("Expected a
# non-empty dict ... Got None"), and {"key": k, "score": None} posts a feedback row with an
# empty score, which then counts in LangSmith's averages. {"results": []} posts nothing,
# so that is how a check that doesn't apply says so.
NO_FEEDBACK: dict = {"results": []}


def record_from_run(run: Run) -> RunRecord:
    return RunRecord.model_validate(run.outputs)


def example_from_langsmith(example: Example) -> EvalExample:
    metadata = example.metadata or {}
    return EvalExample.model_validate(
        {
            "id": metadata["example_id"],
            "inputs": example.inputs,
            "reference": example.outputs,
            "metadata": metadata,  # dataset_split and example_id are ignored
        }
    )


def as_evaluator(check: Check, clauses: dict[str, Clause]) -> Callable[[Run, Example], dict]:
    def evaluator(run: Run, example: Example) -> dict:
        result = check(record_from_run(run), example_from_langsmith(example), clauses)
        if result.score is None:
            return NO_FEEDBACK
        return {"key": result.key, "score": result.score, "comment": result.comment}

    evaluator.__name__ = check.__name__
    return evaluator


def evaluators(checks: list[Check], clauses: dict[str, Clause]) -> list[Callable[[Run, Example], dict]]:
    return [as_evaluator(check, clauses) for check in checks]


def summary_evaluators(clauses: dict[str, Clause]) -> list[Callable[[list[Run], list[Example]], dict]]:
    def pairs(runs: list[Run], examples: list[Example]):
        return [(record_from_run(r), example_from_langsmith(e)) for r, e in zip(runs, examples, strict=True)]

    def emergencies_caught(runs: list[Run], examples: list[Example]) -> dict:
        scores = [emergency_caught(r, e, clauses).score for r, e in pairs(runs, examples)]
        applicable = [s for s in scores if s is not None]
        caught = int(sum(applicable))
        return {"key": "emergencies_caught", "score": caught, "comment": f"{caught} of {len(applicable)}"}

    def false_emergencies(runs: list[Run], examples: list[Example]) -> dict:
        scores = [false_emergency(r, e, clauses).score for r, e in pairs(runs, examples)]
        count = sum(s == 0 for s in scores)
        return {"key": "false_emergencies", "score": count, "comment": f"{count} runs"}

    def mean_cost(runs: list[Run], examples: list[Example]) -> dict:
        costs = [cost(r, e, clauses).score for r, e in pairs(runs, examples)]
        return {"key": "mean_cost", "score": mean(costs) if costs else 0, "comment": "lower is better"}

    def hard_gate_failures(runs: list[Run], examples: list[Example]) -> dict:
        failures = {key: 0 for key in GATE_KEYS}
        for record, example in pairs(runs, examples):
            for result in run_checks(record, example, clauses):
                if result.key in failures and result.score == 0:
                    failures[result.key] += 1
        total = sum(failures.values())
        detail = ", ".join(f"{key} {n}" for key, n in failures.items())
        return {"key": "hard_gate_failures", "score": total, "comment": detail}

    return [emergencies_caught, false_emergencies, mean_cost, hard_gate_failures]
