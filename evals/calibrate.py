"""Calibrate the LLM judge against hand labels.

make calibrate [EXPERIMENT=baseline-triage-dev-8135d196]

evals/calibration/labels.json holds human verdicts for a handful of runs from one
experiment (a run is an example id plus a repetition). This script re-judges those runs
with the current rubrics, prints agreement per criterion, and writes
evals/calibration/report-<rubric>.md with every disagreement and the judge's reasoning,
so a rubric change can be compared with the one before it. The rubric id is a short hash
of evals/judge.py's rubric text.
"""

import argparse
import hashlib
import json
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

from app.models import RunRecord
from evals.evaluators import load_clauses
from evals.examples import EXAMPLES
from evals.judge import JUDGE_KEYS, RUBRICS, Judge
from evals.schema import CheckResult, EvalExample

CALIBRATION_DIR = Path(__file__).resolve().parent / "calibration"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
BY_ID = {example.id: example for example in EXAMPLES}


class LabelledRun(BaseModel):
    example_id: str
    repetition: int
    safety_first: bool | None  # None: the criterion doesn't apply
    tone: bool | None
    grounded: bool | None
    note: str

    def label(self, criterion: str) -> bool | None:
        return getattr(self, criterion)


class Labels(BaseModel):
    experiment: str
    labelled_by: str
    standard: str
    runs: list[LabelledRun]


class Comparison(BaseModel):
    example_id: str
    repetition: int
    criterion: str
    human: bool
    judge: CheckResult


def rubric_id() -> str:
    return hashlib.sha256("\n".join(RUBRICS[k] for k in JUDGE_KEYS).encode()).hexdigest()[:8]


def load_labels(path: Path = CALIBRATION_DIR / "labels.json") -> Labels:
    return Labels.model_validate_json(path.read_text())


def load_records(experiment: str) -> dict[tuple[str, int], RunRecord]:
    results = json.loads((RESULTS_DIR / experiment / "results.json").read_text())["results"]
    return {(r["example_id"], r["repetition"]): RunRecord.model_validate(r["record"]) for r in results}


def compare(judge: Judge, labels: Labels, records: dict[tuple[str, int], RunRecord]) -> list[Comparison]:
    clauses = load_clauses()
    out = []
    for run in labels.runs:
        record = records[(run.example_id, run.repetition)]
        example: EvalExample = BY_ID[run.example_id]
        for criterion in JUDGE_KEYS:
            human = run.label(criterion)
            if human is None:
                continue
            out.append(
                Comparison(
                    example_id=run.example_id, repetition=run.repetition, criterion=criterion,
                    human=human, judge=judge.judge(criterion, record, example, clauses),
                )  # fmt: skip
            )
    return out


def agreement(comparisons: list[Comparison]) -> dict[str, dict[str, int]]:
    """Per criterion: agree, judge_stricter (judge fail, human pass), judge_looser, errors."""
    table = {k: {"n": 0, "agree": 0, "judge_stricter": 0, "judge_looser": 0, "errors": 0} for k in JUDGE_KEYS}
    for c in comparisons:
        row = table[c.criterion]
        row["n"] += 1
        if c.judge.score is None:
            row["errors"] += 1
        elif bool(c.judge.score) == c.human:
            row["agree"] += 1
        elif c.human:
            row["judge_stricter"] += 1
        else:
            row["judge_looser"] += 1
    return table


def render(labels: Labels, comparisons: list[Comparison], rubric: str) -> str:
    table = agreement(comparisons)
    lines = [
        f"# Judge calibration, rubric `{rubric}`",
        "",
        f"Experiment `{labels.experiment}`, {len(labels.runs)} runs labelled by {labels.labelled_by}.",
        "",
        f"Standard: {labels.standard}",
        "",
        "| criterion | labelled | agree | judge stricter | judge looser | judge errors |",
        "|---|---|---|---|---|---|",
    ]
    for key, row in table.items():
        lines.append(
            f"| {key} | {row['n']} | {row['agree']} | {row['judge_stricter']} | {row['judge_looser']} | {row['errors']} |"
        )
    lines += ["", "## Disagreements", ""]
    disagreements = [c for c in comparisons if c.judge.score is not None and bool(c.judge.score) != c.human]
    if not disagreements:
        lines.append("None.")
    by_run = {(run.example_id, run.repetition): run for run in labels.runs}
    for c in disagreements:
        run = by_run[(c.example_id, c.repetition)]
        lines += [
            f"### {c.example_id} rep {c.repetition}, `{c.criterion}`: human {'pass' if c.human else 'fail'}, judge {'pass' if c.judge.score else 'fail'}",
            "",
            f"- Human: {run.note}",
            f"- Judge: {c.judge.comment}",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", default=None, help="defaults to the one in labels.json")
    args = parser.parse_args()
    load_dotenv()

    labels = load_labels()
    experiment = args.experiment or labels.experiment
    comparisons = compare(Judge(), labels, load_records(experiment))
    rubric = rubric_id()
    report = render(labels, comparisons, rubric)
    path = CALIBRATION_DIR / f"report-{rubric}.md"
    path.write_text(report)
    print(report.split("## Disagreements")[0])
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
