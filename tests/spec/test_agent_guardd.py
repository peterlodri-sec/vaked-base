#!/usr/bin/env python3
"""test_agent_guardd.py — the network-membrane vertical slice, end to end.

Exercises the whole loop the agent-guardd reference impl closes:

  1. Emitter. `vakedc lower vaked/examples/membrane/agent-egress.vaked` produces
     `gen/ebpf.policy.json` with the expected compiled membrane (deny-by-default,
     loopback allow-set, grant lattice, observe channel), deterministically.
  2. Decision. policy.decide is deny-by-default: the allow-set is permitted,
     everything else (incl. an un-listed loopback port and a non-IP host) denied.
  3. Enforce + testify + verify. Guard.connect writes one Event.Ebpf per verdict
     to the eventd hash chain; verify_run proves the chain is intact AND every
     verdict conforms to the declared policy — "the membrane held".
  4. Conformance. A forged testimony event (claims allow for a denied dest) is
     caught by verify_run as a mismatch.
  5. Tamper. One flipped ledger byte breaks the chain; verify_run refuses it.
  6. BPF. compile_posture emits the exact deny/allow bytecode; load_membrane
     loads a real cgroup/skb program where the kernel permits (tolerant of a
     sandbox that forbids it — the reference datapath is the fallback).

Stdlib only; driven through the package APIs (no subprocess).
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)

from vakedc.parser import parse_source            # noqa: E402
from vakedc.resolve import build_graph            # noqa: E402
from vakedc import lower as lower_mod              # noqa: E402

import agent_guardd as guardd                      # noqa: E402
from agent_guardd.policy import Membrane, Rule, decide, load_policy  # noqa: E402
from agent_guardd.enforce import run_attempts      # noqa: E402
from agent_guardd.verify import verify_run         # noqa: E402
from agent_guardd import bpf                        # noqa: E402
from eventd import EventLog                          # noqa: E402

EXAMPLE = os.path.join(REPO, "vaked", "examples", "membrane", "agent-egress.vaked")


def _lower_policy_text():
    src = open(EXAMPLE, encoding="utf-8").read()
    graph = build_graph(parse_source(src, "agent-egress.vaked"), "agent-egress.vaked")
    files = lower_mod.lower(graph, parse_source(src, "agent-egress.vaked")).files
    return files["gen/ebpf.policy.json"]


# --------------------------------------------------------------------------- #
# 1. Emitter
# --------------------------------------------------------------------------- #

def _test_emitter(lines):
    ok = True
    text = _lower_policy_text()
    doc = json.loads(text)
    membranes = doc.get("membranes", [])
    if len(membranes) != 1:
        lines.append(f"  FAIL emitter: expected 1 membrane, got {len(membranes)}")
        return False
    m = membranes[0]
    checks = {
        "principal": m.get("principal") == "worker",
        "default": m.get("default") == "deny",
        "grant": m.get("grant") == "network.loopback",
        "observe": m.get("observe") == "stream.ebpfEvents",
        "allow-count": len(m.get("allow", [])) == 2,
    }
    ports = sorted(r["port"] for r in m.get("allow", []))
    checks["ports"] = ports == [7, 9]
    checks["cidr"] = all(r.get("cidr") == "127.0.0.1/32" for r in m.get("allow", []))
    for k, v in checks.items():
        if not v:
            ok = False
            lines.append(f"  FAIL emitter: {k} wrong ({m!r})")
    # determinism
    if _lower_policy_text() != text:
        ok = False
        lines.append("  FAIL emitter: non-deterministic policy output")
    if ok:
        lines.append("  PASS emitter: gen/ebpf.policy.json = deny-default + "
                     "loopback:{7,9} allow-set, grant network.loopback, deterministic")
    return ok


# --------------------------------------------------------------------------- #
# 2. Decision
# --------------------------------------------------------------------------- #

def _membrane():
    return Membrane(
        name="agentEgress", principal="worker", grant="network.loopback",
        default="deny",
        allow=[Rule("tcp", "127.0.0.1", "127.0.0.1/32", 9),
               Rule("tcp", "127.0.0.1", "127.0.0.1/32", 7)],
        observe="stream.ebpfEvents")


def _test_decide(lines):
    ok = True
    m = _membrane()
    allow = [("127.0.0.1", 9), ("127.0.0.1", 7)]
    deny = [("127.0.0.1", 4444), ("127.0.0.1", 8), ("10.0.0.1", 9),
            ("8.8.8.8", 53), ("not-an-ip", 9)]
    for h, p in allow:
        a, _ = decide(m, h, p)
        if a != "allow":
            ok = False
            lines.append(f"  FAIL decide: {h}:{p} should allow, got {a}")
    for h, p in deny:
        a, _ = decide(m, h, p)
        if a != "deny":
            ok = False
            lines.append(f"  FAIL decide: {h}:{p} should deny, got {a}")
    if ok:
        lines.append(f"  PASS decide: deny-by-default — {len(allow)} allowed, "
                     f"{len(deny)} denied (incl. unlisted loopback port + non-IP)")
    return ok


# --------------------------------------------------------------------------- #
# 3. Enforce + testify + verify (membrane held)
# --------------------------------------------------------------------------- #

def _test_enforce_verify(lines):
    ok = True
    m = _membrane()
    from agent_guardd.policy import Policy
    policy = Policy(runtime="agent-egress", membranes=[m])
    with tempfile.TemporaryDirectory() as td:
        log = os.path.join(td, "log.jsonl")
        dests = [("127.0.0.1", 9), ("127.0.0.1", 4444),
                 ("10.0.0.1", 9), ("8.8.8.8", 53)]
        attempts = run_attempts(m, log, "reference", dests)
        if not all(a.held for a in attempts):
            ok = False
            leaks = [(a.host, a.port, a.outcome) for a in attempts if not a.held]
            lines.append(f"  FAIL enforce: membrane leaked at {leaks}")
        denied = [a for a in attempts if a.action == "deny"]
        if not all(a.outcome == "blocked" for a in denied):
            ok = False
            lines.append("  FAIL enforce: a denied destination was not blocked")
        v = verify_run(policy, log)
        if not v.chain_ok:
            ok = False
            lines.append(f"  FAIL verify: chain not intact ({v.error})")
        if not v.held:
            ok = False
            lines.append(f"  FAIL verify: membrane not held ({v.mismatches})")
        if (v.n_events, v.n_allow, v.n_deny) != (4, 1, 3):
            ok = False
            lines.append(f"  FAIL verify: counts {(v.n_events, v.n_allow, v.n_deny)} "
                         f"!= (4,1,3)")
    if ok:
        lines.append("  PASS enforce+verify: 4 verdicts testified, chain intact, "
                     "membrane HELD (1 allow / 3 deny, all denials blocked)")
    return ok


# --------------------------------------------------------------------------- #
# 4. Conformance — a forged event is caught
# --------------------------------------------------------------------------- #

def _test_forged_event(lines):
    ok = True
    m = _membrane()
    from agent_guardd.policy import Policy
    policy = Policy(runtime="agent-egress", membranes=[m])
    with tempfile.TemporaryDirectory() as td:
        log = os.path.join(td, "log.jsonl")
        # a well-chained but LYING event: claims allow for a denied destination
        with EventLog(log, writer=True) as el:
            el.append(guardd.egress_event(
                "agentEgress", "worker", "8.8.8.8", 53,
                "allow", "forged", "reference", seq=0))
        v = verify_run(policy, log)
        if not v.chain_ok:
            ok = False
            lines.append("  FAIL forged: chain should be intact (the lie is in "
                         "the payload, not the hash)")
        if v.held or not v.mismatches:
            ok = False
            lines.append("  FAIL forged: verify did not catch the policy mismatch")
    if ok:
        lines.append("  PASS forged: intact-chain but policy-violating event "
                     "flagged as a conformance mismatch (membrane VIOLATED)")
    return ok


# --------------------------------------------------------------------------- #
# 5. Tamper — a flipped byte breaks the chain
# --------------------------------------------------------------------------- #

def _test_tamper(lines):
    ok = True
    m = _membrane()
    from agent_guardd.policy import Policy
    policy = Policy(runtime="agent-egress", membranes=[m])
    with tempfile.TemporaryDirectory() as td:
        log = os.path.join(td, "log.jsonl")
        run_attempts(m, log, "reference", [("127.0.0.1", 9), ("8.8.8.8", 53)])
        data = bytearray(open(log, "rb").read())
        i = data.find(b'"reason"')
        pos = (i + 12) if i >= 0 else len(data) // 2
        data[pos] ^= 0x20
        open(log, "wb").write(data)
        v = verify_run(policy, log)
        if v.chain_ok or v.held:
            ok = False
            lines.append("  FAIL tamper: a flipped byte was not detected")
    if ok:
        lines.append("  PASS tamper: one flipped ledger byte → chain refused "
                     "(boot-verify TamperError)")
    return ok


# --------------------------------------------------------------------------- #
# 6. BPF — bytecode + (tolerant) real load
# --------------------------------------------------------------------------- #

def _test_bpf(lines):
    ok = True
    import struct
    deny = bpf.compile_posture("deny")
    allow = bpf.compile_posture("allow")
    want_deny = struct.pack("<BBhi", 0xB7, 0, 0, 0) + struct.pack("<BBhi", 0x95, 0, 0, 0)
    want_allow = struct.pack("<BBhi", 0xB7, 0, 0, 1) + struct.pack("<BBhi", 0x95, 0, 0, 0)
    if deny != want_deny or allow != want_allow:
        ok = False
        lines.append("  FAIL bpf: compile_posture bytecode wrong")
    rep = bpf.load_membrane(_membrane())
    if rep.mechanism not in ("reference", "ebpf-cgroup"):
        ok = False
        lines.append(f"  FAIL bpf: unexpected mechanism {rep.mechanism!r}")
    detail = "reference (bpf unavailable here)"
    if rep.available and rep.loaded:
        if rep.verdict != "drop" or rep.insn_count < 2:
            ok = False
            lines.append(f"  FAIL bpf: loaded report inconsistent ({rep})")
        detail = ("real cgroup/skb load, verifier-accepted; attach=%s"
                  % ("in-kernel" if rep.attached else "refused→reference"))
    if ok:
        lines.append(f"  PASS bpf: posture bytecode exact; load_membrane → {detail}")
    return ok


# --------------------------------------------------------------------------- #

def run():
    lines = []
    ok = True
    for label, fn in [
        ("emitter (gen/ebpf.policy.json)", _test_emitter),
        ("decide (deny-by-default)", _test_decide),
        ("enforce + testify + verify (held)", _test_enforce_verify),
        ("conformance (forged event caught)", _test_forged_event),
        ("tamper (chain refused)", _test_tamper),
        ("bpf (bytecode + real load)", _test_bpf),
    ]:
        lines.append(label + ":")
        ok &= fn(lines)
    return bool(ok), lines


if __name__ == "__main__":
    ok, lines = run()
    print("== test_agent_guardd ==")
    for ln in lines:
        print(ln)
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
