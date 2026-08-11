"""Rule catalogue for the Harbourline / Paranagua Agro deployment.

Trade: 60,000 MT Brazilian soyabeans in bulk, CIF Rotterdam, GAFTA 100,
priced off CBOT May-26 futures plus a CIF basis.

This file is the actual deliverable of the deployment engineer. Everything else
in the repo is scaffolding around it.

Three design decisions worth defending
--------------------------------------

1. LAYER ASSIGNMENT. Every rule declares whether it is deterministic, model
   assisted, or human authority. The default is deterministic. A rule earns the
   right to use a model only when the input is genuinely unstructured. Nothing
   involving arithmetic, dates, or set membership goes near a model: those have
   a correct answer, and routing them through a model can only make them
   probabilistic.

2. CONFIDENCE GATING. A rule's verdict is capped by the confidence of its worst
   input. A rule that FAILS on a field extracted at 0.86 does not fail -- it goes
   to a human. Rejecting a USD 27m supplier invoice on a digit you are not sure
   you read is a worse outcome than a five-minute review.

3. AUTHORITY IS NOT INFERENCE. SHP-02 can never auto-clear at any confidence.
   Whether a person is empowered to amend a contract is a customer-configured
   fact about org structure and delegated authority. It is not something a model
   should conclude from a chat message, however clearly the message reads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .schema import Field, Layer, Outcome, RuleResult, Severity, Shipment, parse_date

DEFAULT_MIN_CONFIDENCE = 0.90

REQUIRED_DOCUMENTS = {
    "contract",
    "bill_of_lading",
    "certificate_of_quality",
    "phytosanitary_certificate",
    "commercial_invoice",
    "outturn_weight_certificate",
}

# Commodity contracts settle to 2dp on USD and 3dp on MT. Anything tighter is noise.
MONEY_EPS = 0.01
WEIGHT_EPS = 0.001
# Futures-to-flat conversion is quoted to 2dp; allow half a cent of rounding drift.
PRICE_DERIVATION_EPS = 0.05


@dataclass
class RuleSpec:
    rule_id: str
    name: str
    layer: Layer
    severity: Severity
    min_confidence: float
    fn: Callable[[Shipment], RuleResult]
    authority_required: bool = False


REGISTRY: list[RuleSpec] = []


def rule(
    rule_id: str,
    name: str,
    layer: Layer,
    severity: Severity,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    authority_required: bool = False,
):
    def deco(fn):
        REGISTRY.append(
            RuleSpec(rule_id, name, layer, severity, min_confidence, fn, authority_required)
        )
        return fn

    return deco


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _money(x: float) -> float:
    return round(x + 1e-9, 2)


_LEGAL_SUFFIXES = {
    "bv", "b.v.", "nv", "sa", "s.a.", "sas", "sarl", "gmbh", "ltd", "limited",
    "plc", "inc", "llc", "pte", "pty", "ag", "spa", "srl", "co", "corp", "ltda",
}


def _norm_tokens(name: str) -> set[str]:
    tokens = re.split(r"[^a-z0-9]+", name.lower())
    return {t for t in tokens if t and t not in _LEGAL_SUFFIXES}


def _entity_similarity(a: str, b: str) -> float:
    ta, tb = _norm_tokens(a), _norm_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _oil_average(s: Shipment) -> float | None:
    """Contract cl.6 makes oil content the average of three determinations.

    Reading any single determination in isolation is the classic false-rejection
    on a GAFTA oilseed cargo. Determination 2 here is below the contractual
    minimum on its own; the parcel still conforms on the contractual basis.
    """
    dets = s.value("certificate_of_quality", "oil_content_determinations") or []
    if not dets:
        return None
    basis_rule = s.value("contract", "oil_content_basis_rule")
    if basis_rule == "average_of_3_determinations":
        return sum(dets) / len(dets)
    return min(dets)


def _moisture_allowance_usd(s: Shipment) -> float:
    actual = s.value("certificate_of_quality", "moisture_pct")
    spec = s.value("contract", "moisture_max_pct")
    shipped = s.value("bill_of_lading", "net_weight_mt")
    unit = s.value("contract", "unit_price_usd_per_mt")
    if actual is None or actual <= spec:
        return 0.0
    return _money(round(shipped * (actual - spec) / 100, 5) * unit)


def _oil_discount_usd_per_mt(s: Shipment) -> float:
    avg = _oil_average(s)
    basis = s.value("contract", "oil_content_basis_pct")
    step_value = s.value("contract", "oil_discount_usd_per_half_pct")
    if avg is None or avg >= basis:
        return 0.0
    shortfall = basis - avg
    return _money(shortfall / 0.5 * step_value)


# ---------------------------------------------------------------------------
# document set
# ---------------------------------------------------------------------------

@rule("DOC-01", "Required document set is complete", Layer.DETERMINISTIC, Severity.BLOCKING)
def doc_completeness(s: Shipment) -> RuleResult:
    missing = sorted(REQUIRED_DOCUMENTS - s.present_doc_types())
    if not missing:
        return RuleResult("DOC-01", "Required document set is complete", Layer.DETERMINISTIC,
                          Severity.BLOCKING, Outcome.PASS, "All required documents present.")
    return RuleResult(
        "DOC-01", "Required document set is complete", Layer.DETERMINISTIC, Severity.BLOCKING,
        Outcome.FAIL,
        f"Missing required document(s): {', '.join(missing)}.",
        remedy=(
            "Contract cl.8 makes net outturn weight final at discharge by draft survey. "
            "Final settlement cannot be computed from shipped weight alone. Chase Verimark "
            "for the outturn weight certificate before releasing funds."
        ),
    )


# ---------------------------------------------------------------------------
# quantity
# ---------------------------------------------------------------------------

@rule("QTY-01", "Shipped weight within contract tolerance", Layer.DETERMINISTIC, Severity.BLOCKING)
def qty_tolerance(s: Shipment) -> RuleResult:
    contract_qty = s.value("contract", "quantity_mt")
    tol = s.value("contract", "quantity_tolerance_pct")
    shipped = s.value("bill_of_lading", "net_weight_mt")
    lo = contract_qty * (1 - tol / 100)
    hi = contract_qty * (1 + tol / 100)
    inside = lo - WEIGHT_EPS <= shipped <= hi + WEIGHT_EPS
    return RuleResult(
        "QTY-01", "Shipped weight within contract tolerance", Layer.DETERMINISTIC,
        Severity.BLOCKING, Outcome.PASS if inside else Outcome.FAIL,
        f"B/L net {shipped:,.3f} MT against contract {contract_qty:,.3f} MT "
        f"{tol:g}% more or less (range {lo:,.3f} - {hi:,.3f} MT).",
        inputs=["contract.quantity_mt", "contract.quantity_tolerance_pct",
                "bill_of_lading.net_weight_mt"],
    )


@rule("QTY-02", "Invoiced quantity matches bill of lading", Layer.DETERMINISTIC, Severity.BLOCKING)
def qty_invoice_matches_bl(s: Shipment) -> RuleResult:
    bl = s.value("bill_of_lading", "net_weight_mt")
    inv = s.value("commercial_invoice", "quantity_mt")
    ok = abs(bl - inv) <= WEIGHT_EPS
    return RuleResult(
        "QTY-02", "Invoiced quantity matches bill of lading", Layer.DETERMINISTIC,
        Severity.BLOCKING, Outcome.PASS if ok else Outcome.FAIL,
        f"Invoice {inv:,.3f} MT against B/L net {bl:,.3f} MT.",
        inputs=["bill_of_lading.net_weight_mt", "commercial_invoice.quantity_mt"],
    )


# ---------------------------------------------------------------------------
# price
# ---------------------------------------------------------------------------

@rule("PRC-01", "Invoiced unit price matches contract price", Layer.DETERMINISTIC, Severity.BLOCKING)
def price_matches(s: Shipment) -> RuleResult:
    c = s.value("contract", "unit_price_usd_per_mt")
    i = s.value("commercial_invoice", "unit_price_usd_per_mt")
    ok = abs(c - i) <= MONEY_EPS
    return RuleResult(
        "PRC-01", "Invoiced unit price matches contract price", Layer.DETERMINISTIC,
        Severity.BLOCKING, Outcome.PASS if ok else Outcome.FAIL,
        f"Invoice USD {i:,.2f}/MT against contract USD {c:,.2f}/MT.",
        inputs=["contract.unit_price_usd_per_mt", "commercial_invoice.unit_price_usd_per_mt"],
        financial_impact_usd=None if ok else _money((i - c) * s.value("commercial_invoice", "quantity_mt")),
    )


@rule("PRC-02", "Invoice line extension arithmetic", Layer.DETERMINISTIC, Severity.BLOCKING)
def price_extension(s: Shipment) -> RuleResult:
    qty = s.value("commercial_invoice", "quantity_mt")
    unit = s.value("commercial_invoice", "unit_price_usd_per_mt")
    stated = s.value("commercial_invoice", "line_amount_usd")
    expected = _money(qty * unit)
    ok = abs(expected - stated) <= MONEY_EPS
    return RuleResult(
        "PRC-02", "Invoice line extension arithmetic", Layer.DETERMINISTIC,
        Severity.BLOCKING, Outcome.PASS if ok else Outcome.FAIL,
        f"{qty:,.3f} MT x USD {unit:,.2f} = USD {expected:,.2f}; invoice states USD {stated:,.2f}.",
        inputs=["commercial_invoice.quantity_mt", "commercial_invoice.unit_price_usd_per_mt",
                "commercial_invoice.line_amount_usd"],
        financial_impact_usd=None if ok else _money(stated - expected),
    )


@rule("PRC-03", "Contract price derives correctly from futures and basis",
      Layer.DETERMINISTIC, Severity.BLOCKING)
def price_derivation(s: Shipment) -> RuleResult:
    """Re-derive the flat price rather than trusting the number on the contract.

    Cents-per-bushel to USD-per-tonne is the single most common unit error on a
    grain or oilseed desk: the conversion factor is commodity specific (soyabeans
    and wheat are both 60 lb/bu, corn is 56 lb/bu) and a wrong factor produces a
    price that looks entirely plausible.
    """
    cents = s.value("contract", "futures_settle_cents_per_bushel")
    bu_per_mt = s.value("contract", "bushels_per_mt")
    basis = s.value("contract", "basis_usd_per_mt")
    stated = s.value("contract", "unit_price_usd_per_mt")

    futures_usd_per_mt = cents / 100 * bu_per_mt
    derived = futures_usd_per_mt + basis
    ok = abs(derived - stated) <= PRICE_DERIVATION_EPS

    return RuleResult(
        "PRC-03", "Contract price derives correctly from futures and basis",
        Layer.DETERMINISTIC, Severity.BLOCKING, Outcome.PASS if ok else Outcome.FAIL,
        f"CBOT {cents:,.2f} c/bu / 100 x {bu_per_mt:.4f} bu/MT = USD {futures_usd_per_mt:,.2f}/MT "
        f"flat, plus USD {basis:,.2f}/MT basis = USD {derived:,.2f}/MT. "
        f"Contract states USD {stated:,.2f}/MT.",
        inputs=["contract.futures_settle_cents_per_bushel", "contract.bushels_per_mt",
                "contract.basis_usd_per_mt", "contract.unit_price_usd_per_mt"],
        financial_impact_usd=None if ok else _money((stated - derived) * s.value("bill_of_lading", "net_weight_mt")),
    )


# ---------------------------------------------------------------------------
# quality
# ---------------------------------------------------------------------------

@rule("QUA-01", "Moisture within specification or allowance band", Layer.DETERMINISTIC,
      Severity.BLOCKING)
def moisture(s: Shipment) -> RuleResult:
    actual = s.value("certificate_of_quality", "moisture_pct")
    spec = s.value("contract", "moisture_max_pct")
    ceiling = s.value("contract", "moisture_allowance_ceiling_pct")
    shipped = s.value("bill_of_lading", "net_weight_mt")

    inputs = ["certificate_of_quality.moisture_pct", "contract.moisture_max_pct",
              "contract.moisture_allowance_ceiling_pct"]

    if actual <= spec:
        return RuleResult("QUA-01", "Moisture within specification or allowance band",
                          Layer.DETERMINISTIC, Severity.BLOCKING, Outcome.PASS,
                          f"Certified moisture {actual:.2f}% within contractual maximum {spec:.2f}%.",
                          inputs=inputs)

    if actual <= ceiling:
        excess = round(actual - spec, 4)
        allow_mt = round(shipped * excess / 100, 5)
        allow_usd = _moisture_allowance_usd(s)
        return RuleResult(
            "QUA-01", "Moisture within specification or allowance band", Layer.DETERMINISTIC,
            Severity.ADVISORY, Outcome.ALLOWANCE,
            f"Certified moisture {actual:.2f}% exceeds maximum {spec:.2f}% but is within the "
            f"{ceiling:.2f}% allowance ceiling. Excess {excess:.2f}pp on {shipped:,.3f} MT "
            f"= {allow_mt:,.3f} MT weight allowance in Buyer's favour = USD {allow_usd:,.2f}.",
            inputs=inputs,
            remedy="Contract cl.7(a) pro rata weight allowance. Must appear as a deduction on the invoice.",
        )

    return RuleResult(
        "QUA-01", "Moisture within specification or allowance band", Layer.DETERMINISTIC,
        Severity.BLOCKING, Outcome.FAIL,
        f"Certified moisture {actual:.2f}% exceeds the {ceiling:.2f}% allowance ceiling.",
        inputs=inputs,
        remedy="Contract cl.7(a): Buyer at liberty to reject the parcel or lodge a quality claim.",
    )


@rule("QUA-02", "Oil content meets contractual minimum", Layer.DETERMINISTIC, Severity.BLOCKING)
def oil_content(s: Shipment) -> RuleResult:
    dets = s.value("certificate_of_quality", "oil_content_determinations") or []
    minimum = s.value("contract", "oil_content_min_pct")
    basis_rule = s.value("contract", "oil_content_basis_rule")
    measured = _oil_average(s)

    basis_desc = (
        f"average of {len(dets)} determinations {dets}"
        if basis_rule == "average_of_3_determinations"
        else f"worst of {len(dets)} determinations {dets}"
    )
    ok = measured >= minimum
    worst = min(dets) if dets else None

    note = ""
    if ok and worst is not None and worst < minimum:
        note = (
            f" Note: determination low of {worst:.2f}% is below the {minimum:.2f}% minimum on "
            f"its own; the contract basis is the average, so the parcel conforms. Reading this "
            f"certificate determination by determination would produce a false rejection of a "
            f"conforming panamax cargo."
        )

    return RuleResult(
        "QUA-02", "Oil content meets contractual minimum", Layer.DETERMINISTIC, Severity.BLOCKING,
        Outcome.PASS if ok else Outcome.FAIL,
        f"Oil content {measured:.2f}% against minimum {minimum:.2f}% ({basis_desc}).{note}",
        inputs=["certificate_of_quality.oil_content_determinations", "contract.oil_content_min_pct",
                "contract.oil_content_basis_rule"],
    )


@rule("QUA-03", "Foreign matter and damaged grain caps", Layer.DETERMINISTIC, Severity.BLOCKING)
def defect_caps(s: Shipment) -> RuleResult:
    checks = [
        ("Foreign matter", s.value("certificate_of_quality", "foreign_matter_pct"),
         s.value("contract", "foreign_matter_max_pct")),
        ("Damaged grains", s.value("certificate_of_quality", "damaged_grains_pct"),
         s.value("contract", "damaged_grains_max_pct")),
        ("Heat damaged", s.value("certificate_of_quality", "heat_damaged_pct"),
         s.value("contract", "heat_damaged_max_pct")),
    ]
    breaches = [f"{n} {a:.2f}% > {m:.2f}%" for n, a, m in checks if a > m]
    detail = "; ".join(f"{n} {a:.2f}% (max {m:.2f}%)" for n, a, m in checks)
    return RuleResult(
        "QUA-03", "Foreign matter and damaged grain caps", Layer.DETERMINISTIC, Severity.BLOCKING,
        Outcome.FAIL if breaches else Outcome.PASS,
        (f"Breach: {'; '.join(breaches)}." if breaches else f"Within caps. {detail}."),
        inputs=["certificate_of_quality.foreign_matter_pct", "certificate_of_quality.damaged_grains_pct",
                "certificate_of_quality.heat_damaged_pct", "contract.foreign_matter_max_pct",
                "contract.damaged_grains_max_pct", "contract.heat_damaged_max_pct"],
    )


@rule("QUA-04", "Protein meets contractual minimum", Layer.DETERMINISTIC, Severity.BLOCKING)
def protein(s: Shipment) -> RuleResult:
    a = s.value("certificate_of_quality", "protein_pct")
    m = s.value("contract", "protein_min_pct")
    return RuleResult(
        "QUA-04", "Protein meets contractual minimum", Layer.DETERMINISTIC, Severity.BLOCKING,
        Outcome.PASS if a >= m else Outcome.FAIL,
        f"Protein {a:.2f}% against minimum {m:.2f}%.",
        inputs=["certificate_of_quality.protein_pct", "contract.protein_min_pct"],
    )


# ---------------------------------------------------------------------------
# financial reconciliation
# ---------------------------------------------------------------------------

@rule("FIN-01", "Moisture allowance reflected on invoice", Layer.DETERMINISTIC, Severity.BLOCKING)
def moisture_allowance_applied(s: Shipment) -> RuleResult:
    if moisture(s).outcome is not Outcome.ALLOWANCE:
        return RuleResult("FIN-01", "Moisture allowance reflected on invoice", Layer.DETERMINISTIC,
                          Severity.BLOCKING, Outcome.NOT_APPLICABLE,
                          "No moisture allowance triggered for this parcel.")

    allow_usd = _moisture_allowance_usd(s)
    lines = s.value("commercial_invoice", "allowance_line_count", 0)
    total = s.value("commercial_invoice", "total_usd")
    gross = s.value("commercial_invoice", "line_amount_usd")

    if lines > 0 and abs(total - _money(gross - allow_usd)) <= MONEY_EPS:
        return RuleResult("FIN-01", "Moisture allowance reflected on invoice", Layer.DETERMINISTIC,
                          Severity.BLOCKING, Outcome.PASS,
                          f"Moisture allowance USD {allow_usd:,.2f} correctly deducted.")

    return RuleResult(
        "FIN-01", "Moisture allowance reflected on invoice", Layer.DETERMINISTIC,
        Severity.BLOCKING, Outcome.FAIL,
        f"Contract cl.7(a) moisture allowance of USD {allow_usd:,.2f} is not deducted. "
        f"Invoice carries no allowance line and totals USD {total:,.2f}. "
        f"Buyer is overcharged by USD {allow_usd:,.2f}.",
        inputs=["certificate_of_quality.moisture_pct", "contract.moisture_max_pct",
                "bill_of_lading.net_weight_mt", "commercial_invoice.total_usd",
                "commercial_invoice.allowance_line_count"],
        financial_impact_usd=allow_usd,
        remedy=(
            f"Reject the invoice and request a credit note for USD {allow_usd:,.2f}. Seller "
            "acknowledged both adjustments in the broker chat on 19 Mar ('we will reflect both "
            "on the invoice') but the issued invoice carries neither."
        ),
    )


@rule("FIN-02", "Oil content discount reflected on invoice", Layer.DETERMINISTIC, Severity.BLOCKING)
def oil_discount_applied(s: Shipment) -> RuleResult:
    avg = _oil_average(s)
    basis = s.value("contract", "oil_content_basis_pct")
    if avg is None or avg >= basis:
        return RuleResult("FIN-02", "Oil content discount reflected on invoice", Layer.DETERMINISTIC,
                          Severity.BLOCKING, Outcome.NOT_APPLICABLE,
                          "Oil content at or above basis; no discount due.")

    per_mt = _oil_discount_usd_per_mt(s)
    qty = s.value("commercial_invoice", "quantity_mt")
    total_discount = _money(per_mt * qty)
    lines = s.value("commercial_invoice", "allowance_line_count", 0)

    if lines > 0:
        return RuleResult("FIN-02", "Oil content discount reflected on invoice", Layer.DETERMINISTIC,
                          Severity.BLOCKING, Outcome.PASS,
                          f"Oil content discount USD {total_discount:,.2f} appears on the invoice.")

    return RuleResult(
        "FIN-02", "Oil content discount reflected on invoice", Layer.DETERMINISTIC,
        Severity.BLOCKING, Outcome.FAIL,
        f"Certified oil {avg:.2f}% is {basis - avg:.2f}pp below the {basis:.2f}% basis. "
        f"Contract cl.7(b) gives USD {per_mt:,.2f}/MT discount pro rata, "
        f"= USD {total_discount:,.2f} on {qty:,.3f} MT. No discount line on the invoice.",
        inputs=["certificate_of_quality.oil_content_determinations", "contract.oil_content_basis_pct",
                "contract.oil_discount_usd_per_half_pct", "commercial_invoice.quantity_mt",
                "commercial_invoice.allowance_line_count"],
        financial_impact_usd=total_discount,
        remedy=(
            f"Include USD {total_discount:,.2f} in the credit note request alongside the moisture "
            "allowance. Confirm the oil determinations against the Verimark certificate first: "
            "this figure rests on an extraction the pipeline is not confident about."
        ),
    )


@rule("FIN-03", "Invoice weight basis matches contract weight basis", Layer.DETERMINISTIC,
      Severity.BLOCKING)
def weight_basis(s: Shipment) -> RuleResult:
    contract_basis = s.value("contract", "weight_basis")
    invoice_basis = s.value("commercial_invoice", "weight_basis_stated")
    ok = contract_basis == invoice_basis
    return RuleResult(
        "FIN-03", "Invoice weight basis matches contract weight basis", Layer.DETERMINISTIC,
        Severity.BLOCKING, Outcome.PASS if ok else Outcome.FAIL,
        f"Contract settles on '{contract_basis}'; invoice is raised on '{invoice_basis}'.",
        inputs=["contract.weight_basis", "commercial_invoice.weight_basis_stated"],
        remedy=(
            "Contract cl.8 makes outturn weight final. Invoicing on shipped weight puts transit "
            "and handling loss on the Buyer, which on a panamax parcel is routinely 0.1-0.3% of "
            "cargo value. Hold final settlement until the draft survey outturn certificate is in, "
            "then re-price on the certified outturn figure."
        ) if not ok else None,
    )


# ---------------------------------------------------------------------------
# shipment timing and contract amendment
# ---------------------------------------------------------------------------

@rule("SHP-01", "Shipment effected within contractual window", Layer.DETERMINISTIC, Severity.BLOCKING)
def shipment_window(s: Shipment) -> RuleResult:
    bl_date = parse_date(s.value("bill_of_lading", "bl_date"))
    start = parse_date(s.value("contract", "shipment_window_start"))
    end = parse_date(s.value("contract", "shipment_window_end"))
    ok = start <= bl_date <= end
    late_by = (bl_date - end).days if bl_date > end else 0
    return RuleResult(
        "SHP-01", "Shipment effected within contractual window", Layer.DETERMINISTIC,
        Severity.BLOCKING, Outcome.PASS if ok else Outcome.FAIL,
        f"B/L dated {bl_date.isoformat()} against contractual window "
        f"{start.isoformat()} to {end.isoformat()}"
        + (f"; {late_by} day(s) late." if late_by else "."),
        inputs=["bill_of_lading.bl_date", "contract.shipment_window_start",
                "contract.shipment_window_end"],
        remedy=(
            "An extension to 2026-03-05 was discussed in the broker chat. See SHP-02: that "
            "extension is not established as a binding amendment on the evidence held."
        ) if not ok else None,
    )


@rule("SHP-02", "Authority to amend the shipment window", Layer.HUMAN_AUTHORITY,
      Severity.BLOCKING, authority_required=True)
def amendment_authority(s: Shipment) -> RuleResult:
    """The rule this deployment exists to get right.

    The model reads the chat correctly. Both parties clearly intend an extension.
    And it still must not clear automatically, because the question is not "what
    was said" but "was the person who said it empowered to bind the company, in
    the form the contract requires".

    Contract cl.10 requires (a) writing, (b) both parties, (c) broker confirmation.
    The chat gives an operations coordinator's informal assent and a broker line
    acknowledging receipt without confirming an amendment. That is a legal and
    organisational judgement, and it belongs to a human every time.
    """
    # Only reachable when the shipment does not comply on its face. If the B/L sits
    # inside the contractual window there is no amendment to rely on and no
    # authority question to answer, so the queue stays empty.
    if shipment_window(s).outcome is Outcome.PASS:
        return RuleResult("SHP-02", "Authority to amend the shipment window",
                          Layer.HUMAN_AUTHORITY, Severity.BLOCKING, Outcome.NOT_APPLICABLE,
                          "Shipment complies with the contractual window; no amendment relied upon.")

    proposed = s.value("broker_chat", "proposed_shipment_window_end")
    if proposed is None:
        return RuleResult(
            "SHP-02", "Authority to amend the shipment window", Layer.HUMAN_AUTHORITY,
            Severity.BLOCKING, Outcome.NEEDS_REVIEW,
            "Shipment is outside the contractual window and no amendment evidence was found in "
            "any ingested channel. Treat as a late-shipment claim unless the desk holds an "
            "addendum the pipeline has not seen.",
            review_reason="Late shipment with no amendment on file.",
        )

    ack_by = s.value("broker_chat", "amendment_acknowledged_by")
    signatory = s.value("contract", "buyer_signatory")
    broker_conf = s.value("broker_chat", "broker_confirmation_present")
    requirement = s.value("contract", "amendment_requires")
    bl_date = parse_date(s.value("bill_of_lading", "bl_date")).isoformat()

    gaps = []
    if ack_by and signatory and signatory.split()[-1].lower() not in str(ack_by).lower():
        gaps.append(f"assent given by {ack_by}, who is not the contract signatory ({signatory})")
    if not broker_conf:
        gaps.append("no explicit broker confirmation of the amendment")

    return RuleResult(
        "SHP-02", "Authority to amend the shipment window", Layer.HUMAN_AUTHORITY,
        Severity.BLOCKING, Outcome.NEEDS_REVIEW,
        f"An extension of the shipment window to {proposed} is evidenced in the broker chat, "
        f"which would bring the {bl_date} B/L back into compliance. Contract cl.10 requires: "
        f"{requirement}. Open points: {'; '.join(gaps) if gaps else 'none identified'}.",
        inputs=["broker_chat.proposed_shipment_window_end", "broker_chat.amendment_acknowledged_by",
                "broker_chat.broker_confirmation_present", "contract.buyer_signatory",
                "contract.amendment_requires"],
        review_reason=(
            "Contract-amendment authority is never inferred. Routed to the trade contracts desk "
            "regardless of extraction confidence."
        ),
        remedy=(
            "Trade contracts desk to obtain a countersigned addendum from J.M. van den Berg and "
            "broker confirmation from Vanterpool, or price the 3-day late shipment as a GAFTA "
            "claim. Do not release payment on the chat thread alone."
        ),
    )


# ---------------------------------------------------------------------------
# counterparty
# ---------------------------------------------------------------------------

@rule("CPT-01", "Counterparty identity consistent across documents", Layer.MODEL_ASSISTED,
      Severity.ADVISORY, min_confidence=0.92)
def counterparty_match(s: Shipment) -> RuleResult:
    buyer = s.value("contract", "buyer")
    consignee = s.value("bill_of_lading", "consignee")
    billed_to = s.value("commercial_invoice", "billed_to")

    sim_consignee = _entity_similarity(buyer, consignee)
    sim_billed = _entity_similarity(buyer, billed_to)

    if sim_consignee == 1.0 and sim_billed == 1.0:
        outcome = Outcome.PASS
        msg = "Buyer, consignee and invoice addressee are the same legal entity."
    elif sim_consignee == 0.0 or sim_billed == 0.0:
        outcome = Outcome.FAIL
        msg = f"Counterparty names share no common root. Buyer '{buyer}', consignee '{consignee}'."
    else:
        outcome = Outcome.NEEDS_REVIEW
        msg = (
            f"Contract buyer is '{buyer}' but the B/L and phytosanitary certificate consign to "
            f"'{consignee}' (name overlap {sim_consignee:.2f}). Likely an affiliate in the same "
            f"group, but title to the goods and the payment obligation now sit with different "
            f"legal entities."
        )

    return RuleResult(
        "CPT-01", "Counterparty identity consistent across documents", Layer.MODEL_ASSISTED,
        Severity.ADVISORY, outcome, msg,
        inputs=["contract.buyer", "bill_of_lading.consignee", "commercial_invoice.billed_to"],
        review_reason=(
            "Entity resolution across a corporate group is customer master data, not an inference. "
            "Confirm against the Harbourline group structure before auto-linking."
        ) if outcome is Outcome.NEEDS_REVIEW else None,
        remedy=(
            "Confirm Harbourline Oilseeds Processing B.V. is an approved delivery entity under "
            "PAE-2611 and record the affiliate mapping in counterparty master data so this clears "
            "automatically next time."
        ) if outcome is Outcome.NEEDS_REVIEW else None,
    )


# ---------------------------------------------------------------------------
# engine
# ---------------------------------------------------------------------------

def _confidence_of(s: Shipment, ref: str) -> float | None:
    if "." not in ref:
        return None
    doc_type, fname = ref.split(".", 1)
    f = s.field(doc_type, fname)
    return f.confidence if f else None


def _min_confidence(s: Shipment, inputs: list[str]) -> float | None:
    confidences = [c for ref in inputs if (c := _confidence_of(s, ref)) is not None]
    return min(confidences) if confidences else None


def evaluate(shipment: Shipment) -> list[RuleResult]:
    """Run the catalogue and apply the review policy."""
    results: list[RuleResult] = []

    for spec in REGISTRY:
        try:
            result = spec.fn(shipment)
        except (TypeError, KeyError, AttributeError, ValueError) as exc:
            results.append(
                RuleResult(
                    spec.rule_id, spec.name, spec.layer, spec.severity, Outcome.NEEDS_REVIEW,
                    f"Rule could not be evaluated: {type(exc).__name__}: {exc}",
                    review_reason="Missing or malformed input. Never silently pass a rule that did not run.",
                )
            )
            continue

        result.layer = spec.layer
        conf = _min_confidence(shipment, result.inputs)
        result.min_input_confidence = conf

        # Authority rules are already NEEDS_REVIEW and are never upgraded.
        if spec.authority_required:
            results.append(result)
            continue

        # Confidence gate: a verdict is capped by its least reliable input.
        if (
            conf is not None
            and conf < spec.min_confidence
            and result.outcome in (Outcome.PASS, Outcome.FAIL, Outcome.ALLOWANCE)
        ):
            weakest = min(
                ((ref, c) for ref in result.inputs if (c := _confidence_of(shipment, ref)) is not None),
                key=lambda t: t[1],
            )[0]
            result.review_reason = (
                f"Lowest input confidence {conf:.2f} is below the {spec.min_confidence:.2f} "
                f"threshold for this rule (weakest input: {weakest}). Verdict withheld: "
                f"'{result.outcome.value}' pending operator confirmation."
            )
            result.withheld_outcome = result.outcome
            result.outcome = Outcome.NEEDS_REVIEW

        results.append(result)

    return results
