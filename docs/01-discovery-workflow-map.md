# 01 — Discovery: as-is workflow map

**Customer (fictional):** Harbourline Commodities B.V., Rotterdam — grain & oilseed trader, ~55 staff, 9 in trade operations.
**Scope of this deployment:** inbound purchase reconciliation for bulk soyabeans and soyameal, Brazil/Argentina origin, CIF ARA discharge.
**Systems in scope:** Outlook, shared `TRADE-OPS` mailbox, WhatsApp (broker groups), SharePoint document store, NetSuite (AP + inventory).

> Everything in this repo is fabricated. No real company, cargo, counterparty or price is represented. Volumes and timings below are the kind of numbers a discovery session produces; they are stated as assumptions, not findings.

---

## The as-is process

One purchase shipment moves through seven hands over roughly six weeks.

| # | Step | Owner | Inputs | Today | Time |
|---|---|---|---|---|---|
| 1 | Trade capture | Trade support | Broker confirmation email | Rekeyed into NetSuite from the email body | 15 min |
| 2 | Contract filing | Trade support | Seller's contract PDF | Saved to SharePoint, key terms rekeyed into a contract spreadsheet | 20 min |
| 3 | Amendment tracking | Ops coordinator | WhatsApp, email, calls | **Not systematically captured.** Lives in the coordinator's head and chat history | — |
| 4 | Shipping docs receipt | Ops coordinator | B/L, phyto, certificate of origin | Checked visually against the contract spreadsheet | 25 min |
| 5 | Quality review | Ops coordinator + trader | Superintendent's certificate of quality | Specs compared by eye; allowances calculated in a personal Excel model | 30 min |
| 6 | Invoice reconciliation | AP clerk + ops | Seller invoice | Three-way match by eye against B/L and contract | 35 min |
| 7 | Payment release | Finance | All of the above | Released on ops sign-off | 10 min |

**~2h15 of touch time per shipment. ~40 inbound shipments/month → roughly 1.5 FTE.**

## Where the money actually leaks

Touch time is the visible cost. It is not the expensive one.

| Failure | Mechanism | Frequency (assumed) | Cost per event |
|---|---|---|---|
| Contractual allowance not claimed | Quality certificate arrives days after the invoice is approved; the allowance is never netted off | ~1 in 6 shipments | USD 50k–150k |
| Settled on shipped weight instead of outturn | Invoice is raised on the B/L figure and nobody holds payment for the draft survey | ~1 in 10 | 0.1–0.3% of cargo value |
| Late shipment not claimed | Extension agreed informally in chat; no one revisits whether it was ever binding | ~1 in 8 | Varies; forfeits a claim |
| Claim lodged after the contractual time bar | The exception was found but sat in a queue | rare, severe | Full value of the claim |
| Unit-conversion error in pricing | cents/bushel to USD/MT with the wrong factor | rare, severe | ~USD 30/MT |

On the single shipment modelled in this repo the first two alone are worth **USD 184,294.60**.

The pattern: **the errors that cost real money are the ones where documents disagree with each other days or weeks apart.** No individual step is hard. Holding all seven in your head across six weeks, forty times a month, is.

## Why this is the right first workflow

1. It is the densest disagreement surface in the business — contract, B/L, certificate and invoice all assert overlapping facts.
2. It has an unambiguous financial readout, so value is arguable in currency rather than in hours.
3. It is bounded. No integration beyond a NetSuite AP write is required to prove value.
4. It generalises. Soyameal, corn and wheat differ in spec fields and conversion factors, not in shape.

## Explicitly out of scope for phase 1

Laytime and demurrage, letters of credit, position/exposure reporting, sales-side reconciliation, freight invoice audit. Each is a phase-2 candidate; none is required to prove the first workflow.

---

## Reusable: the discovery question bank

The 22 questions that produced the map above. Sequenced so that a two-hour session with a trade ops lead yields a configurable spec.

**Trade shape**
1. Which commodities, origins and discharge ranges are in scope?
2. Buy side, sell side, or both? Where does the pain concentrate?
3. Which standard-form contract governs — GAFTA, FOSFA, FCC, ICE/CME, bespoke?
4. What is the priced basis: flat, futures + differential, formula? Which exchange and month?
5. What conversion factors are in use, and where are they written down?

**Documents**
6. List every document that must exist before payment releases.
7. Which arrive before the invoice, and which after?
8. Which arrive by email, portal, courier, chat?
9. Who is the issuing authority for each, and do you trust all issuers equally?
10. Show me the three ugliest examples you have received this year.

**Terms that trigger money movement**
11. What quantity tolerance applies, and at whose option?
12. Which quality parameters carry allowances, discounts or rejection rights?
13. Is weight final at load or at discharge? Who certifies?
14. What are the payment terms, and what starts the clock?
15. What time bars apply to claims?

**Exceptions and authority**
16. Walk me through the last shipment that went wrong.
17. Who is allowed to accept a deviation, and up to what value?
18. Who is allowed to amend a contract, and in what form?
19. Where do amendments actually get agreed today?
20. What happens to an exception nobody actions?

**Systems**
21. What is the system of record for a booked trade, and what does it need from us?
22. What must never be written automatically?

Questions 17–20 are the ones that change the configuration most and get asked least.
