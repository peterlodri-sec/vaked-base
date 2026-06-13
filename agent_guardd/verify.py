"""agent_guardd.verify — "the membrane held": replay the testimony and prove it.

Two independent guarantees, both from the eventd ledger alone:

  1. **Integrity** — the log is a contiguous, untampered hash chain from genesis
     (eventd's boot-verify; a single flipped byte breaks a link and is refused).
  2. **Conformance** — every testified verdict agrees with the *declared* policy:
     recompute :func:`agent_guardd.policy.decide` for each event's destination
     and compare it to the recorded ``action``. Any divergence is enforcement
     drift or tampering, not a membrane that held.

Together: the network membrane the operator *declared* in ``.vaked`` is exactly
the one the runtime *enforced* and the chain *testifies* — the closed loop.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from eventd import EventLog, TamperError
from .policy import Policy, decide


@dataclass
class VerifyReport:
    chain_ok: bool
    n_entries: int = 0
    n_events: int = 0          # ebpf_egress testimony events
    n_allow: int = 0
    n_deny: int = 0
    mismatches: list = field(default_factory=list)   # (attempt, recorded, expected, dst)
    rules_exercised: set = field(default_factory=set)
    error: "str | None" = None

    @property
    def held(self) -> bool:
        return self.chain_ok and not self.mismatches and self.error is None


def verify_run(policy: Policy, log_path: str) -> VerifyReport:
    """Verify the eventd log at ``log_path`` against ``policy``."""
    try:
        log = EventLog(log_path)        # boot-verify: TamperError if chain broken
    except TamperError as e:
        return VerifyReport(chain_ok=False, error=str(e))

    rep = VerifyReport(chain_ok=True, n_entries=len(log))
    for entry in log.entries:
        payload = entry.get("payload", {})
        if payload.get("kind") != "ebpf_egress":
            continue
        rep.n_events += 1
        principal = payload.get("principal", "")
        membrane = policy.membrane_for(principal) or (
            policy.membranes[0] if policy.membranes else None)
        recorded = payload.get("action")
        host, port = payload.get("daddr"), payload.get("dport")
        if recorded == "allow":
            rep.n_allow += 1
        elif recorded == "deny":
            rep.n_deny += 1
        if membrane is None:
            rep.mismatches.append((payload.get("attempt"), recorded,
                                   "no-policy", "%s:%s" % (host, port)))
            continue
        expected, _reason = decide(membrane, host, int(port))
        if expected != recorded:
            rep.mismatches.append((payload.get("attempt"), recorded, expected,
                                   "%s:%s" % (host, port)))
        elif recorded == "allow":
            rep.rules_exercised.add("%s:%s" % (host, port))
    return rep
