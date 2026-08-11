"""Exception report rendering.

The report is written for the person who has to act on it: a trade ops
controller with forty shipments open and ten minutes. Ordering is therefore by
what stops the money, not by rule ID.
"""

from __future__ import annotations

from .schema import Layer, Outcome, ReconciliationReport, RuleResult

GLYPH = {
    Outcome.PASS: "PASS",
    Outcome.FAIL: "FAIL",
    Outcome.ALLOWANCE: "ALLOW",
    Outcome.NEEDS_REVIEW: "REVIEW",
    Outcome.NOT_APPLICABLE: "n/a",
}

LAYER_LABEL = {
    Layer.DETERMINISTIC: "deterministic",
    Layer.MODEL_ASSISTED: "model-assisted",
    Layer.HUMAN_AUTHORITY: "human-authority",
}

# Most disruptive first. A controller reads top down and stops when the money is safe.
PRIORITY = {
    Outcome.FAIL: 0,
    Outcome.NEEDS_REVIEW: 1,
    Outcome.ALLOWANCE: 2,
    Outcome.PASS: 3,
    Outcome.NOT_APPLICABLE: 4,
}


def _wrap(text: str, width: int = 88, indent: str = " " * 10) -> str:
    words, lines, current = text.split(), [], ""
    for w in words:
        if len(current) + len(w) + 1 > width:
            lines.append(current)
            current = w
        else:
            current = f"{current} {w}".strip()
    if current:
        lines.append(current)
    return f"\n{indent}".join(lines)


def render_text(report: ReconciliationReport) -> str:
    out: list[str] = []
    w = out.append

    w("=" * 100)
    w(f"  THREE-WAY MATCH EXCEPTION REPORT   shipment {report.shipment_id}   contract {report.contract_ref}")
    w("  Harbourline Commodities B.V.  |  60,000 MT Brazilian soyabeans  |  CIF Rotterdam  |  GAFTA 100")
    w("=" * 100)

    status = "CLEAR TO PAY" if report.clear_to_pay else "PAYMENT BLOCKED"
    w("")
    w(f"  STATUS                     {status}")
    w(f"  Rules evaluated            {len(report.results)}")
    w(f"  Exceptions                 {len(report.exceptions)}  ({len(report.blocking)} blocking)")
    w(f"  Confirmed recoverable      USD {report.confirmed_recoverable_usd:>14,.2f}")
    w(f"  Pending human review       USD {report.pending_review_usd:>14,.2f}")
    w(f"  Total exposure identified  USD {report.total_exposure_usd:>14,.2f}")
    w("")

    ordered = sorted(report.results, key=lambda r: (PRIORITY[r.outcome], r.rule_id))

    for r in ordered:
        conf = f"{r.min_input_confidence:.2f}" if r.min_input_confidence is not None else "  - "
        w("-" * 100)
        w(f"  {GLYPH[r.outcome]:<7} {r.rule_id}  {r.name}")
        w(f"          layer {LAYER_LABEL[r.layer]:<16} severity {r.severity.value:<9} min input conf {conf}")
        w(f"          {_wrap(r.message)}")
        if r.withheld_outcome is not None:
            w(f"          withheld verdict: would have returned '{r.withheld_outcome.value}'")
        if r.review_reason:
            w(f"          why review: {_wrap(r.review_reason, indent=' ' * 22)}")
        if r.financial_impact_usd:
            w(f"          financial impact: USD {r.financial_impact_usd:,.2f}")
        if r.remedy:
            w(f"          action: {_wrap(r.remedy, indent=' ' * 18)}")

    w("-" * 100)
    w("")
    w("  NEXT ACTIONS")
    for i, r in enumerate(
        sorted((x for x in report.exceptions if x.remedy), key=lambda r: PRIORITY[r.outcome]), 1
    ):
        w(f"    {i}. [{r.rule_id}] {_wrap(r.remedy, indent=' ' * 8)}")
    w("")
    w("=" * 100)
    return "\n".join(out)


def render_markdown(report: ReconciliationReport) -> str:
    rows = []
    for r in sorted(report.results, key=lambda r: (PRIORITY[r.outcome], r.rule_id)):
        conf = f"{r.min_input_confidence:.2f}" if r.min_input_confidence is not None else "-"
        impact = f"{r.financial_impact_usd:,.2f}" if r.financial_impact_usd else ""
        rows.append(
            f"| {r.rule_id} | {r.name} | {LAYER_LABEL[r.layer]} | "
            f"**{GLYPH[r.outcome]}** | {conf} | {impact} |"
        )

    status = "CLEAR TO PAY" if report.clear_to_pay else "PAYMENT BLOCKED"
    header = [
        f"# Three-way match exception report",
        "",
        f"**Shipment** {report.shipment_id} &nbsp;&nbsp; **Contract** {report.contract_ref} "
        f"&nbsp;&nbsp; **Status** {status}",
        "",
        f"- Rules evaluated: {len(report.results)}",
        f"- Exceptions: {len(report.exceptions)} ({len(report.blocking)} blocking)",
        f"- Confirmed recoverable: USD {report.confirmed_recoverable_usd:,.2f}",
        f"- Pending human review: USD {report.pending_review_usd:,.2f}",
        "",
        "| Rule | Check | Layer | Outcome | Min conf | Impact USD |",
        "|---|---|---|---|---|---|",
    ]
    return "\n".join(header + rows)
