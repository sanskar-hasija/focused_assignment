# Why V0 fails: causes behind the baseline

Experiment `baseline-triage-dev-1e6e1624`: V0 (`triage`) on the 34 dev examples, 3
repetitions, 102 runs, dataset `focused_triage-eval`. Read with [summary.md](summary.md)
and [failures.md](failures.md). Every failing repetition was read and given a one-line
cause; the causes group into five.

## The headline

V0 is better than expected where it matters most and worse where it is easy to be sloppy.

| | result |
|---|---|
| Emergencies caught | 27 of 27 runs |
| False emergencies | 2 of 75 runs (D19, a leak from the flat above, twice) |
| Replies claiming a ticket that was never created | 3 of 102 runs |
| Safety steps first on emergencies (judge) | 18 of 27 runs |
| Grounded reply (judge) | 21 of 102 runs |
| Gold clause cited | 71% |
| Retrieved clauses in scope (current, this building) | 72% |

The model is good at recognising danger. What it gets wrong is process: when to look things
up, what to cite, and describing things it has not done.

## Cause A: V0 chooses when to gather evidence, and sometimes doesn't

- `check_open_tickets` ran on only 1 of 3 D33 runs, so the open ticket for exactly that
  fan was never found; D33 ended with no issue at all, 3 of 3.
- `search_policies` never ran on 2 of 3 D29 runs and 3 of 3 D31 runs, so nothing was cited.
- Unfiltered search returned the superseded policy or other buildings' handbooks in 28% of
  retrieved clauses.
- On gas smells it cited EMG-2.2 (carbon monoxide) in 11 of 12 runs: the wrong procedure,
  retrieved because the two clauses are near neighbours.

**V1 fix:** `gather` always runs both tools, with search filtered to the tenant's building
and current documents; `gate` drops any citation search did not return.

## Cause B: the reply is written with the decision, not after the actions

- "I'll log this as a routine repair" with no `create_ticket` call: D04 once, D30 twice.
- Safety steps come after "I've raised ticket TK-0006 and paged the on-call manager" in
  9 of 27 emergency runs.
- Promises no tool can keep: adding notes to tickets, chasing contractors, arranging
  visits. This is most of the 81 grounded failures.

**V1 fix:** `act` creates the tickets, then `reply` is given what actually happened and a
rule to put the safety clause first. The reply cannot describe a ticket that does not exist.

## Cause C: judgement errors in the decision itself

- D01, bulb gone: no issue at all, 3 of 3 (R1 says one issue, self-help).
- D33, noisy fan: "not a repair", 3 of 3.
- D19, water from the flat above: emergency 2 of 3.

**V1 helps only partly.** `decide` sees the date, the clause text and the open tickets in
one prompt, which fixed D01 and D33, but a gate cannot fix judgement: V1 introduced its own
(D23 and D25 became tickets instead of self-help). Listed in the README as open problems.

## Cause D: an infrastructure bug the eval found

The first baseline run (`baseline0-triage-dev-8135d196`, on the earlier copy of the
dataset) crashed on all 3 D15 runs with `UNIQUE constraint failed: tickets.id`. Two issues
in one message made the model call `create_ticket` twice in parallel; both read the same
highest ticket id. Fixed in `app/tools.py` by taking the write lock before choosing the id,
with a test. Everything else between the runs is model noise, which is why there are 3
repetitions.

## Cause E: limits of the evaluation itself

- All 6 `no_unsafe_advice` failures are replies telling a Birch Court tenant NOT to bleed
  the radiators (D14, D22). A substring check cannot see the negation. The same blind spot
  hit V1 once on the outage case: "no repair ticket has been created" matched the
  "ticket has been created" claim. Kept as is, reported as known false positives; the fix
  is an LLM check or negation-aware matching.
- The `grounded` judge failed every run with its first rubric, which treated any practical
  step beyond the clause text as unsupported. Calibrated against 20 hand labels from
  baseline0 (`evals/calibration/`): agreement went from 30 of 45 to 42 of 45 after one
  rewrite that limits it to claims (policy, timescales, promises, what happened), not advice.
- `gold_cited` punishes a correct decision that cites a neighbouring clause (a routine
  hinge citing POL2-2.1 rather than POL2-3.3). It measures citation discipline, not
  correctness; read it next to `priority_match`.
