"""Three-way match orchestration: contract <-> shipping documents <-> invoice.

Run:
    python -m src.reconcile
    python -m src.reconcile --format markdown
"""

from __future__ import annotations

import argparse
import sys

from .extract import get_extractor
from .report import render_markdown, render_text
from .rules import evaluate
from .schema import ReconciliationReport, Shipment


def reconcile(shipment: Shipment) -> ReconciliationReport:
    return ReconciliationReport(
        shipment_id=shipment.shipment_id,
        contract_ref=shipment.contract_ref,
        results=evaluate(shipment),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Three-way match for a commodity shipment")
    ap.add_argument("--shipment", default="SHP-4471")
    ap.add_argument("--format", choices=["text", "markdown"], default="text")
    ap.add_argument("--live", action="store_true",
                    help="use the live extractor if ANTHROPIC_API_KEY is set")
    args = ap.parse_args(argv)

    shipment = get_extractor(prefer_live=args.live).load(args.shipment)
    report = reconcile(shipment)

    print(render_markdown(report) if args.format == "markdown" else render_text(report))

    # Exit non-zero when payment is blocked so this can sit in a pipeline.
    return 0 if report.clear_to_pay else 2


if __name__ == "__main__":
    sys.exit(main())
