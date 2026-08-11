#!/usr/bin/env bash
# One command, no dependencies, no credentials, no network.
set -euo pipefail
cd "$(dirname "$0")"

echo "### Three-way match: contract <-> shipping documents <-> invoice"
python3 -m src.reconcile || true

echo
echo "### Rule catalogue eval"
python3 evals/run_eval.py
