# 03 — Rules, layer assignment and human-review policy

The configuration decision that makes or breaks this deployment: **for each check, what decides — arithmetic, a model, or a person?**

Implemented in [`src/rules.py`](../src/rules.py). Sixteen rules, all executable.

---

## The three layers

| Layer | Decides | Used when | Failure mode if misassigned |
|---|---|---|---|
| **Deterministic** | Code | The input is structured and the answer is computable | None. This is the default. |
| **Model-assisted** | Model proposes, code verifies and bounds | The input is genuinely unstructured | Plausible wrong answers at scale |
| **Human authority** | A named person | The question is about authority, intent or liability | Silent, expensive, discovered late |

**The default is deterministic and a rule has to earn its way out.** Fourteen of sixteen rules
here never touch a model at decision time. A model extracts `14.35` from a certificate; whether
14.35 exceeds 14.00 is not a judgement call, and routing it through a model can only make a
correct answer probabilistic.

This is also a cost and latency argument, but that is not the main one. The main one is that
deterministic rules are **testable, explainable to a counterparty, and stable across model
versions.** When Harbourline lodges a USD 95k claim, the arithmetic has to survive being read
aloud by someone else's lawyer.

## The catalogue

| Rule | Check | Layer | Severity | Min conf |
|---|---|---|---|---|
| DOC-01 | Required document set complete | deterministic | blocking | — |
| QTY-01 | Shipped weight within contract tolerance | deterministic | blocking | 0.90 |
| QTY-02 | Invoiced quantity matches B/L | deterministic | blocking | 0.90 |
| PRC-01 | Invoiced unit price matches contract | deterministic | blocking | 0.90 |
| PRC-02 | Invoice line extension arithmetic | deterministic | blocking | 0.90 |
| PRC-03 | Price re-derives from futures + basis | deterministic | blocking | 0.90 |
| QUA-01 | Moisture within spec or allowance band | deterministic | blocking | 0.90 |
| QUA-02 | Oil content meets minimum (avg basis) | deterministic | blocking | 0.90 |
| QUA-03 | Foreign matter / damaged / heat caps | deterministic | blocking | 0.90 |
| QUA-04 | Protein minimum | deterministic | blocking | 0.90 |
| FIN-01 | Moisture allowance reflected on invoice | deterministic | blocking | 0.90 |
| FIN-02 | Oil discount reflected on invoice | deterministic | blocking | 0.90 |
| FIN-03 | Invoice weight basis matches contract | deterministic | blocking | 0.90 |
| SHP-01 | Shipment within contractual window | deterministic | blocking | 0.90 |
| SHP-02 | **Authority to amend the window** | **human authority** | blocking | n/a |
| CPT-01 | Counterparty identity across documents | model-assisted | advisory | 0.92 |

## Confidence gating

> A rule's verdict is capped by the confidence of its worst input.

Below threshold, the verdict is **withheld** rather than overridden: the rule's proposed answer
is preserved and shown to the reviewer as `withheld verdict: would have returned 'fail'`.

Two consequences worth stating plainly:

**A FAIL is gated as hard as a PASS.** Rejecting a USD 27m supplier invoice on a digit the
pipeline is not sure it read is worse than a five-minute human check. Most systems gate only
the passes, on the theory that a false alarm is cheap. On a trading desk a false alarm against
a counterparty is not cheap — it costs a relationship.

**Gating propagates.** `oil_content_determinations` extracts at 0.86. That single field gates
both QUA-02 (quality verdict) and FIN-02 (USD 89,118.75 discount claim). One hard-to-read
table on one certificate correctly quarantines every downstream conclusion, and the report
separates `confirmed recoverable` from `pending review` so nobody quotes an unverified figure
to a counterparty.

Thresholds are per-rule because tolerance for a wrong answer is per-rule. CPT-01 sits at 0.92
against a 0.90 default: entity mismatches are advisory, so a lower bar for review costs one
queue item and catches a real problem.

### Calibrating the numbers

The 0.90 default is a starting position, not a finding. It is calibrated during UAT
([04](04-uat-acceptance.md)) by running the golden set at 0.80 / 0.85 / 0.90 / 0.95 and having
the ops lead judge the resulting queue volume against the misses. **A threshold nobody
negotiated is a threshold nobody trusts.**

## Human authority: the rule that never auto-clears

SHP-02 is the only rule in the catalogue that cannot be satisfied by any amount of confidence.

The situation: the B/L is dated 3 March against a window closing 28 February. The cargo is
three days late and the contract is breached on its face. The broker chat contains a clear
extension request, an equally clear "ok fine, noted", and a broker acknowledgement.

Every part of that is extractable. The model reads it correctly. **And it still must not clear
the exception.** Contract cl.10 requires writing, both parties, and broker confirmation. What
the chat contains is an operations coordinator's informal assent and a broker line acknowledging
receipt. Whether Priya Raman holds delegated authority to bind Harbourline to a contract
variation is a fact about Harbourline's org chart and signing policy. It is not in the document,
so it is not inferable from the document.

Eval case `amendment_fully_authorised_still_reviewed` pins this: even when the acknowledgement
comes from the contract signatory *and* the broker confirms, SHP-02 routes to a human. That is
an accepted cost, recorded as such.

**The generalisation, and the thing worth arguing about with a customer:** the ceiling on
automating this workflow is not extraction accuracy. Extraction is close to solved on these
documents. The ceiling is that a contract amendment is a *speech act by an authorised party*,
and authority is customer master data that mostly does not exist in structured form anywhere.
Chase extraction accuracy from 0.94 to 0.97 and the queue barely moves. Model delegated
authority once and a whole class of exceptions closes.

## Review queues

| Queue | Owner | SLA | Feeds |
|---|---|---|---|
| **Financial exception** | Trade ops controller | 1 business day | FIN-01, FIN-02, FIN-03, PRC-* |
| **Quality** | Trader + ops coordinator | 1 business day | QUA-* |
| **Contract authority** | Trade contracts desk | 2 business days | SHP-02 |
| **Master data** | Trade support | 5 business days | CPT-01 |
| **Document chase** | Ops coordinator | 1 business day | DOC-01 |

Master data items resolve *permanently*: confirming Harbourline Oilseeds Processing B.V. as an
approved delivery affiliate closes CPT-01 for every future shipment on that lane. Queue volume
should decay over the first quarter. If it does not, the configuration is wrong, and that is
the metric to watch in week 4 rather than raw automation rate.

## What the system may never do

1. Approve a payment.
2. Write anything derived from a chat message into NetSuite.
3. Clear an authority question at any confidence level.
4. Create a vendor or counterparty record.
5. Silently pass a rule that errored. An unevaluated rule is `NEEDS_REVIEW`, never `PASS`.

Item 5 is enforced in the engine, not by convention — see the exception handler in
`rules.evaluate`. A rule that throws produces a review item naming the exception. The failure
this prevents is the expensive one: a rule quietly stops firing after a schema change and
nobody notices for a quarter because the queue got *shorter*.
