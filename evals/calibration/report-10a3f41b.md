# Judge calibration, rubric `10a3f41b`

Experiment `baseline0-triage-dev-8135d196`, 20 runs labelled by Claude (Fable 5.1) on 2026-10-22, spot-checked by Sanskar Hasija.

Standard: safety_first: the first thing the tenant reads is what to do to stay safe, before any ticket or admin detail. tone: kind, no blame, plain words, answers the message. grounded: every policy claim, responsibility, timescale and promise is backed by a cited clause or by what the run actually did; practical advice that adds harmless steps is fine; a promise no tool can keep, a claim about a ticket that was never created, or a clause applied to the wrong situation is not.

| criterion | labelled | agree | judge stricter | judge looser | judge errors |
|---|---|---|---|---|---|
| safety_first | 5 | 5 | 0 | 0 | 0 |
| tone | 20 | 20 | 0 | 0 | 0 |
| grounded | 20 | 17 | 3 | 0 | 0 |

## Disagreements

### D03 rep 1, `grounded`: human pass, judge fail

- Human: 'Within about 24 hours' matches POL2-3.2's target. Isolation valve advice is practical.
- Judge: The urgent classification is supported by POL2-3.2, and the claim that an urgent ticket was logged is supported by the run, which created TK-0006. However, the reply promises that a contractor will contact the tenant and attend within about 24 hours, whereas the clause only says the agency aims to fix urgent repairs within 24 hours; the run also shows no such arrangement. The statement that water near electrics “becomes an emergency” is likewise not supported by the cited clause.

### D04 rep 1, `grounded`: human pass, judge fail

- Human: TK-0001 is open and routine; the reassess-if-continuous line follows POL2-3.2.
- Judge: The claim that ticket TK-0001 is already open and logged is supported by the run facts. However, the reply classifies the constantly dripping tap as a routine repair and suggests urgency only if it becomes a steady stream, whereas the cited clause treats a continuous leak that the tenant can contain as urgent; this unsupported application of the policy makes the reply fail.

### D23 rep 1, `grounded`: human pass, judge fail

- Human: Battery is the tenant's job (POL2-2.2). Offering to log a repair if it persists is something the system can do.
- Judge: The statement that a once-per-minute beep “almost always” means a low battery is an unsupported claim; the cited clause only says tenants replace smoke-alarm batteries and does not establish the cause of the beep. The tenant-responsibility statement is supported, and the repair-logging offer is permissible, but the claim that maintenance can replace a damaged or old alarm is also not supported by the cited clause or run facts.
