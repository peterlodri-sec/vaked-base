"""agent-guardd — the network-membrane enforcement + testimony daemon (Python
reference implementation).

Roster position (docs/runtime/README.md): ``agent-guardd`` — Zig · eBPF loader /
policy / audit; the ``network`` and ``ebpf`` membranes. This package is the
**Python reference / oracle** for that daemon (the #15 pattern eventd follows:
Python defines the bytes + the decision, Zig reproduces them). The hyphenated
daemon name maps to the importable module ``agent_guardd``.

It closes the network-membrane vertical slice:

    Vaked declares      network agentEgress { default = "deny"; allow = [...] }
        ↓ vakedc lower  gen/ebpf.policy.json            (policy)
    Nix materializes    (the flake spine wires the daemon — interface today)
    Zig enforces        load_membrane()  → real cgroup/skb BPF, attach @egress  (bpf)
                        Guard.connect()  → deny-by-default decision             (enforce)
    eBPF testifies      egress_event()   → Event.Ebpf payloads                  (evidence)
    eventd (immutable)  appended to the hash chain                              (eventd)
    Surfaces reveal     verify_run()     → "the membrane held"                  (verify)
"""
from .policy import Membrane, Policy, Rule, decide, load_policy
from .bpf import LoadReport, compile_posture, kernel_probe, load_membrane
from .evidence import egress_event, testify
from .enforce import Attempt, Guard, run_attempts
from .verify import VerifyReport, verify_run

__all__ = [
    "Membrane", "Policy", "Rule", "decide", "load_policy",
    "LoadReport", "compile_posture", "kernel_probe", "load_membrane",
    "egress_event", "testify",
    "Attempt", "Guard", "run_attempts",
    "VerifyReport", "verify_run",
]
