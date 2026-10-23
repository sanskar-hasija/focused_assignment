"""Run an experiment on the LangSmith dataset and write its reports.

make eval AGENT=triage SPLIT=dev REPS=3 PREFIX=baseline [LIMIT=3] [JUDGE=0]

The deterministic checks always run; the LLM judge (evals/judge.py) runs unless
--no-judge is given. Every run uses its own copy of the database (app.eval_target), so concurrent runs
never see each other's tickets.
"""

import argparse
import hashlib
import os
import subprocess
import warnings
from collections import defaultdict

from dotenv import load_dotenv
from langsmith import Client
from langsmith.evaluation import evaluate

from app.eval_target import make_target
import app.prompts
from evals import adapters
from evals.evaluators import CHECKS, load_clauses, run_checks
from evals.judge import Judge
from evals.push_dataset import DEFAULT_DATASET
from evals.reports import ExperimentInfo, RepetitionResult, write_reports


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "no-git"


def trace_url(client: Client, run, project_id) -> str:
    # get_run_url is deprecated in langsmith 0.14.11, but its suggested replacement,
    # client.runs.get_url, returns an un-awaited coroutine from the sync client here.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return client.get_run_url(run=run, project_id=project_id)


def prompt_sha() -> str:
    """Short hash of app/prompts.py, which holds every agent's prompt templates."""
    return hashlib.sha256(open(app.prompts.__file__, "rb").read()).hexdigest()[:10]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default="triage")
    parser.add_argument("--split", choices=["dev", "heldout"], default="dev")
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--prefix", default="baseline")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-judge", action="store_true", help="deterministic checks only")
    args = parser.parse_args()
    load_dotenv()

    client = Client()
    dataset = os.getenv("EVAL_DATASET", DEFAULT_DATASET)
    data = list(client.list_examples(dataset_name=dataset, splits=[args.split], limit=args.limit))
    clauses = load_clauses()
    judge = None if args.no_judge else Judge()
    checks = CHECKS + (judge.checks if judge else [])
    metadata = {
        "agent": args.agent,
        "split": args.split,
        "git_sha": git_sha(),
        "prompt_sha": prompt_sha(),
        "judge_model": (os.getenv("JUDGE_MODEL") or os.getenv("AGENT_MODEL")) if judge else None,
    }
    print(f"Running {args.agent} on {len(data)} {args.split} examples x {args.reps} from {dataset}")

    results = evaluate(
        make_target(args.agent),
        data=data,
        evaluators=adapters.evaluators(checks, clauses),
        summary_evaluators=adapters.summary_evaluators(clauses),
        experiment_prefix=f"{args.prefix}-{args.agent}-{args.split}",
        num_repetitions=args.reps,
        max_concurrency=4,
        metadata=metadata,
        client=client,
    )
    rows = list(results)

    # The reports recompute the checks locally: the deterministic ones match the feedback
    # the evaluators posted, and the judge verdicts come from its cache, so no extra calls.
    by_example = defaultdict(list)
    for row in rows:
        by_example[row["example"].id].append(row)
    examples, repetitions = {}, []
    for example_rows in by_example.values():
        example = adapters.example_from_langsmith(example_rows[0]["example"])
        examples[example.id] = example
        for number, row in enumerate(sorted(example_rows, key=lambda r: r["run"].start_time), start=1):
            run = row["run"]
            record = adapters.record_from_run(run)
            repetitions.append(
                RepetitionResult(
                    example_id=example.id,
                    repetition=number,
                    run_id=str(run.id),
                    trace_url=trace_url(client, run, results.experiment_id),
                    record=record,
                    checks=run_checks(record, example, clauses)
                    + (judge.run(record, example, clauses) if judge else []),
                )
            )
    repetitions.sort(key=lambda r: (r.example_id, r.repetition))

    info = ExperimentInfo(
        name=results.experiment_name,
        url=results.url,
        agent=args.agent,
        split=args.split,
        repetitions=args.reps,
        **{k: metadata[k] for k in ("git_sha", "prompt_sha")},
    )
    out_dir = write_reports(info, examples, repetitions)
    print(f"Wrote {out_dir}/summary.md, failures.md and results.json")
    print(info.url)


if __name__ == "__main__":
    main()
