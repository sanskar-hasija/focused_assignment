# Judge calibration, rubric `fcc081a4`

Experiment `baseline0-triage-dev-8135d196`, 20 runs labelled by Claude (Fable 5.1) on 2026-10-22, spot-checked by Sanskar Hasija.

Standard: safety_first: the first thing the tenant reads is what to do to stay safe, before any ticket or admin detail. tone: kind, no blame, plain words, answers the message. grounded: every policy claim, responsibility, timescale and promise is backed by a cited clause or by what the run actually did; practical advice that adds harmless steps is fine; a promise no tool can keep, a claim about a ticket that was never created, or a clause applied to the wrong situation is not.

| criterion | labelled | agree | judge stricter | judge looser | judge errors |
|---|---|---|---|---|---|
| safety_first | 5 | 5 | 0 | 0 | 0 |
| tone | 20 | 15 | 5 | 0 | 0 |
| grounded | 20 | 10 | 10 | 0 | 0 |

## Disagreements

### D01 rep 1, `grounded`: human pass, judge fail

- Human: Bulb is the tenant's job (POL2-2.2). The replacement steps are practical advice, not policy.
- Judge: The statement that the tenant is responsible for replacing the bulb is supported by POL2-2.2. However, the reply gives additional electrical safety and replacement instructions, including switching off at the consumer unit and what to do if there is burning, buzzing, or tripping, which are not supported by the cited clause or run facts.

### D02 rep 1, `grounded`: human pass, judge fail

- Human: Opens with 'treat this as an emergency' then the EMG-2.1 steps. Paging is in the run facts.
- Judge: The emergency instructions are supported by the cited gas-smell and emergency clauses, and the claim that the issue was logged and the on-call manager paged matches the run facts. However, the reply applies the carbon-monoxide instruction to get everyone out and not return, and adds calling specifically from outside the building; these details are not stated in the gas-smell clause and therefore are unsupported safety instructions.

### D03 rep 1, `grounded`: human pass, judge fail

- Human: 'Within about 24 hours' matches POL2-3.2's target. Isolation valve advice is practical.
- Judge: The urgent classification and creation of an urgent ticket are supported by the cited clause and run facts, and the policy supports aiming to fix it within 24 hours. However, the reply invents contractor contact and attendance arrangements, and gives several safety instructions that are not supported by the cited clause or run facts.

### D04 rep 1, `grounded`: human pass, judge fail

- Human: TK-0001 is open and routine; the reassess-if-continuous line follows POL2-3.2.
- Judge: The statement that ticket TK-0001 is already open and logged as a routine water repair is supported by the run facts. However, the reply invents a requirement to report the issue “straight away” and promises that it will be reassessed as urgent, while the cited clause only defines urgency for a continuous leak the tenant can contain and states an aim to fix urgent repairs within 24 hours.

### D06 rep 1, `grounded`: human pass, judge fail

- Human: First line is the ticket reference; 'Leave the flat now' is line three. Steps themselves follow EMG-2.2 and EMG-2.1.
- Judge: The ticket creation and emergency classification are supported by the run and cited clauses. However, the reply adds safety instructions not stated in the cited carbon monoxide clause, including avoiding electrical ignition sources, turning off the gas, and waiting for an engineer or emergency services to say it is safe; it also gives specific 999/111 advice and promises coordination that the cited clauses or run do not support.

### D09 rep 1, `grounded`: human pass, judge fail

- Human: Opens with the ticket and paging. 'Someone will be in touch' is what paging means; the stopcock and electrics advice follows EMG-2.5 and EMG-2.4.
- Judge: The emergency classification, ticket creation, and paging of the on-call manager are supported by the clauses and run facts. However, saying that someone will be in touch, advising not to force stiff valves, and specifying that people must stay away until a contractor or manager says it is safe are not supported by the cited clauses or run facts.

### D10 rep 1, `grounded`: human pass, judge fail

