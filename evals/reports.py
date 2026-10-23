"""Write an experiment's reports: summary.md, failures.md and results.json."""

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from pydantic import BaseModel

from app.models import RunRecord
from evals.evaluators import CHECKS, COST_KEYS, FAILURE_KEYS, GATE_KEYS, INFO_KEYS
from evals.judge import JUDGE_KEYS
from evals.schema import CheckResult, EvalExample

RESULTS_DIR = Path(__file__).resolve().parent / "results"
CHECK_KEYS = [check.__name__ for check in CHECKS] + JUDGE_KEYS


class ExperimentInfo(BaseModel):
    name: str
    url: str
    agent: str
    split: str
    repetitions: int
    git_sha: str
    prompt_sha: str


class RepetitionResult(BaseModel):
    example_id: str
    repetition: int  # 1-based, in run start order
    run_id: str
    trace_url: str
    record: RunRecord
    checks: list[CheckResult]

    def score(self, key: str) -> float | None:
        return next((c.score for c in self.checks if c.key == key), None)

    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.key in FAILURE_KEYS and c.score is not None and c.score < 1]

    def judge_failed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.key in JUDGE_KEYS and c.score is not None and c.score < 1]


def write_reports(
    info: ExperimentInfo, examples: dict[str, EvalExample], results: list[RepetitionResult]
) -> Path:
    out_dir = RESULTS_DIR / info.name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.md").write_text(render_summary(info, examples, results))
    (out_dir / "failures.md").write_text(render_failures(info, examples, results))
    (out_dir / "results.json").write_text(
        json.dumps(
            {
                "experiment": info.model_dump(),
                "results": [r.model_dump(mode="json") for r in results],
            },
            indent=2,
        )
    )
    return out_dir


# summary.md


def _mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _scores(results: list[RepetitionResult], key: str) -> list[float]:
    return [s for r in results if (s := r.score(key)) is not None]


def _fmt(value: float | None, key: str) -> str:
    if value is None:
        return "-"
    if key in COST_KEYS or key in INFO_KEYS:
        return f"{value:.1f}"
    return f"{value:.2f}"


def render_summary(
    info: ExperimentInfo, examples: dict[str, EvalExample], results: list[RepetitionResult]
) -> str:
    n_examples = len({r.example_id for r in results})
    emergencies = _scores(results, "emergency_caught")
    false_flags = _scores(results, "false_emergency")
    costs = _scores(results, "cost")
    lines = [
        f"# {info.name}",
        "",
        f"Agent `{info.agent}` on the `{info.split}` split: {n_examples} examples x"
        f" {info.repetitions} repetitions = {len(results)} runs."
        f" Git `{info.git_sha}`, prompt `{info.prompt_sha}`.",
        "",
        "## Hard gates (target: zero failures)",
        "",
        f"- Emergencies caught: **{int(sum(emergencies))} of {len(emergencies)}** runs",
        f"- False emergencies: **{sum(s == 0 for s in false_flags)}** runs",
        f"- Mean cost: **{_fmt(_mean(costs), 'cost')}** per run (lower is better)",
        "",
        "| gate | failures | runs checked |",
        "|---|---|---|",
    ]
    for key in GATE_KEYS:
        scores = _scores(results, key)
        lines.append(f"| {key} | {sum(s < 1 for s in scores)} | {len(scores)} |")

    lines += [
        "",
        "## Every check",
        "",
        "Mean over every run where the check applies (n runs). `cost` is a cost, lower is"
        " better; `tool_calls` and `tool_errors` are mean counts; the last three rows are"
        " the LLM judge (pass rate).",
        "",
        "| check | mean | n |",
        "|---|---|---|",
    ]
    for key in CHECK_KEYS:
        scores = _scores(results, key)
        lines.append(f"| {key} | {_fmt(_mean(scores), key)} | {len(scores)} |")

    by_slice: dict[str, list[RepetitionResult]] = defaultdict(list)
    for result in results:
        for slice_name in examples[result.example_id].metadata.slices:
            by_slice[slice_name].append(result)
    lines += [
        "",
        "## By slice",
        "",
        "Means per slice; `-` where no run in the slice is checked.",
        "",
        "| slice | examples | " + " | ".join(CHECK_KEYS) + " |",
        "|---|---|" + "---|" * len(CHECK_KEYS),
    ]
    for slice_name in sorted(by_slice):
        rows = by_slice[slice_name]
        cells = [_fmt(_mean(_scores(rows, key)), key) for key in CHECK_KEYS]
        n = len({r.example_id for r in rows})
        lines.append(f"| {slice_name} | {n} | " + " | ".join(cells) + " |")

    lines += ["", "## Experiment", "", info.url, ""]
    return "\n".join(lines)


# failures.md


def _issues(issues) -> str:
    return ", ".join(f"{i.category}/{i.priority}/{i.ticket}" for i in issues) or "[]"


def render_failures(
    info: ExperimentInfo, examples: dict[str, EvalExample], results: list[RepetitionResult]
) -> str:
    by_example: dict[str, list[RepetitionResult]] = defaultdict(list)
    for result in results:
        by_example[result.example_id].append(result)

    lines = [
        f"# Failures: {info.name}",
        "",
        "Examples that failed a hard gate or an issue, ticket or clause check"
        f" ({', '.join(FAILURE_KEYS)}) or a judge criterion ({', '.join(JUDGE_KEYS)})"
        " in at least one repetition."
        " FLAKY: those checks scored differently across repetitions.",
        "",
    ]
    failing = [
        eid for eid in sorted(by_example)
        if any(r.failed() or r.judge_failed() for r in by_example[eid])
    ]  # fmt: skip
    if not failing:
        lines.append("No failures.")
    for example_id in failing:
        reps = sorted(by_example[example_id], key=lambda r: r.repetition)
        example = examples[example_id]
        ref = example.reference
        flaky = len({tuple(r.score(k) for k in FAILURE_KEYS + JUDGE_KEYS) for r in reps}) > 1
        outage = " (ticketing down)" if example.inputs.fail_create_ticket else ""
        lines += [
            f"## {example_id}{' FLAKY' if flaky else ''}: {example.inputs.message}",
            "",
            f"- Tenant {example.inputs.tenant_id}, {example.inputs.now:%Y-%m-%d %H:%M}{outage}",
            f"- Expected {_issues(ref.issues)} · gold {', '.join(ref.gold_clauses) or '-'}"
            f" · forbidden {', '.join(ref.forbidden_clauses) or '-'}",
            "",
        ]
        for rep in reps:
            record = rep.record
            got = _issues(record.result.issues) if record.result else "no result"
            cited = ", ".join(record.result.cited_clauses) if record.result else "-"
            created = ", ".join(f"{t.id} {t.category}/{t.priority}" for t in record.tickets_created) or "-"
            lines += [
                f"### Repetition {rep.repetition}",
                "",
                f"- Got {got} · cited {cited or '-'} · created {created}",
                f"- Tools {' -> '.join(record.tool_calls) or '-'} · errors {record.tool_errors}",
                "- Failed: " + ("; ".join(f"`{c.key}` {c.comment}" for c in rep.failed()) or "none"),
            ]
            if rep.judge_failed():
                lines.append("- Judge failed: " + "; ".join(f"`{c.key}` {c.comment}" for c in rep.judge_failed()))
            if record.error:
                lines.append(f"- Error: {record.error}")
            lines.append(f"- Trace: {rep.trace_url}")
            lines.append("")
            reply = record.result.reply if record.result else "(no reply)"
            lines += ["> " + line if line else ">" for line in reply.splitlines()]
            lines.append("")
    return "\n".join(lines)
