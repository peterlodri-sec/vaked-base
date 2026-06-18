#!/usr/bin/env python3
"""reconcile-gate.py — "derive, don't assert", as code (example to adapt).

Refuses an all-clear claim while the ledger still has open items. The point is
the SHAPE: derive the verdict from state and reject any independent assertion of
the opposite — don't maintain a forbidden-phrase list, and don't phrase-scan prose
(an audit doc must be free to quote/critique a false claim). Gate machine-readable
fields, not human narrative.

Here the "state" is a tiny JSON ledger; swap in your own (open issues, failing
tests, TODO count, …). MIT licensed.
"""
import json
import os
import re
import sys
from pathlib import Path

LEDGER = Path(os.environ.get("HONESTY_LEDGER", "ledger.json"))
DONE_STATES = {"RESOLVED", "FIXED", "WONTFIX", "CLOSED", "DONE"}


def is_done(status: str) -> bool:
    s = str(status).strip()
    return bool(s) and s.upper().split()[0].rstrip(".?,:;") in DONE_STATES


def find_allclear(node, path="$"):
    """Yield structured 'all is perfect' assertions (booleans / 1.0 scores)."""
    if isinstance(node, dict):
        for k, v in node.items():
            kl = str(k).lower()
            if re.search(r"zero[_\s-]*(divergence|defects?|issues?)", kl) and v is True:
                yield f"{path}.{k}=true"
            if re.search(r"(trust|health|pass)[_\s-]*(index|score|rate)", kl) \
                    and isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) >= 1.0:
                yield f"{path}.{k}={v}"
            yield from find_allclear(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from find_allclear(v, f"{path}[{i}]")


def main() -> int:
    if not LEDGER.exists():
        print(f"FAIL: ledger not found: {LEDGER}", file=sys.stderr)
        return 1
    data = json.loads(LEDGER.read_text())
    items = data.get("items", data.get("anomalies", []))
    open_items = [i for i in items if not is_done(i.get("status", ""))]
    claims = list(find_allclear(data))

    print(f"open items: {len(open_items)}  |  all-clear assertions: {claims or 'none'}")
    if open_items and claims:
        print(f"\nFAIL: open items exist but an all-clear claim was found: {claims}\n"
              "Derive the verdict from state; do not assert it.", file=sys.stderr)
        return 1
    print("OK: claims reconcile with ledger state.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