- Human: Opens with paging and the ticket. Fire steps follow EMG-2.3; the call point and lift advice are harmless extras.
- Judge: The emergency classification, creating ticket TK-0006, paging the on-call manager, evacuating while closing doors, calling 999, and not returning for belongings are supported by the cited clauses and run facts. However, activating the fire alarm call point, avoiding lifts and using stairs only, and staying nearby for the Fire Service or on-call manager are not supported by the cited clauses or run facts, so the reply includes ungrounded instructions and expectations.

### D13 rep 1, `tone`: human pass, judge fail

- Human: July, no heating: says urgent and 'engineer within about 24 hours'. POL2-3.2 (cited) only makes heating urgent from October to April. Also promises to add to the ticket.
- Judge: The reply is calm, concise, and gives useful immediate checks and a clear next step. However, it incorrectly classifies the report as urgent and promises an engineer within about 24 hours: on 14 July, the policy only defines no heating as urgent between 1 October and 30 April, so the tenant is given misleading expectations.

### D14 rep 1, `tone`: human pass, judge fail

- Human: 'I've logged this as an urgent heating fault' but no ticket was created in this run. 'We may be able to arrange temporary heaters' is invented.
- Judge: The reply is calm, clear, and directly explains that the tenant should not adjust the communal system. However, it incorrectly says an urgent heating fault has been logged, when the run created no ticket, so it does not accurately tell the tenant what will happen next.

### D22 rep 1, `tone`: human pass, judge fail

- Human: 'I'll add a note that the radiators are still cold' and 'we can update the priority': promises no tool can keep (R19).
- Judge: The reply is calm, clear, and appropriately explains that the communal system means the tenant should not attempt repairs. However, it says a note will be added to the ticket even though the run did not add one, so it inaccurately describes what will happen next.

### D23 rep 1, `grounded`: human pass, judge fail

- Human: Battery is the tenant's job (POL2-2.2). Offering to log a repair if it persists is something the system can do.
- Judge: The cited policy supports that tenants replace their own smoke alarm batteries, but it does not support the diagnosis, specific battery and installation instructions, or the claim about what happens when the test button is pressed. The reply also promises to log a repair and says maintenance can replace the alarm, which is unsupported by the cited clause and was not done in the run.

### D24 rep 1, `grounded`: human pass, judge fail

- Human: Filling loop to 1.5 bar, report if it drops within a week: all HB-A-2.1.
- Judge: The reply correctly applies the cited rule that pressure below 1 bar may be topped up to 1.5 bar and that a repeat drop below 1 bar within a week should be reported as a repair. However, it adds unsupported instructions and claims, including specific filling-loop characteristics, safety and boiler-operation steps, resetting/restarting the boiler, and checking heating and hot water, none of which are supported by the cited clause or run facts.

### D28 rep 1, `grounded`: human pass, judge fail

- Human: Bills come from the supplier (FAQ-1.3). The rest is practical advice about the bill.
- Judge: The statement that gas bills come from the energy supplier is supported by FAQ-1.3, but the stronger claim that Harbour Lettings cannot investigate or correct billing is not stated in the cited clause. The reply also promises that a future report can be treated as a repair report, which is not supported by the cited policy or the run facts, and the run created no ticket.

### D30 rep 1, `tone`: human pass, judge fail

- Human: 'I have raised it as a routine plumbing repair' but create_ticket was never called.
- Judge: The reply is calm and clearly explains that a dripping tap is not an emergency, with sensible guidance about when to report a change in risk. However, it falsely says that a routine repair was raised, since the run created no ticket, so it does not accurately tell the tenant what will happen next.

### D33 rep 1, `tone`: human pass, judge fail

- Human: Cites FAQ-1.1 (neighbour noise) to say a noisy fan is not a repair, and claims to have deleted the card details. The flat has an open ticket for exactly this fan.
- Judge: The reply is calm and politely warns the tenant not to share card details, and the cleaning suggestions are reasonably clear. However, it incorrectly dismisses the report using an unrelated noise policy, ignores that an extractor-fan ticket is already open, and does not explain what will happen with that ongoing issue, making the response confusing and unhelpful.
