"""dogfood_bridge — wire an oracle finding to a real vaked-aegis kernel transition.

Slice 2 "double-dogfood": recording an oracle RE finding is itself judged and
logged as an aegis kernel transition (tools/dogfood). Two hash-chained ledgers
cross-reference — the oracle ledger entry carries transition_xref = the eventd
WAL entry hash; the WAL transition's actual_effects.writes contains the finding
artifact path. Acyclic: the WAL hashes the finding WITHOUT the xref; the oracle
ledger stores it WITH.

NOTE: wal_path and blobs_dir must live OUTSIDE `root` — kernel.judge snapshots the
whole non-git root subtree, so state dirs under root would register as changes
and fail the capability gate.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
_DOGFOOD = os.path.join(_REPO, "tools", "dogfood")
for _p in (_HERE, _DOGFOOD, _REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bridge          # oracle/bridge.py            # noqa: E402
import kernel          # dogfood/kernel.py           # noqa: E402
from eventd import EventLog                          # noqa: E402


def ground_finding(*, finding: dict, finding_rel: str, root: str, scope: list,
                   wal_path: str, blobs_dir: str, oracle_ledger) -> dict:
    """Record `finding` as an aegis kernel transition and cross-link both chains.

    Returns {"verdict", "transition_xref", "ledger_entry", "linked_finding"}.
    Raises RuntimeError if the kernel rejects the transition.
    """
    finding = dict(finding)
    # normalize the finding's OWN observed_effects to the artifact path — the
    # shared key verify_xref checks for the WAL->finding direction.
    finding["observed_effects"] = bridge.to_observed_effects(finding, files_written=[finding_rel])

    def _proposer(root, scope, intent):
        dest = os.path.join(root, finding_rel)
        os.makedirs(os.path.dirname(dest) or root, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(finding, f, sort_keys=True)        # finding WITHOUT xref
        return {"writes": [finding_rel], "deletes": []}  # declared effects

    tgt = finding.get("target", {})
    intent = f"RE evidence: {tgt.get('path', '?')} fns={len(finding.get('functions', []))}"
    verdict = kernel.judge(root, list(scope), intent, _proposer,
                           wal_path=wal_path, blobs_dir=blobs_dir,
                           observed=finding["observed_effects"])
    if not verdict["accepted"]:
        raise RuntimeError(f"kernel rejected grounding: {verdict['reasons']}")
    wal_hash = verdict["hash"]
    linked = bridge.attach_transition(finding, wal_hash)  # finding WITH xref
    led_entry = oracle_ledger.append(linked)
    return {"verdict": verdict, "transition_xref": wal_hash,
            "ledger_entry": led_entry, "linked_finding": linked}


def verify_xref(*, finding: dict, wal_path: str, oracle_ledger) -> bool:
    """Prove the bidirectional link + both chains. Raises ValueError on any break."""
    if not oracle_ledger.verify():
        raise ValueError("oracle ledger chain invalid")
    xref = finding.get("transition_xref")
    if not xref:
        raise ValueError("finding has no transition_xref")
    with EventLog(wal_path) as log:                       # opens + verifies the WAL chain
        entries = list(log.entries)
    match = [e for e in entries if e["hash"] == xref]
    if not match:
        raise ValueError(f"transition_xref {xref[:16]}... not in WAL")
    wal_writes = set(match[0]["payload"].get("actual_effects", {}).get("writes", []))
    fw = set(finding.get("observed_effects", {}).get("writes", []))
    if not fw or not (fw <= wal_writes):
        raise ValueError(f"finding writes {sorted(fw)} not recorded by transition "
                         f"(writes={sorted(wal_writes)})")
    return True
