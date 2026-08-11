# 02 — Data model and field mappings

Source documents → canonical shipment record → NetSuite.

The canonical record is the contract between extraction and rules. Rules never read a
document; they read canonical fields. That way a new document layout, a new origin, or a
new superintendent changes the extraction prompt and nothing else.

Implemented in [`src/schema.py`](../src/schema.py); the populated instance for SHP-4471 is
[`data/fixtures/SHP-4471.json`](../data/fixtures/SHP-4471.json).

---

## Field envelope

Every field carries five attributes, not one:

```json
"moisture_pct": {
  "value": 14.35,
  "confidence": 0.99,
  "extractor": "model",
  "source_doc": "VMK-26-03318",
  "source_span": "Moisture  14.35 %"
}
```

`source_span` is not decoration. When a controller disputes a USD 95k exception, the first
question is "where does that number come from", and the answer has to be one click, not a
document hunt. It is also what makes the extraction auditable after the fact — GAFTA
arbitration will ask.

---

## Contract (PAE-2611)

| Canonical field | Type | Conf. | NetSuite target | Notes |
|---|---|---|---|---|
| `buyer` | string | 0.99 | Vendor Bill → Subsidiary | |
| `buyer_signatory` | string | 0.95 | *(none)* | Feeds SHP-02 authority check only |
| `seller` | string | 0.99 | Vendor | Match on vendor master, never create |
| `contract_form` | enum | 0.97 | Custom: `custbody_contract_form` | GAFTA 100 / FOSFA 54 / bespoke |
| `quantity_mt` | decimal(3) | 0.99 | PO → Quantity | |
| `quantity_tolerance_pct` | decimal(2) | 0.99 | Custom: `custbody_qty_tol_pct` | |
| `futures_settle_cents_per_bushel` | decimal(2) | 0.97 | Custom: `custbody_futures_settle` | |
| `bushels_per_mt` | decimal(4) | 0.96 | *(none)* | Commodity-specific. See PRC-03. |
| `basis_usd_per_mt` | decimal(2) | 0.98 | Custom: `custbody_basis` | |
| `unit_price_usd_per_mt` | decimal(2) | 0.98 | PO → Rate | Re-derived, never trusted |
| `incoterm` | enum | 0.99 | Custom: `custbody_incoterm` | |
| `shipment_window_start` / `_end` | date | 0.99 | Custom: `custbody_ship_window_*` | |
| `moisture_max_pct` | decimal(2) | 0.99 | *(spec table)* | |
| `moisture_allowance_ceiling_pct` | decimal(2) | 0.97 | *(spec table)* | Boundary between allowance and rejection right |
| `foreign_matter_max_pct` | decimal(2) | 0.99 | *(spec table)* | |
| `damaged_grains_max_pct` | decimal(2) | 0.99 | *(spec table)* | |
| `heat_damaged_max_pct` | decimal(2) | 0.98 | *(spec table)* | Subset of damaged grains |
| `oil_content_min_pct` | decimal(2) | 0.98 | *(spec table)* | Rejection threshold |
| `oil_content_basis_pct` | decimal(2) | 0.97 | *(spec table)* | Discount reference, ≠ minimum |
| `oil_content_basis_rule` | enum | 0.94 | *(spec table)* | `average_of_3_determinations` \| `worst_determination` |
| `oil_discount_usd_per_half_pct` | decimal(2) | 0.93 | *(spec table)* | |
| `protein_min_pct` | decimal(2) | 0.98 | *(spec table)* | |
| `weight_basis` | enum | 0.96 | Custom: `custbody_weight_basis` | `net_shipped_weight` \| `net_outturn_weight` |
| `payment_terms_days` | int | 0.99 | Vendor Bill → Terms | |
| `amendment_requires` | enum | 0.92 | *(none)* | Feeds SHP-02 |

**Note on `oil_content_min_pct` vs `oil_content_basis_pct`.** These are different numbers doing
different jobs: 18.50% is where the Buyer gains a rejection right; 19.00% is the reference the
price adjusts around. Collapsing them into one "oil spec" field — which is what the legacy
contract spreadsheet does — is what makes the discount get missed. Modelling them separately is
the single highest-value change in this mapping.

## Bill of lading (PNG-2026-0219)

