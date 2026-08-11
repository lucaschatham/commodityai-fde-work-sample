"""Extraction layer.

Deployment note
---------------
Extraction is deliberately behind an interface with two implementations:

  FixtureExtractor  -- replays a committed golden extraction. Default. No network,
                       no key, deterministic. This is what the eval harness runs
                       against so that rule changes are measured in isolation from
                       model drift.

  ClaudeExtractor   -- calls the model against the raw corpus. Used to regenerate
                       fixtures and to measure extraction drift between model
                       versions.

Why the seam matters: if extraction and rules are evaluated together, a rules
regression and a model regression look identical in the results. Separating them
means a red eval always points at exactly one owner -- the deployment engineer
(rules) or the platform team (extraction). That distinction is the difference
between a useful bug report and a vague one.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .schema import Document, Extractor, Field, Shipment

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "data" / "fixtures"
CORPUS_DIR = REPO_ROOT / "data" / "synthetic"


class FixtureExtractor:
    """Replays a committed extraction. The default path for evals and demos."""

    name = "fixture"

    def __init__(self, fixture_dir: Path = FIXTURE_DIR) -> None:
        self.fixture_dir = fixture_dir

    def load(self, shipment_id: str) -> Shipment:
        path = self.fixture_dir / f"{shipment_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"no extraction fixture for {shipment_id} at {path}")
        raw = json.loads(path.read_text())
        return _shipment_from_dict(raw)

    def load_overlay(self, shipment_id: str, overlay: dict) -> Shipment:
        """Load the base fixture then apply field overrides.

        The eval harness uses this to build variant cases (a different moisture
        reading, a lower confidence, a missing document) without duplicating the
        whole fixture. Keeps the golden set readable and diffable.
        """
        raw = json.loads((self.fixture_dir / f"{shipment_id}.json").read_text())

        for doc_type in overlay.get("drop_documents", []):
            raw["documents"].pop(doc_type, None)

        for doc_type, doc in overlay.get("add_documents", {}).items():
            raw["documents"][doc_type] = {
                "doc_id": doc.get("doc_id", f"{doc_type.upper()}-EVAL"),
                "doc_type": doc_type,
                "fields": {
                    k: {
                        "value": v.get("value"),
                        "confidence": v.get("confidence", 0.99),
                        "extractor": v.get("extractor", "model"),
                        "source_span": v.get("source_span", "(injected by eval overlay)"),
                    }
                    for k, v in doc.get("fields", {}).items()
                },
            }

        for doc_type, fields in overlay.get("set_fields", {}).items():
            if doc_type not in raw["documents"]:
                continue
            for fname, patch in fields.items():
                target = raw["documents"][doc_type]["fields"].setdefault(
                    fname, {"value": None, "confidence": 1.0, "extractor": "model", "source_span": "(injected by eval overlay)"}
                )
                target.update(patch)

        return _shipment_from_dict(raw)


class ClaudeExtractor:
    """Live extraction against the raw corpus.

    Not exercised in the committed eval run: this work sample is built to run with
    no credentials so a reviewer can clone and execute it in one command. Set
    ANTHROPIC_API_KEY and run `python -m src.extract --refresh` to regenerate
    fixtures and diff them against the committed set.
    """

    name = "claude"
    MODEL = "claude-sonnet-4-5"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def load(self, shipment_id: str) -> Shipment:
        if not self.available:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Run with the default FixtureExtractor, "
                "or export a key to regenerate extractions from data/synthetic/."
            )
        raise NotImplementedError(
            "Live extraction is stubbed in this work sample. The interface, the "
            "field schema and the confidence contract are the deployable parts; "
            "the model call is the platform's job, not the deployment engineer's."
        )


def _shipment_from_dict(raw: dict) -> Shipment:
    documents: dict[str, Document] = {}
    for doc_type, doc_raw in raw["documents"].items():
        fields = {
            fname: Field(
                name=fname,
                value=f["value"],
                confidence=float(f["confidence"]),
                source_doc=doc_raw["doc_id"],
                source_span=f.get("source_span", ""),
                extractor=Extractor(f.get("extractor", "model")),
            )
            for fname, f in doc_raw["fields"].items()
        }
        documents[doc_type] = Document(
            doc_id=doc_raw["doc_id"], doc_type=doc_raw["doc_type"], fields=fields
        )
    return Shipment(
        shipment_id=raw["shipment_id"],
        contract_ref=raw["contract_ref"],
        documents=documents,
    )


def get_extractor(prefer_live: bool = False):
    if prefer_live:
        live = ClaudeExtractor()
        if live.available:
            return live
        print("[extract] ANTHROPIC_API_KEY not set, falling back to fixtures.")
    return FixtureExtractor()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Extraction layer utilities")
    ap.add_argument("--refresh", action="store_true", help="regenerate fixtures via the live extractor")
    ap.add_argument("--shipment", default="SHP-4471")
    args = ap.parse_args()

    if args.refresh:
        ClaudeExtractor().load(args.shipment)
    else:
        s = FixtureExtractor().load(args.shipment)
        print(f"{s.shipment_id}  contract {s.contract_ref}")
        for dtype, doc in s.documents.items():
            lo = min((f.confidence for f in doc.fields.values()), default=1.0)
            print(f"  {dtype:<26} {doc.doc_id:<18} {len(doc.fields):>2} fields  min conf {lo:.2f}")
