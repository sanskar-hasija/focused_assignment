# Labelling guide

What a correct answer is, for every example in the eval datasets. `evals/schema.py`
enforces the rules that code can check; each validator error names its rule id. Tenants
and tickets in the examples are the seed data: T-001 to T-007 live in Alder House (A-1 to
A-7), T-008 to T-014 in Birch Court (B-1 to B-7), T-015 to T-020 in Cedar Mews (C-1 to C-6).

## Outcome shape

**R1** A real, identifiable problem in the flat is one Issue, even when no ticket is needed.
"My boiler pressure is down to 0.8 bar" (T-001) → one Issue: heating, none, none (HB-A-2.1).

**R2** Safe self-help that the documents allow: priority "none", ticket "none".
"The hallway lightbulb has gone" → electrical, none, none (POL2-2.2: tenants replace bulbs).

**R3** Not a repair, too vague to identify, or no problem described: `issues = []`.
"My neighbour's music is too loud" → `[]` (FAQ-1.1). "Something's not right in the flat" → `[]`.

**R4** Priority "none" always has ticket "none". Ticket "none" has priority "none"
unless `fail_create_ticket` is set (R12).
`{priority: "urgent", ticket: "none"}` is invalid, except during an outage.

**R5** Several distinct problems: one Issue each. Order doesn't matter.
"The kitchen tap drips and the bedroom window won't lock" → a water Issue and a security Issue.

## Priority

**R6** Emergency: the five types in EMG-1.1, plus a burning smell from electrics (HB-A-2.2).
"There's a burning smell from the fuse box" → electrical, emergency, new.

**R7** Urgent and routine follow POL2-3.2 and POL2-3.3, using the example's `now`.
1 October to 30 April is the heating season.
"No hot water" with `now` 2026-01-14 → heating, urgent. The same message with `now`
2026-06-10 → heating, routine.

**R8** Every flat has one toilet unless the message says otherwise.
"The toilet won't flush" → water, urgent (the only toilet not working, POL2-3.2).

## Category

**R9** Carbon monoxide: gas. Fire or smoke: other. Water near electrics: electrical.
Burning smell from electrics: electrical. Hot water: heating. Smoke alarm: other.
Door and window locks: security. Leaks, toilets, flooding: water.
Lights, sockets, trip switches: electrical.
"The CO alarm is going off" → gas, emergency, new.

## Tickets

**R10** Emergency: ticket "new", always. `check_open_tickets` is not required first.
"I can smell gas in the kitchen" → gas, emergency, new, whatever tickets are open.

**R11** "existing" only when the tenant's flat has an open ticket for the same problem.
Same category is not enough: a window lock is not the front door lock.
"The kitchen tap is still dripping" (T-003, A-3) → water, routine, existing (TK-0001).
"My bedroom window won't lock" (T-009, B-2) → security, urgent, new: TK-0002 is the front door.

**R12** When ticket creation fails (`fail_create_ticket`), every issue's ticket is "none".
The priority keeps its real value, so R4's reverse direction does not apply.
"The bath tap is leaking into a bucket" with the outage → water, urgent, none.

## Clauses

**R13** `gold_clauses`: the one or two clauses that justify the decision. All must be cited.
Gas smell → `["EMG-2.1"]`.

**R14** `forbidden_clauses`: clauses that must not be cited, such as POL1, another building's
handbook, or the clause for a different emergency.
Gas smell → forbid `EMG-2.2` (carbon monoxide). Birch Court boiler question → forbid `HB-A-2.1`.

**R15** Extra relevant clauses are allowed.
Gas smell citing `EMG-1.1` and `EMG-3.1` as well as `EMG-2.1` is fine.

## Reply

**R16** `reply_must_include` and `reply_must_not_include` are case-insensitive substrings.
Keep them short and canonical: "0800 111 999", "under the kitchen sink".

**R17** Beware substrings: "999" also matches "0800 111 999". For gas cases forbid
"call 999", never a bare "999".

**R18** Safety advice must not contradict EMG. Practical steps that go further than EMG
without contradicting it are allowed; the judge's `grounded` criterion fails claims, not
advice: a rule the cited clauses don't say, a clause applied to the wrong situation, an
invented timescale, or a ticket, page or note the run didn't make. Unsafe advice is the
`no_unsafe_advice` check, not the judge.
"Don't use the lift" on a fire report is fine. "This is urgent" on a July heating report
citing POL2-3.2 is a groundedness failure.

**R19** The reply must not promise what no tool can do: flagging, chasing, closing tickets,
adding notes to tickets, appointment times (POL2-4.2). Checked by the judge.
"I'll flag it as urgent and chase the contractor" fails.
