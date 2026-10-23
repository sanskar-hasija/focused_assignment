"""Push evals/examples.py to a LangSmith dataset: make dataset (or --dry-run).

Example ids are uuid5 of the dataset name and the local id, so pushing twice changes
nothing, and the same examples can live in a second dataset under different ids (LangSmith
example ids are unique across datasets). Missing examples are created and changed ones
updated. Nothing is ever deleted: deleting
the dataset would delete its experiments, so remote extras are only reported.
"""

import argparse
import os
import uuid
from collections import Counter

from dotenv import load_dotenv

from evals.examples import EXAMPLES
from evals.schema import EvalExample, expected_outcome

DEFAULT_DATASET = "triage-eval"


def remote_id(example: EvalExample, dataset_name: str = DEFAULT_DATASET) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{dataset_name}/{example.id}")


def payload(example: EvalExample, dataset_name: str = DEFAULT_DATASET) -> dict:
    return {
        "id": remote_id(example, dataset_name),
        "inputs": example.inputs.model_dump(mode="json"),
        "outputs": example.reference.model_dump(mode="json"),
        "metadata": example.metadata.model_dump() | {"example_id": example.id},
        "split": example.metadata.split,
    }


def print_counts(examples: list[EvalExample]) -> None:
    def show(title: str, counts: Counter) -> None:
        print(f"{title}: " + ", ".join(f"{key} {n}" for key, n in sorted(counts.items())))

    print(f"{len(examples)} valid examples")
    show("by split", Counter(e.metadata.split for e in examples))
    show("by outcome", Counter(expected_outcome(e.reference) for e in examples))
    show("by slice", Counter(s for e in examples for s in e.metadata.slices))


def push(dataset_name: str, examples: list[EvalExample]) -> None:
    from langsmith import Client

    client = Client()
    if client.has_dataset(dataset_name=dataset_name):
        dataset = client.read_dataset(dataset_name=dataset_name)
    else:
        dataset = client.create_dataset(
            dataset_name, description="Harbour Lettings triage evaluation (evals/examples.py)"
        )
        print(f"Created dataset {dataset_name}")

    remote = {example.id: example for example in client.list_examples(dataset_id=dataset.id)}
    to_create, to_update = [], []
    for example in examples:
        local = payload(example, dataset_name)
        current = remote.get(local["id"])
        if current is None:
            to_create.append(local)
        elif _differs(current, local):
            to_update.append(local)

    if to_create:
        client.create_examples(dataset_id=dataset.id, examples=to_create)
    if to_update:
        client.update_examples(dataset_id=dataset.id, updates=to_update)

    local_ids = {remote_id(example, dataset_name) for example in examples}
    extras = [example for rid, example in remote.items() if rid not in local_ids]
    unchanged = len(examples) - len(to_create) - len(to_update)
    print(
        f"{dataset_name}: {len(to_create)} created, {len(to_update)} updated, {unchanged} unchanged"
    )
    for extra in extras:
        print(f"  remote example not in evals/examples.py (left in place): {extra.id}")


def _differs(current, local: dict) -> bool:
    metadata = dict(current.metadata or {})
    splits = metadata.pop("dataset_split", None) or []
    return (
        current.inputs != local["inputs"]
        or current.outputs != local["outputs"]
        or metadata != local["metadata"]
        or splits != [local["split"]]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="validate and print, don't push")
    args = parser.parse_args()
    load_dotenv()

    print_counts(EXAMPLES)  # validation already ran when EXAMPLES was imported
    if args.dry_run:
        return
    push(os.getenv("EVAL_DATASET", DEFAULT_DATASET), EXAMPLES)


if __name__ == "__main__":
    main()
