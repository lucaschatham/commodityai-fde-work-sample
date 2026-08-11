# 04 — UAT plan and acceptance criteria

UAT exists to make go-live a non-event. It ends with a named person signing a page that says
what the system does, what it refuses to do, and what it will get wrong.

**Duration:** 10 business days.
**Sign-off:** Head of Trade Operations (process + thresholds), Financial Controller (write-back + payment controls), IT (access + audit).

---

## Entry criteria

- [ ] 30 historical shipments extracted and fixtured, spanning ≥3 origins and ≥2 commodities
- [ ] Rule catalogue configured against the customer's own contract forms
- [ ] Eval suite green on the golden set (`python evals/run_eval.py`)
- [ ] NetSuite sandbox connected, write-back limited to *Pending Approval*
- [ ] Review queues provisioned with named owners

## Acceptance criteria

Numeric targets are measured against the 30-shipment historical set, adjudicated by the ops lead.

| # | Criterion | Target | Measured by |
|---|---|---|---|
| A1 | Field extraction accuracy, contract + B/L + invoice | ≥ 98% of fields | Field-level diff vs. manual key |
| A2 | Field extraction accuracy, quality certificates | ≥ 95% of fields | As above; lower bar is deliberate, these are analytical tables |
| A3 | **Financial exceptions caught** | **100%** | Every known allowance/discount/basis error in the historical set is raised |
| A4 | False rejections of conforming cargo | **0** | No conforming shipment blocked by a quality rule |
| A5 | False-positive rate on financial exceptions | ≤ 5% | Raised exceptions adjudicated as non-issues |
| A6 | Straight-through rate (no human touch) | ≥ 55% | Shipments with zero queue items |
| A7 | Median touch time on exception shipments | ≤ 12 min | Timed observation, vs. 2h15 baseline |
| A8 | Every exception traceable to a source span | 100% | Spot check, 20 exceptions |
| A9 | No unauthorised write-back | 0 events | NetSuite audit log |
| A10 | Confidence thresholds agreed and recorded | signed | Threshold calibration session |

**A3 and A4 are the pair that matters.** A3 alone is trivially satisfiable by raising everything;
A4 alone by raising nothing. Held together they are the actual product. A6 is explicitly *not*
gated on a high number — a 55% straight-through rate with 100% financial recall beats 85%
straight-through with a miss, and the ops lead should be told that in those words.

## Test scripts

### T1 — Base reconciliation
Run SHP-4471 (or the customer equivalent). Confirm all sixteen rules evaluate, the exception
report is legible to someone who has not seen the tool, and each exception's source span
resolves to the right place in the right document.

**Pass:** 9 exceptions, 7 blocking, USD 95,175.85 confirmed + USD 89,118.75 pending.

### T2 — Conforming cargo
Run a fully conforming shipment. Confirm zero exceptions and a Vendor Bill drafted in *Pending
Approval*.

**Pass:** clear to pay, one bill drafted, nothing approved.

### T3 — Boundary walk
For each parameter with an allowance band, run the value just inside the spec, just inside the
allowance band, and just above the ceiling. Confirm PASS / ALLOWANCE / FAIL respectively, and
that the allowance arithmetic matches the ops lead's own spreadsheet **to the cent**.

**Pass:** three distinct outcomes per parameter, allowance figures agree exactly.

### T4 — False-rejection guard
Run the certificate where one determination is below the minimum but the average conforms.

**Pass:** PASS, with the reasoning shown. The ops lead should be asked to confirm this is the
commercially correct reading before sign-off, in writing.

### T5 — Degraded extraction
Run a deliberately poor scan. Confirm affected rules withhold rather than guess, the withheld
verdict is visible, and confirmed vs. pending money are reported separately.

**Pass:** no verdict asserted below threshold; totals segregated.

### T6 — Authority escalation
Run the late-shipment case with the chat amendment. Confirm SHP-02 routes to the contracts
desk and cannot be cleared from the ops queue.

**Pass:** routed correctly; no path to auto-clear. **Then run T6b**, the variant where the
signatory themselves acknowledged and the broker confirmed, and confirm it *still* routes. If
the ops lead disagrees with that, the disagreement is resolved before go-live and the decision
is recorded here, not discovered in production.

### T7 — Write-back controls
Attempt write-back with a blocking exception open.

**Pass:** refused, event logged.

### T8 — Threshold calibration
Re-run the golden set at 0.80 / 0.85 / 0.90 / 0.95. Present queue volume against misses at
each level. Ops lead selects.

**Pass:** a chosen number with a name attached to it.

## Exit criteria

- [ ] A1–A10 met or explicitly waived in writing
- [ ] All P1 defects closed, P2 defects scheduled with dates
- [ ] Known gaps reviewed and accepted — including claim time bars ([RESULTS](../evals/RESULTS.md))
- [ ] Review queue owners trained and named in the runbook
- [ ] Rollback rehearsed end to end
- [ ] Three sign-offs collected

## Defect triage

| Sev | Definition | Response |
|---|---|---|
| P1 | Money wrong, or a payment control bypassed | Stop UAT, fix, re-run full suite |
| P2 | Exception missed or falsely raised | Fix before go-live; add a golden case |
| P3 | Wrong or unclear explanatory text | Fix before go-live |
| P4 | Cosmetic | Backlog |

**Every P1 and P2 fix adds a case to the golden set before it is called closed.** A fix without
a case is a fix that comes back.
