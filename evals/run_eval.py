"""Eval harness for the Harbourline rule catalogue.

Why this exists
---------------
A rule catalogue is configuration, and configuration silently rots. Every time a
customer clarifies a term mid-deployment ("actually, oil is the average of three,
not the worst"), somebody edits a threshold, and nothing tells them what else
moved. This harness is the thing that tells them.

It is deliberately not a unit test suite. Unit tests assert that a function does
what its author intended. These cases assert that the catalogue produces the
commercially correct answer on document sets a trade ops controller would
recognise -- including the ones where the correct answer is "do not decide".

Two rules for keeping it honest:

  1. A conforming cargo must stay in the set (case 02). A catalogue that only
     knows how to raise exceptions gets muted by its users within a month.
  2. Known gaps are asserted, not omitted (case 10). A gap that is not written
     down becomes a surprise at go-live.

Run:
    python evals/run_eval.py
    python evals/run_eval.py --markdown > evals/RESULTS.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.extract import FixtureExtractor  # noqa: E402
from src.reconcile import reconcile  # noqa: E402
from src.rules import REGISTRY  # noqa: E402

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
BASE_SHIPMENT = "SHP-4471"
MONEY_EPS = 0.01


class CaseOutcome:
    def __init__(self, case_id: str, description: str) -> None:
        self.case_id = case_id
        self.description = description
        self.failures: list[str] = []
        self.checks = 0
        self.gap: dict | None = None

    @property
    def passed(self) -> bool:
        return not self.failures


def run_case(path: Path) -> CaseOutcome:
    spec = json.loads(path.read_text())
    out = CaseOutcome(spec["case_id"], spec["description"])

    shipment = FixtureExtractor().load_overlay(BASE_SHIPMENT, spec.get("overlay", {}))
    report = reconcile(shipment)
    by_id = {r.rule_id: r for r in report.results}

    for rule_id, expected in spec.get("expect", {}).items():
        out.checks += 1
        actual = by_id.get(rule_id)
        if actual is None:
            out.failures.append(f"{rule_id}: rule did not run")
        elif actual.outcome.value != expected:
            out.failures.append(
                f"{rule_id}: expected '{expected}', got '{actual.outcome.value}' "
                f"-- {actual.message[:110]}"
            )

    if "expect_clear_to_pay" in spec:
        out.checks += 1
        if report.clear_to_pay != spec["expect_clear_to_pay"]:
            out.failures.append(
                f"clear_to_pay: expected {spec['expect_clear_to_pay']}, got {report.clear_to_pay}"
            )

    for key, actual_value in (
        ("expect_confirmed_recoverable_usd", report.confirmed_recoverable_usd),
        ("expect_pending_review_usd", report.pending_review_usd),
    ):
        if key in spec:
            out.checks += 1
            if abs(spec[key] - actual_value) > MONEY_EPS:
                out.failures.append(
                    f"{key}: expected {spec[key]:,.2f}, got {actual_value:,.2f}"
                )

    gap = spec.get("known_gap")
    if gap:
        out.checks += 1
        prefix = gap["assert_no_rule_prefix"]
        covering = [s.rule_id for s in REGISTRY if s.rule_id.startswith(prefix)]
        if covering:
            out.failures.append(
                f"known gap '{gap['capability']}' is now covered by {covering}. "
                f"Close the gap entry instead of leaving a stale assertion."
            )
        else:
            out.gap = gap

    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args(argv)

    results = [run_case(p) for p in sorted(GOLDEN_DIR.glob("*.json"))]
    passed = sum(1 for r in results if r.passed)
    checks = sum(r.checks for r in results)
    gaps = [r for r in results if r.gap]

    if args.markdown:
        print(_markdown(results, passed, checks, gaps))
    else:
        print(_text(results, passed, checks, gaps))

    return 0 if passed == len(results) else 1


def _text(results, passed, checks, gaps) -> str:
    lines = ["", "=" * 92,
             "  RULE CATALOGUE EVAL   Harbourline / Paranagua Agro   contract PAE-2611",
             "=" * 92, ""]
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        noun = "assertion" if r.checks == 1 else "assertions"
        lines.append(f"  [{mark}]  {r.case_id}  ({r.checks} {noun})")
        for f in r.failures:
            lines.append(f"           -> {f}")
    lines += ["", "-" * 92,
              f"  {passed}/{len(results)} cases green across {checks} assertions.", ""]
    if gaps:
        lines.append("  KNOWN GAPS (asserted, not fixed)")
        for r in gaps:
            g = r.gap
            lines.append(f"    - {g['capability']}: no rule covers this. "
                         f"Exposure USD {g['exposure_usd']:,.2f}.")
            lines.append(f"      {g['note']}")
        lines.append("")
    lines.append("=" * 92)
    return "\n".join(lines)


def _markdown(results, passed, checks, gaps) -> str:
    lines = [
        "# Rule catalogue eval results",
        "",
        f"`{passed}/{len(results)}` cases green across `{checks}` assertions. "
        f"Generated by `python evals/run_eval.py --markdown`.",
        "",
        "| Case | Assertions | Result |",
        "|---|---|---|",
    ]
    for r in results:
        lines.append(f"| `{r.case_id}` | {r.checks} | {'PASS' if r.passed else 'FAIL'} |")
    lines += ["", "## What each case protects", ""]
    for r in results:
        lines.append(f"**`{r.case_id}`** — {r.description}")
        lines.append("")
    if gaps:
        lines += ["## Known gaps", "",
                  "Asserted by the harness so they cannot quietly disappear.", ""]
        for r in gaps:
            g = r.gap
            lines.append(
                f"- **{g['capability']}** — no rule covers this. "
                f"Exposure on this single shipment: USD {g['exposure_usd']:,.2f}. {g['note']}"
            )
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
