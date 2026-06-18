#!/usr/bin/env python3
"""reconcile-gate.py — Norm #4, as code (hardened after the gate-breaker audit).

Open anomaly => no machine-readable assertion of zero divergence / perfect trust.
The honest verdict is DERIVED from the open-anomaly count; any structured field
that asserts the opposite is rejected.

Hardening over v1 (all three bypasses found by honesty-gate-breaker, confirmed):
  A. strict terminal-state allowlist — "RESOLVED-ish"/"RESOLVEDx" no longer count
     as resolved (only RESOLVED / FIXED / WONTFIX / CLOSED, first token).
  B. structured trust-assertion scan — any *.json in the operation dir asserting
     zero_divergence==true or a numeric trust_index>=1.0 (at any nesting depth),
     not just the manifest's top-level field.
  C. relocation-resistant — scans every JSON claim surface in the dir.

Deliberately NOT phrase-scanning prose (.md): an audit doc must be free to quote
and critique a dishonest claim without tripping the gate. The gate governs
machine-readable claims; prose is the human-review surface. (Documented residual.)

The self cannot see itself: this runs in CI (external), from the trusted main
copy, never from the artifact that makes the claim.
"""
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(os.environ.get("HONESTY_REPO_ROOT", Path(__file__).resolve().parent.parent))
OPDIR = REPO / "the-honest-swarm-researcher"
MANIFEST = OPDIR / "anomaly_manifest.json"

RESOLVED_STATES = {"RESOLVED", "FIXED", "WONTFIX", "CLOSED"}


def is_resolved(status: str) -> bool:
    s = str(status).strip()
    if not s:
        return False
    head = s.upper().split()[0].rstrip(".?,:;")  # first whitespace token; no dash split
    return head in RESOLVED_STATES


def find_trust_assertions(node, path="$"):
    """Yield (path, reason) for structured zero-divergence / perfect-trust claims."""
    if isinstance(node, dict):
        for k, v in node.items():
            kl = str(k).lower()
            if re.search(r"zero[_\s-]*divergence", kl) and v is True:
                yield (f"{path}.{k}", "zero_divergence=true")
            if re.search(r"trust[_\s-]*index", kl) and isinstance(v, (int, float)) \
                    and not isinstance(v, bool) and float(v) >= 1.0:
                yield (f"{path}.{k}", f"trust_index={v}")
            yield from find_trust_assertions(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from find_trust_assertions(v, f"{path}[{i}]")


def main() -> int:
    if not MANIFEST.exists():
        print(f"FAIL: {MANIFEST} not found", file=sys.stderr)
        return 1

    data = json.loads(MANIFEST.read_text())
    anomalies = data.get("anomalies", [])
    open_anoms = [a for a in anomalies if not is_resolved(a.get("status", ""))]

    assertions = []
    for jf in sorted(OPDIR.glob("*.json")):
        try:
            jdata = json.loads(jf.read_text())
        except (ValueError, OSError):
            continue
        for ptr, reason in find_trust_assertions(jdata, jf.name):
            assertions.append((jf.name, ptr, reason))

    print(f"open anomalies: {len(open_anoms)} "
          f"({', '.join(a.get('id', '?') for a in open_anoms) or 'none'})")
    print(f"structured trust/divergence assertions: "
          f"{[f'{a[0]}:{a[2]}' for a in assertions] or 'none'}")

    if open_anoms and assertions:
        print(
            "\nFAIL (Norm #4): open anomalies exist, but a machine-readable "
            "zero-divergence / perfect-trust claim was found. Derive the verdict "
            "from state; do not assert it.\n"
            f"  open: {[a.get('id') for a in open_anoms]}\n"
            f"  assertions: {assertions}",
            file=sys.stderr,
        )
        return 1

    print("\nOK: no structured trust/divergence claim contradicts the open-anomaly state.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
