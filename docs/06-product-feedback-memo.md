# 06 — Product feedback from deployment

**To:** Engineering / Product
**From:** Deployment
**Re:** Harbourline (purchase reconciliation, bulk oilseeds) — what the platform should absorb
**Status:** all five items are currently handled in per-customer configuration and will be re-handled by hand on every similar deployment

---

Written the way I would want to receive it: each item states what happened, what it cost, what I
did locally, and what I think belongs in the platform — separated so you can disagree with the
last part without re-litigating the first.

---

## 1. Exceptions need a contractual clock, not just a value — P1

**What happened.** The catalogue identified USD 184,294.60 recoverable on one shipment. Each
exception carries a value, a remedy and an owner. None carries an expiry. GAFTA and FOSFA forms
time-bar quality and condition claims; a credit note request that sits in a queue past the bar is
worth exactly zero, and the queue gives no signal that it is decaying.

**Cost.** Full value of any time-barred claim. On this single shipment, USD 184,294.60.

**Local workaround.** A Friday calendar reminder for the ops lead. This is not a control; it is a
person remembering.

**Proposed.** `Exception` gains `deadline` and `deadline_source`, derived from the governing
contract form's time-bar clause at configuration time. Queues sort by deadline, not age. Escalate
at 50% of remaining time.

**Why platform, not config.** Time bars are a property of standard contract forms, not of
customers. GAFTA 100's bar is the same for every customer who trades on it. Configuring this per
deployment means re-deriving the same clause dozens of times and getting it wrong somewhere.

Asserted as a known gap in `evals/golden/10-claim-time-bar-known-gap.json` so it cannot quietly
disappear.

---

## 2. Delegated authority should be a first-class object — P1

**What happened.** SHP-02 is the only rule in the catalogue that cannot be automated at any
confidence level, and it is the one that gates the highest-value exception. The model reads the
broker chat perfectly. It cannot answer whether the person who wrote "ok fine, noted" was
empowered to bind the company to a contract variation, because that fact is not in the document.

**Cost.** Every amendment reaches a human, forever. At Harbourline's volume, roughly 5 items per
month at ~30 minutes each. Small in hours; the point is that no amount of model improvement
reduces it.

**Local workaround.** Hard-coded routing to the contracts desk, and a documented decision that it
never auto-clears.

**Proposed.** An `Authority` model: person → entity → what they may bind → up to what value → in
what form. Populated at deployment from the customer's signing policy, which they already have as
a PDF for their auditors. Then SHP-02 becomes a lookup with a real answer rather than a permanent
escalation.

**The general claim, and the one I would most like challenged.** On this workflow, the ceiling on
automation is not extraction accuracy. Extraction on these documents is close to solved — the
weakest field in the set is 0.86 and it is a multi-row analytical table. The ceiling is that
several of the most valuable decisions turn on *who was allowed to say what*, and authority is
customer master data that exists almost nowhere in structured form. Pushing extraction from 0.94
to 0.97 moves the queue barely at all. Modelling authority once closes a whole class.

If that is right, it has roadmap consequences well beyond this customer.

---

## 3. Analytical tables need list-valued fields with a contractual reduction — P2

**What happened.** The contract computes oil content as the average of three determinations. One
determination (18.40%) sits below the contractual minimum (18.50%) while the average (18.70%)
conforms. Extracting oil content as a scalar forces the extractor to pick a number at extraction
time, without the contract in view. Pick the worst and you reject a conforming panamax cargo
worth USD 27m.

**Cost.** One false rejection of a conforming cargo. Direct cost is the arbitration; the real cost
is the counterparty relationship.

**Local workaround.** Modelled `oil_content_determinations` as a list; the reduction (`average` vs
`worst`) is read from the contract and applied in the rule. Guarded by eval case
`oil_single_determination_low_average_conforms`.

**Proposed.** First-class support for list-valued extracted fields with a contract-driven
reduction, and extraction confidence reported per element. This shape recurs everywhere in
commodities: multiple determinations, multi-hold sampling, composite draft surveys, tank-by-tank
analysis on liquids.

---

## 4. Confidence should propagate through derived values — P2

**What happened.** `oil_content_determinations` extracts at 0.86. It feeds both a quality verdict
and a USD 89,118.75 financial claim. I gate both, and I report `confirmed recoverable` separately
from `pending review` so nobody quotes an unverified number to a counterparty. That separation is
the single most useful thing in the report and I had to build it by hand.

**Cost.** Without it, a blended "USD 184k recoverable" headline lets a 0.86 extraction underwrite
a claim letter.

**Local workaround.** Manual `inputs` declaration on every rule; the engine takes the minimum. It
works and it is fragile — it depends on every rule author listing their inputs honestly.

**Proposed.** Confidence propagates automatically through the derivation graph. Any computed value
carries the minimum confidence of its ancestors, without the rule author declaring anything.
Reporting surfaces should refuse to sum values at different confidence tiers into one figure.

---

## 5. Chat is evidence, not a record — P3

**What happened.** The amendment, the seller's acknowledgement of both adjustments, and the
sailing notice all lived in WhatsApp and nowhere else. Ingesting chat is genuinely differentiating
— none of it exists in email. But treating a chat message as a system-of-record input would let an
emoji reaction move USD 27m.

**Local workaround.** Policy: chat fields never write to NetSuite. They populate review queues as
evidence, with the source span quoted.

**Proposed.** Formalise the distinction in the platform: sources carry an `admissibility` property
(`system_of_record` / `evidence_only`). Rules declare what they accept. Attempting to write an
`evidence_only` value to an integration target fails loudly at config time rather than at runtime.

This turns a policy I wrote in a markdown file into something the platform enforces, and it is the
difference between a convention and a control.

---

## Prioritisation, if it were mine

1. **Authority model** (#2) — closes the highest-value permanently-manual class
2. **Deadlines on exceptions** (#1) — cheapest large downside to remove
3. **Confidence propagation** (#4) — foundational; the others get simpler once it exists
4. **List-valued fields** (#3) — recurs on every liquid and multi-hold cargo
5. **Source admissibility** (#5) — makes a policy into a control

#1 and #3 are contained. #2 and #4 are architectural and I would want to be argued out of them
before anyone builds anything.

## What I would want to know before building any of it

- How many deployed customers hit the authority problem? I have one data point and a theory.
- Does the extraction layer already carry per-element confidence internally, and is it just not
  surfaced? #4 is a much smaller change if so.
- Is `evidence_only` a real distinction across the customer base, or a Harbourline artefact of
  brokers who work over WhatsApp?
