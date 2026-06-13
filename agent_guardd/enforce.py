"""agent_guardd.enforce — the userspace reference datapath.

Applies :func:`agent_guardd.policy.decide` to real ``connect`` attempts and
testifies each verdict to the eventd chain. A DENY mirrors the kernel drop: the
connection is refused before a packet leaves (the membrane holds whether or not
the cgroup BPF program is attached). An ALLOW attempt actually dials the
destination — a connection-refused / timeout there is still an ALLOW (the
membrane permitted egress; nothing was listening), distinct from a policy DENY.

This is the authoritative enforcement when the cgroup attach is unavailable
(nested containers, CI) and the byte-for-byte mirror of what the kernel program
does where it IS attached — one decision function, two datapaths.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass

from .evidence import egress_event, testify
from .policy import Membrane, decide


@dataclass
class Attempt:
    host: str
    port: int
    action: str          # the policy verdict: "allow" | "deny"
    reason: str
    outcome: str         # "blocked" | "connected" | "no-listener" | "error:<x>"
    entry: dict          # the eventd chain entry that testified it

    @property
    def held(self) -> bool:
        """The membrane held for this attempt: a DENY was blocked, an ALLOW was
        not blocked (connected, or refused/timed-out by the far side)."""
        if self.action == "deny":
            return self.outcome == "blocked"
        return self.outcome != "blocked"


class Guard:
    """A membrane enforcer bound to one membrane + eventd log."""

    def __init__(self, membrane: Membrane, log_path: str, mechanism: str):
        self.membrane = membrane
        self.log_path = log_path
        self.mechanism = mechanism

    def connect(self, host: str, port: int, *, timeout: float = 0.25,
                seq: "int | None" = None) -> Attempt:
        action, reason = decide(self.membrane, host, port)
        if action == "deny":
            outcome = "blocked"          # refuse before any packet leaves
        else:
            outcome = self._dial(host, port, timeout)
        entry = testify(self.log_path, egress_event(
            self.membrane.name, self.membrane.principal, host, port,
            action, reason, self.mechanism, seq=seq))
        return Attempt(host, port, action, reason, outcome, entry)

    @staticmethod
    def _dial(host: str, port: int, timeout: float) -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return "connected"
        except (ConnectionRefusedError, socket.timeout, TimeoutError):
            return "no-listener"         # allowed; nothing was listening
        except OSError as e:
            return "error:%s" % (e.__class__.__name__)
        finally:
            s.close()


def run_attempts(membrane: Membrane, log_path: str, mechanism: str,
                 destinations: list) -> list:
    """Enforce + testify a sequence of ``(host, port)`` destinations in order.
    Returns the list of :class:`Attempt`."""
    guard = Guard(membrane, log_path, mechanism)
    out = []
    for i, (host, port) in enumerate(destinations):
        out.append(guard.connect(host, int(port), seq=i))
    return out
