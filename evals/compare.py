"""Compare two experiments side by side: make compare BEFORE=<name> AFTER=<name>

Reads evals/results/<name>/results.json for each and writes
evals/results/compare-<before>-vs-<after>.md: the hard gates as counts, every check as a
mean with the change, the same by slice, and the examples whose outcome changed. Only
examples present in both experiments are compared.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from pydantic import BaseModel

from evals.evaluators import COST_KEYS, GATE_KEYS, INFO_KEYS
from evals.examples import EXAMPLES
from evals.judge import JUDGE_KEYS
from evals.reports import CHECK_KEYS

RESULTS_DIR = Path(__file__).resolve().parent / "results"
BY_ID = {example.id: example for example in EXAMPLES}
LOWER_IS_BETTER = set(COST_KEYS)


class Loaded(BaseModel):
    name: str
    agent: str
    url: str
    scores: dict[str, dict[str, list[float]]]  # example id -> check key -> scores over reps


def load(name: str) -> Loaded:
    data = json.loads((RESULTS_DIR / name / "results.json").read_text())
    scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in data["results"]:
        for check in row["checks"]:
            if check["score"] is not None:
                scores[row["example_id"]][check["key"]].append(check["score"])
    info = data["experiment"]
    return Loaded(name=info["name"], agent=info["agent"], url=info["url"], scores=scores)


def _all(loaded: Loaded, key: str, ids: list[str]) -> list[float]:
    return [s for eid in ids for s in loaded.scores[eid].get(key, [])]


def _fmt(values: list[float], key: str) -> str:
    if not values:
        return "-"
    if key in LOWER_IS_BETTER or key in INFO_KEYS:
        return f"{mean(values):.1f}"
    return f"{mean(values):.2f}"


def _delta(before: list[float], after: list[float], key: str) -> str:
    if not before or not after:
        return ""
    diff = mean(after) - mean(before)
    if abs(diff) < 0.005:
        return "same"
    better = diff < 0 if key in LOWER_IS_BETTER else diff > 0
    if key in INFO_KEYS:
        return f"{diff:+.1f}"
    arrow = "better" if better else "WORSE"
    return f"{diff:+.2f} {arrow}" if key not in LOWER_IS_BETTER else f"{diff:+.1f} {arrow}"


def _gate_counts(loaded: Loaded, key: str, ids: list[str]) -> str:
    values = _all(loaded, key, ids)
    return f"{sum(v < 1 for v in values)} of {len(values)}"


def render(before: Loaded, after: Loaded) -> str:
    ids = sorted(set(before.scores) & set(after.scores))
    lines = [
        f"# {before.agent} vs {after.agent}",
        "",
        f"Before: `{before.name}` ({before.url}). After: `{after.name}` ({after.url}).",
        f"{len(ids)} examples in both.",
        "",
        "## Hard gates: failures (target zero)",
        "",
        "| gate | before | after |",
        "|---|---|---|",
    ]
    for key in GATE_KEYS:
        lines.append(f"| {key} | {_gate_counts(before, key, ids)} | {_gate_counts(after, key, ids)} |")
    caught = lambda l: f"{int(sum(_all(l, 'emergency_caught', ids)))} of {len(_all(l, 'emergency_caught', ids))}"
    lines += ["", f"Emergencies caught: before **{caught(before)}**, after **{caught(after)}** runs.", ""]

    lines += [
        "## Every check",
        "",
        "Mean over runs where the check applies. `cost` lower is better; `tool_calls` and"
        " `tool_errors` are counts; the last three are the LLM judge.",
        "",
        "| check | before | after | change |",
        "|---|---|---|---|",
    ]
    for key in CHECK_KEYS:
        b, a = _all(before, key, ids), _all(after, key, ids)
        lines.append(f"| {key} | {_fmt(b, key)} | {_fmt(a, key)} | {_delta(b, a, key)} |")

    headline = ["emergency_caught", "false_emergency", "ticket_claims_true", "priority_match", "ticket_match",
                "cost", "gold_cited", "forbidden_cited", "retrieval_in_scope", "safety_first", "grounded"]  # fmt: skip
    by_slice: dict[str, list[str]] = defaultdict(list)
    for eid in ids:
        for slice_name in BY_ID[eid].metadata.slices:
            by_slice[slice_name].append(eid)
    lines += [
        "",
        "## By slice (before -> after)",
        "",
        "| slice | n | " + " | ".join(headline) + " |",
        "|---|---|" + "---|" * len(headline),
    ]
    for slice_name in sorted(by_slice):
        sids = by_slice[slice_name]
        cells = []
        for key in headline:
            b, a = _all(before, key, sids), _all(after, key, sids)
            cells.append(f"{_fmt(b, key)} -> {_fmt(a, key)}" if b or a else "-")
        lines.append(f"| {slice_name} | {len(sids)} | " + " | ".join(cells) + " |")

    lines += ["", "## Examples whose outcome checks changed", "", "Mean of priority_match, ticket_match and issue_count_match over repetitions.", ""]
    changed = []
    for eid in ids:
        keys = ["priority_match", "ticket_match", "issue_count_match"]
        b = mean(s for k in keys for s in before.scores[eid].get(k, []))
        a = mean(s for k in keys for s in after.scores[eid].get(k, []))
        if abs(a - b) >= 0.01:
            changed.append((eid, b, a))
    if not changed:
        lines.append("None.")
    else:
        lines += ["| example | message | before | after |", "|---|---|---|---|"]
        for eid, b, a in changed:
            word = "better" if a > b else "WORSE"
            lines.append(f"| {eid} | {BY_ID[eid].inputs.message[:70]} | {b:.2f} | {a:.2f} ({word}) |")
    lines += ["", "## Judge: examples whose grounded or safety_first pass rate changed", ""]
    jchanged = []
    for eid in ids:
        for key in ("safety_first", "grounded"):
            b, a = before.scores[eid].get(key, []), after.scores[eid].get(key, [])
            if b and a and abs(mean(a) - mean(b)) >= 0.01:
                jchanged.append(f"| {eid} | {key} | {mean(b):.2f} | {mean(a):.2f} |")
    lines += (["| example | criterion | before | after |", "|---|---|---|---|"] + jchanged) if jchanged else ["None."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    args = parser.parse_args()
    before, after = load(args.before), load(args.after)
    out = RESULTS_DIR / f"compare-{args.before}-vs-{args.after}.md"
    out.write_text(render(before, after))
    print(out.read_text().split("## Every check")[0])
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
