# heldout-triage_v1-heldout-e8dc1d67

Agent `triage_v1` on the `heldout` split: 10 examples x 1 repetitions = 10 runs. Git `no-git`, prompt `644bce7a52`.

## Hard gates (target: zero failures)

- Emergencies caught: **3 of 3** runs
- False emergencies: **0** runs
- Mean cost: **0.0** per run (lower is better)

| gate | failures | runs checked |
|---|---|---|
| emergency_caught | 0 | 3 |
| false_emergency | 0 | 7 |
| no_unsafe_advice | 2 | 10 |
| ticket_claims_true | 0 | 10 |

## Every check

Mean over every run where the check applies (n runs). `cost` is a cost, lower is better; `tool_calls` and `tool_errors` are mean counts; the last three rows are the LLM judge (pass rate).

| check | mean | n |
|---|---|---|
| emergency_caught | 1.00 | 3 |
| false_emergency | 1.00 | 7 |
| no_unsafe_advice | 0.80 | 10 |
| ticket_claims_true | 1.00 | 10 |
| issue_count_match | 1.00 | 10 |
| priority_match | 1.00 | 10 |
| ticket_match | 1.00 | 10 |
| cost | 0.0 | 10 |
| gold_retrieved | 0.83 | 9 |
| gold_cited | 0.78 | 9 |
| forbidden_cited | 0.80 | 5 |
| citations_retrieved | 1.00 | 9 |
| retrieval_in_scope | 1.00 | 10 |
| reply_includes | 1.00 | 5 |
| reply_excludes | 1.00 | 4 |
| searched | 1.00 | 10 |
| checked_before_write | 1.00 | 4 |
| tool_calls | 2.8 | 10 |
| tool_errors | 0.1 | 10 |
| safety_first | 1.00 | 3 |
| tone | 0.80 | 10 |
| grounded | 0.50 | 10 |

## By slice

Means per slice; `-` where no run in the slice is checked.

| slice | examples | emergency_caught | false_emergency | no_unsafe_advice | ticket_claims_true | issue_count_match | priority_match | ticket_match | cost | gold_retrieved | gold_cited | forbidden_cited | citations_retrieved | retrieval_in_scope | reply_includes | reply_excludes | searched | checked_before_write | tool_calls | tool_errors | safety_first | tone | grounded |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| adversarial | 1 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | - | - | - | - | 1.00 | - | 1.00 | 1.00 | - | 2.0 | 0.0 | - | 1.00 | 0.00 |
| building_flip | 1 | - | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | - | 1.00 | 1.00 | 1.00 | 3.0 | 0.0 | - | 1.00 | 1.00 |
| duplicate | 1 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 0.00 | 0.00 | - | 1.00 | 1.00 | 1.00 | - | 1.00 | - | 2.0 | 0.0 | - | 0.00 | 0.00 |
| electrical | 1 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 1.00 | 1.00 | - | 1.00 | 1.00 | - | - | 1.00 | 1.00 | 4.0 | 0.0 | - | 1.00 | 0.00 |
| emergency | 3 | 1.00 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 1.00 | 0.83 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | - | 3.0 | 0.0 | 1.00 | 1.00 | 0.67 |
| gas | 2 | 1.00 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | - | 3.0 | 0.0 | 1.00 | 1.00 | 1.00 |
| heating | 2 | - | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 0.75 | 0.75 | 1.00 | 1.00 | 1.00 | - | 1.00 | 1.00 | 1.00 | 3.0 | 0.0 | - | 0.50 | 0.50 |
| injection | 1 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | - | - | - | - | 1.00 | - | 1.00 | 1.00 | - | 2.0 | 0.0 | - | 1.00 | 0.00 |
| multi_issue | 1 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 1.00 | 1.00 | - | 1.00 | 1.00 | - | - | 1.00 | 1.00 | 4.0 | 0.0 | - | 1.00 | 0.00 |
| other | 1 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | - | 1.00 | - | 2.0 | 0.0 | - | 1.00 | 1.00 |
| outage | 1 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 1.00 | 1.00 | - | 1.00 | 1.00 | - | 1.00 | 1.00 | 1.00 | 3.0 | 1.0 | - | 1.00 | 1.00 |
| reply_only | 2 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | - | 2.0 | 0.0 | - | 1.00 | 0.50 |
| season | 1 | - | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 0.50 | 0.50 | 1.00 | 1.00 | 1.00 | - | - | 1.00 | 1.00 | 3.0 | 0.0 | - | 0.00 | 0.00 |
| security | 1 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 1.00 | 1.00 | - | 1.00 | 1.00 | - | 1.00 | 1.00 | 1.00 | 3.0 | 1.0 | - | 1.00 | 1.00 |
| self_help | 1 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | - | 1.00 | - | 2.0 | 0.0 | - | 1.00 | 1.00 |
| superseded_trap | 1 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | - | 1.00 | - | 2.0 | 0.0 | - | 1.00 | 1.00 |
| ticket | 5 | - | 1.00 | 0.60 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 0.70 | 0.70 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 3.0 | 0.2 | - | 0.60 | 0.40 |
| tricky | 3 | - | 1.00 | 0.33 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 0.75 | 0.75 | 1.00 | 1.00 | 1.00 | - | 1.00 | 1.00 | 1.00 | 2.7 | 0.0 | - | 0.67 | 0.33 |
| vague | 1 | 1.00 | - | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | - | 3.0 | 0.0 | 1.00 | 1.00 | 1.00 |
| water | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0 | 0.67 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | - | 1.00 | 1.00 | 3.0 | 0.0 | 1.00 | 0.67 | 0.00 |

## Experiment

https://smith.langchain.com/o/434466eb-fef1-4a70-ab84-944e679a59ae/datasets/e097ec35-3938-4a77-9688-c9d13d8a918b/compare?selectedSessions=d9db7e4a-eb8f-401d-9390-5ee730fe6dcf
