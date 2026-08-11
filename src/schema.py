"""Canonical data model for the Harbourline deployment.

Design note for reviewers
-------------------------
Every extracted value carries its own provenance and confidence. This is
deliberate. In a document-reconciliation deployment the expensive failures are
not "the model read the number wrong" -- they are "the model read the number
wrong and nothing downstream knew it was uncertain."

Carrying confidence at the *field* level lets the rules engine make a claim it
otherwise could not: a rule is only as trustworthy as its least confident input.
See rules.py::evaluate for where that gets enforced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class Extractor(str, Enum):
    """How a field arrived in the system. Drives audit + review defaults."""

    DETERMINISTIC = "deterministic"  # regex / positional parse of a fixed layout
    MODEL = "model"                  # LLM extraction from unstructured text
    HUMAN = "human"                  # keyed or corrected by an operator
    DERIVED = "derived"              # computed by us from other fields


class Layer(str, Enum):
    """Which layer owns the decision. This is the core config decision an FDE makes."""

    DETERMINISTIC = "deterministic"  # pure arithmetic / date / set logic. No model.
    MODEL_ASSISTED = "model_assisted"  # model proposes, deterministic logic verifies
    HUMAN_AUTHORITY = "human_authority"  # never auto-cleared, regardless of confidence


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ALLOWANCE = "allowance"          # tolerated deviation with a contractual remedy
    NEEDS_REVIEW = "needs_review"    # routed to a human queue
    NOT_APPLICABLE = "not_applicable"


class Severity(str, Enum):
    BLOCKING = "blocking"    # stops the payment / posting
    ADVISORY = "advisory"    # logged, does not stop the workflow
    INFO = "info"


@dataclass(frozen=True)
class Field:
    """One extracted value plus everything needed to defend it in an audit."""

    name: str
    value: Any
    confidence: float
    source_doc: str
    source_span: str            # verbatim text the value came from
    extractor: Extractor

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"{self.name}: confidence must be in [0,1]")


@dataclass
class Document:
    """A single source document and its extracted fields."""

    doc_id: str
    doc_type: str
    fields: dict[str, Field] = field(default_factory=dict)

    def get(self, name: str) -> Field | None:
        return self.fields.get(name)

    def value(self, name: str, default: Any = None) -> Any:
        f = self.fields.get(name)
        return f.value if f else default


@dataclass
class Shipment:
    """The unit of reconciliation: one contract, one physical movement, one invoice."""

    shipment_id: str
    contract_ref: str
    documents: dict[str, Document] = field(default_factory=dict)

    def doc(self, doc_type: str) -> Document | None:
        return self.documents.get(doc_type)

    def field(self, doc_type: str, name: str) -> Field | None:
        d = self.documents.get(doc_type)
        return d.get(name) if d else None

    def value(self, doc_type: str, name: str, default: Any = None) -> Any:
        d = self.documents.get(doc_type)
        return d.value(name, default) if d else default

    def present_doc_types(self) -> set[str]:
        return set(self.documents.keys())


@dataclass
class RuleResult:
    rule_id: str
    name: str
    layer: Layer
    severity: Severity
    outcome: Outcome
    message: str
    inputs: list[str] = field(default_factory=list)       # field names consumed
    min_input_confidence: float | None = None
    financial_impact_usd: float | None = None
    review_reason: str | None = None
    remedy: str | None = None
    # Set when the confidence gate withheld a verdict: what the rule would have
    # said had its inputs been trusted. Kept so reviewers see the proposed answer
    # rather than an unexplained "needs review".
    withheld_outcome: Outcome | None = None

    @property
    def is_exception(self) -> bool:
        return self.outcome in (Outcome.FAIL, Outcome.NEEDS_REVIEW, Outcome.ALLOWANCE)

    @property
    def blocks_payment(self) -> bool:
        return self.severity is Severity.BLOCKING and self.outcome in (
            Outcome.FAIL,
            Outcome.NEEDS_REVIEW,
        )


@dataclass
class ReconciliationReport:
    shipment_id: str
    contract_ref: str
    results: list[RuleResult] = field(default_factory=list)

    @property
    def exceptions(self) -> list[RuleResult]:
        return [r for r in self.results if r.is_exception]

    @property
    def blocking(self) -> list[RuleResult]:
        return [r for r in self.results if r.blocks_payment]

    @property
    def clear_to_pay(self) -> bool:
        return not self.blocking

    @property
    def confirmed_recoverable_usd(self) -> float:
        """Money the pipeline is prepared to assert on its own."""
        return round(
            sum(r.financial_impact_usd or 0.0
                for r in self.results if r.outcome is Outcome.FAIL),
            2,
        )

    @property
    def pending_review_usd(self) -> float:
        """Money contingent on a human confirming a low-confidence input.

        Kept separate from confirmed_recoverable_usd on purpose. Reporting one
        blended number would let an unverified extraction underwrite a claim
        against a counterparty.
        """
        return round(
            sum(r.financial_impact_usd or 0.0
                for r in self.results if r.outcome is Outcome.NEEDS_REVIEW),
            2,
        )

    @property
    def total_exposure_usd(self) -> float:
        return round(self.confirmed_recoverable_usd + self.pending_review_usd, 2)


def parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)
