"""agent_guardd.policy — load + decide the compiled egress membrane policy.

Reads ``gen/ebpf.policy.json`` (the 0012 ``ebpf.policy`` lowering output) and
provides the single authoritative egress decision, :func:`decide`. This is the
contract BOTH datapaths honour identically:

  * the kernel datapath (:mod:`agent_guardd.bpf`) compiles the membrane's
    deny-by-default posture into a real ``cgroup/skb`` BPF program;
  * the userspace reference datapath (:mod:`agent_guardd.enforce`) applies the
    same :func:`decide` on every ``connect`` and testifies the verdict.

Deny-by-default (0012 §7): a destination ``(host, port)`` is allowed iff it
matches an allow rule (``host`` ∈ the rule's CIDR ∧ ``port`` == the rule's port
∧ same proto); otherwise the membrane's ``default`` posture applies. Pure and
deterministic — no clock, no network, no resolver (hosts are IP literals; a
non-IP destination is denied as un-attestable).

Python 3.11+ stdlib only (mirrors eventd's reference-impl discipline).
"""
from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rule:
    """One allow rule: ``proto`` ``host``/``cidr`` ``port`` (an emitted
    ``allow[]`` entry of ``gen/ebpf.policy.json``)."""
    proto: str
    host: str
    cidr: str
    port: int


@dataclass
class Membrane:
    """One egress membrane: a principal, its lattice grant, the deny/allow
    default posture, and the allow-set."""
    name: str
    principal: str
    grant: "str | None"
    default: str
    allow: list = field(default_factory=list)   # list[Rule]
    observe: "str | None" = None


@dataclass
class Policy:
    runtime: str
    membranes: list = field(default_factory=list)   # list[Membrane]

    def membrane_for(self, principal: str) -> "Membrane | None":
        for m in self.membranes:
            if m.principal == principal:
                return m
        return None

    def only(self) -> Membrane:
        """The sole membrane (the common single-principal slice case)."""
        if len(self.membranes) != 1:
            raise ValueError(
                "policy has %d membranes; name the principal explicitly"
                % len(self.membranes))
        return self.membranes[0]


def load_policy(path: str) -> Policy:
    """Parse a ``gen/ebpf.policy.json`` document into a :class:`Policy`."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    membranes = []
    for m in doc.get("membranes", []):
        rules = [Rule(proto=r.get("proto", "tcp"), host=r["host"],
                      cidr=r.get("cidr", r["host"] + "/32"), port=int(r["port"]))
                 for r in m.get("allow", [])]
        membranes.append(Membrane(
            name=m.get("membrane", ""), principal=m.get("principal", ""),
            grant=m.get("grant"), default=m.get("default", "deny"),
            allow=rules, observe=m.get("observe")))
    return Policy(runtime=doc.get("runtime", ""), membranes=membranes)


def decide(membrane: Membrane, host: str, port: int,
           proto: str = "tcp") -> "tuple[str, str]":
    """The egress verdict for ``(host, port)`` under ``membrane``.

    Returns ``(action, reason)`` where ``action`` is ``"allow"`` or ``"deny"``.
    Deny-by-default: an allow-rule match wins; otherwise the membrane ``default``
    posture decides. A non-IP host is denied (un-attestable at the packet layer).
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "deny", "non-ip destination %r (un-attestable)" % host
    for r in membrane.allow:
        if r.proto != proto or port != r.port:
            continue
        try:
            net = ipaddress.ip_network(r.cidr, strict=False)
        except ValueError:
            continue
        if ip.version == net.version and ip in net:
            return "allow", "matches allow %s:%d" % (r.host, r.port)
    if membrane.default == "allow":
        return "allow", "default=allow"
    return "deny", "deny-by-default (%s)" % membrane.name