| Canonical field | Type | Conf. | NetSuite target |
|---|---|---|---|
| `bl_number` | string | 0.99 | Item Receipt → `custbody_bl_no` |
| `bl_date` | date | 0.98 | Item Receipt → `custbody_bl_date` |
| `vessel` | string | 0.99 | `custbody_vessel` |
| `net_weight_mt` | decimal(3) | 0.99 | Item Receipt → Quantity |
| `consignee` | string | 0.93 | *(review only)* |
| `shipper` | string | 0.98 | *(match to vendor)* |
| `port_of_loading` / `_discharge` | string | 0.99 | `custbody_pol` / `custbody_pod` |

## Certificate of quality (VMK-26-03318)

| Canonical field | Type | Conf. | NetSuite target |
|---|---|---|---|
| `moisture_pct` | decimal(2) | 0.99 | `custbody_qc_moisture` |
| `foreign_matter_pct` | decimal(2) | 0.97 | `custbody_qc_fm` |
| `damaged_grains_pct` | decimal(2) | 0.97 | `custbody_qc_damaged` |
| `heat_damaged_pct` | decimal(2) | 0.96 | `custbody_qc_heat` |
| `oil_content_determinations` | list[decimal(2)] | **0.86** | `custbody_qc_oil_avg` (derived) |
| `protein_pct` | decimal(2) | 0.97 | `custbody_qc_protein` |
| `sampling_date` / `sampling_place` | date / string | 0.98 | `custbody_qc_*` |

`oil_content_determinations` is a **list**, and that is deliberate. The contract computes oil
content as the average of three determinations. A scalar field forces the extractor to decide
which number matters, at extraction time, without the contract in view. That is how a
conforming cargo gets rejected on its worst sample — see eval case
`oil_single_determination_low_average_conforms`.

It is also the lowest-confidence field in the set (0.86) because multi-row analytical tables
are genuinely harder to read than a labelled scalar. Both quality and financial rules that
depend on it are gated accordingly.

## Phytosanitary certificate (BR-PR-2026-118427)

| Canonical field | Type | Conf. | NetSuite target |
|---|---|---|---|
| `certificate_number` | string | 0.99 | `custbody_phyto_no` |
| `consignee` | string | 0.94 | *(review only)* |
| `bl_reference` | string | 0.97 | *(cross-check)* |
| `quantity_mt` | decimal(3) | 0.97 | *(cross-check)* |
| `issue_date` | date | 0.98 | `custbody_phyto_date` |

## Commercial invoice (PAE-INV-26-0412)

| Canonical field | Type | Conf. | NetSuite target |
|---|---|---|---|
| `invoice_number` | string | 0.99 | Vendor Bill → Reference No. |
| `invoice_date` | date | 0.99 | Vendor Bill → Date |
| `billed_to` | string | 0.99 | *(subsidiary check)* |
| `quantity_mt` | decimal(3) | 0.99 | Vendor Bill line → Quantity |
| `unit_price_usd_per_mt` | decimal(2) | 0.99 | Vendor Bill line → Rate |
| `line_amount_usd` | decimal(2) | 0.99 | Vendor Bill line → Amount |
| `total_usd` | decimal(2) | 0.99 | Vendor Bill → Total |
| `weight_basis_stated` | enum | 0.91 | *(review only)* |
| `allowance_line_count` | int | 0.95 | *(rule input)* |

## Broker chat (WA-PAE-2611)

| Canonical field | Type | Conf. | NetSuite target |
|---|---|---|---|
| `proposed_shipment_window_end` | date | 0.88 | *(never written)* |
| `amendment_requested_by` | string | 0.90 | *(never written)* |
| `amendment_acknowledged_by` | string | 0.89 | *(never written)* |
| `broker_confirmation_present` | bool | 0.72 | *(never written)* |
| `seller_allowance_commitment` | string | 0.87 | *(never written)* |

**Nothing extracted from chat writes to NetSuite.** Chat is admissible as *evidence for a human
review queue* and inadmissible as *a system of record input*. This is a deployment-time policy
decision, not a technical limitation, and it is the one worth arguing about — see
[03](03-rules-and-review-policy.md) and the memo in [06](06-product-feedback-memo.md).

---

## Write-back policy to NetSuite

| Condition | Action |
|---|---|
| All blocking rules PASS | Create Vendor Bill in *Pending Approval*. Never *Approved*. |
| Any blocking rule FAIL | No write. Exception queue only. |
| Any blocking rule NEEDS_REVIEW | No write. Review queue, with the withheld verdict shown. |
| ALLOWANCE only | Write with allowance lines itemised and flagged for AP confirmation |

The system never approves a bill. It gets a bill to the point where approving it is a
five-second decision instead of a thirty-five-minute reconstruction.
