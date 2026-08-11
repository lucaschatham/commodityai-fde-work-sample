# 05 — Go-live runbook

**Cutover window:** Monday, 06:00–10:00 CET, before Rotterdam discharge operations pick up.
**Deployment lead:** on site day 1, remote days 2–10, daily standing call at 09:00 CET for two weeks.
**Rollback authority:** ops lead or deployment lead, unilaterally, no approval chain.

---

## Phase 0 — T-5 days

| # | Step | Owner | Verify |
|---|---|---|---|
| 0.1 | Freeze rule catalogue; tag the release | Deployment lead | Tag matches UAT-signed config |
| 0.2 | Run full eval suite against the frozen tag | Deployment lead | 10/10 green, 56 assertions |
| 0.3 | Confirm NetSuite production credentials, write scope limited to draft bills | IT | Scope test: approval attempt fails |
| 0.4 | Confirm mailbox + WhatsApp export ingestion in production | IT | Test document lands end to end |
| 0.5 | Brief queue owners; confirm coverage for the two-week window | Ops lead | Named owner + named backup per queue |
| 0.6 | Publish the escalation path | Deployment lead | Pinned in the ops channel |

## Phase 1 — Cutover

| # | Step | Owner | Verify | Rollback |
|---|---|---|---|---|
| 1.1 | Snapshot current open shipments | Ops lead | Count recorded | — |
| 1.2 | Enable ingestion, **write-back disabled** | Deployment lead | Documents flowing | Disable ingestion |
| 1.3 | Process 5 open shipments in shadow | Deployment lead | Output vs. manual reconciliation | — |
| 1.4 | Ops lead reviews all 5 line by line | Ops lead | Written agreement on every exception | **Stop here if any disagreement** |
| 1.5 | Enable write-back to draft bills | IT | One draft bill created, unapproved | Disable write-back flag |
| 1.6 | Process the live queue | Ops | Queue items appearing with correct owners | Revert to manual |
| 1.7 | Declare go-live | Deployment lead | Announcement posted | — |

**Gate at 1.4 is hard.** If the ops lead disagrees with any of the five, cutover stops and the
disagreement is resolved as a configuration change. A cutover completed over an unresolved
objection produces a system nobody uses.

## Phase 2 — Parallel run, days 1–10

Every shipment is reconciled both ways. Manual result wins on any disagreement; every
disagreement becomes a golden case the same day.

| Day | Focus | Exit signal |
|---|---|---|
| 1–2 | Every exception reviewed jointly | No P1 defects |
| 3–5 | Ops leads review, deployment lead observes | Disagreement rate < 5% |
| 6–10 | Ops runs independently; spot checks only | Two consecutive days with zero P1/P2 |

**Parallel run does not end on a date. It ends on the exit signal.** If day 10 arrives without
two clean consecutive days, the parallel run extends and somebody's plan slips. That is the
correct outcome and it is agreed in advance so it is not a negotiation in the moment.

## Phase 3 — Steady state

| Cadence | Check | Threshold | Escalation |
|---|---|---|---|
| Daily | Queue age | Nothing > SLA | Ops lead |
| Daily | Rules that errored | 0 | Deployment lead |
| Weekly | Straight-through rate | ≥ 55%, trending up | Review config |
| Weekly | False-positive rate | ≤ 5% | Retune thresholds |
| Weekly | Master-data queue volume | Trending down | If flat, mappings are not being saved |
| Monthly | Financial recall audit, 10 shipments sampled | 100% | P1 |
| Monthly | Re-run eval suite against current config | 10/10 | Block further changes until green |
| Quarterly | Threshold recalibration | — | Ops lead re-signs |

**Watch the queue-volume trend more closely than the automation rate.** Master-data exceptions
are supposed to resolve permanently. A flat CPT-01 volume in week 4 means resolutions are not
being written back to counterparty master, which is a silent failure that looks like normal
operation.

## Rollback

**Triggers — any one is sufficient:**
- A payment released against an incorrect reconciliation
- Write-back created an approved bill
- Financial exception provably missed on a live shipment
- Queue exceeds 2× SLA for two consecutive days
- Ops lead loses confidence, for any reason they judge sufficient

**Procedure:** disable ingestion → disable write-back → void unapproved draft bills created that
day → notify queue owners → revert to manual with the shipment snapshot from 1.1 → post-incident
review within 48h. Target: under 15 minutes, and it is rehearsed in UAT rather than read for the
first time under pressure.

**No rollback requires engineering.** If it does, the deployment is not ready.

## Comms

| Audience | When | Channel |
|---|---|---|
| Trade ops team | T-2 days, go-live, daily for 10 days | Standing call + channel |
| Finance | Before write-back is enabled | Email, controller cc'd |
| Traders | Go-live day | Channel, one paragraph |
| Counterparties | Never | Nothing changes externally |

Counterparties are told nothing. Claims are lodged by named humans on Harbourline letterhead
exactly as before. A supplier discovering that an allowance claim was raised by an automated
reconciliation is a commercial problem nobody needs in week one.

## Day-1 known state

Carried into production knowingly, agreed at UAT sign-off:

1. **Claim time bars are not tracked.** Exceptions carry value and remedy, no expiry. Manual
   control: ops lead reviews open financial exceptions every Friday against contractual bars.
   See [`evals/RESULTS.md`](../evals/RESULTS.md).
2. **SHP-02 never auto-clears.** Every amendment reaches the contracts desk, including
   well-evidenced ones. Accepted.
3. **Quality certificate extraction runs at ~0.86 on multi-determination tables.** Downstream
   conclusions are gated. Expect roughly one review item per two shipments here.
4. **Phase 1 is purchase-side only.** Sales-side reconciliation is unchanged.
