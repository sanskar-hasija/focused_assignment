"""Run a few examples through the agent and print what it did next to the reference.

make smoke IDS="D02 D24 D32". No scoring: this is for eyeballing, not measuring.
"""

import argparse

from dotenv import load_dotenv
from langchain_core.tracers.langchain import wait_for_all_tracers

from app.eval_target import make_target
from app.models import RunRecord
from evals.examples import EXAMPLES
from evals.schema import EvalExample

BY_ID = {example.id: example for example in EXAMPLES}


def _issues(issues) -> str:
    return ", ".join(f"{i.category}/{i.priority}/{i.ticket}" for i in issues) or "[]"


def show(example: EvalExample, record: RunRecord) -> None:
    ref = example.reference
    result = record.result
    flag = "  (ticketing down)" if example.inputs.fail_create_ticket else ""
    print(f"== {example.id} {example.inputs.tenant_id}{flag}: {example.inputs.message}")
    print(f"   issues    expected {_issues(ref.issues)}")
    print(f"             got      {_issues(result.issues) if result else '-'}")
    print(f"   clauses   gold {', '.join(ref.gold_clauses) or '-'}"
          f" · forbidden {', '.join(ref.forbidden_clauses) or '-'}")
    print(f"             cited {', '.join(result.cited_clauses) if result else '-'}"
          f" · retrieved {', '.join(record.retrieved) or '-'}")
    created = [f"{t.id} {t.category}/{t.priority}{' PAGED' if t.paged_on_call else ''}"
               for t in record.tickets_created]  # fmt: skip
    print(f"   tickets   {', '.join(created) or '-'}")
    print(f"   tools     {' -> '.join(record.tool_calls) or '-'} · errors {record.tool_errors}")
    print(f"   reply     include {ref.reply_must_include or '-'}"
          f" · exclude {ref.reply_must_not_include or '-'}")
    if result:
        print("             " + result.reply.replace("\n", "\n             "))
    if record.error:
        print(f"   ERROR     {record.error}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="+", help="example ids, e.g. D02 D24 D32")
    parser.add_argument("--agent", default="triage")
    args = parser.parse_args()
    unknown = [i for i in args.ids if i not in BY_ID]
    if unknown:
        parser.error(f"unknown example ids: {', '.join(unknown)}")

    load_dotenv()
    target = make_target(args.agent)
    try:
        for example_id in args.ids:
            example = BY_ID[example_id]
            output = target(example.inputs.model_dump(mode="json"))
            show(example, RunRecord.model_validate(output))
    finally:
        wait_for_all_tracers()


if __name__ == "__main__":
    main()
