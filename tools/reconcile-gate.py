#!/usr/bin/env python3
"""reconcile-gate.py — Norm #4, as code.

Open anomaly => the manifest may NOT also claim zero_divergence / perfect trust.
A consensus engine cannot honestly report "no divergence" while its own anomaly
ledger lists unresolved entries. This reads the ledger as structured data (not
prose) and exits non-zero on contradiction.

The self cannot see itself: this check is run by CI (an external observer), never
by the artifact that makes the claim.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "the-honest-swarm-researcher" / "anomaly_manifest.json"


def main() -> int:
    if not MANIFEST.exists():
        print(f"FAIL: {MANIFEST} not found", file=sys.stderr)
        return 1

    data = json.loads(MANIFEST.read_text())
    anomalies = data.get("anomalies", [])
    open_anoms = [
        a for a in anomalies
        if not str(a.get("status", "")).strip().upper().startswith("RESOLVED")
    ]

    claims_zero_div = data.get("zero_divergence") is True
    consensus = str(data.get("consensus", ""))
    claims_aligned = "no state drift" in consensus.lower() or "all 6 nodes aligned" in consensus.lower()

    print(f"open anomalies: {len(open_anoms)} "
          f"({', '.join(a.get('id', '?') for a in open_anoms) or 'none'})")
    print(f"claims zero_divergence: {claims_zero_div}")
    print(f"consensus prose asserts alignment/no-drift: {claims_aligned}")

    if open_anoms and (claims_zero_div or claims_aligned):
        print(
            "\nFAIL (Norm #4): the manifest has open anomalies but also asserts "
            "zero divergence / full alignment. Open anomaly => no zero_divergence. "
            "Derive the claim from state; do not assert it.",
            file=sys.stderr,
        )
        return 1

    print("\nOK: divergence claims reconcile with the anomaly ledger.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
