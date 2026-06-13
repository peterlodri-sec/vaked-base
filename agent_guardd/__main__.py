"""agent-guardd CLI — drive + demonstrate the network-membrane slice.

    python3 -m agent_guardd probe
        Report kernel BPF capability (load + egress attach) on this host.

    python3 -m agent_guardd compile <policy.json> [--principal P]
        Load the policy, compile + load the membrane's posture as a real
        cgroup/skb BPF program, and print the load/attach report.

    python3 -m agent_guardd enforce <policy.json> --log L \
            --connect host:port [--connect host:port ...]
        Enforce each destination + testify the verdict to the eventd log L.

    python3 -m agent_guardd verify <policy.json> --log L
        Verify the chain + prove the membrane held against the declared policy.

    python3 -m agent_guardd demo <policy.json> [--out DIR]
        The whole slice end-to-end, BuildKit-style: load BPF → enforce a fixed
        allowed/denied set → testify → verify → tamper-check.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile

from .bpf import kernel_probe, load_membrane
from .enforce import run_attempts
from .policy import decide, load_policy
from .verify import verify_run


def _pick(policy, principal):
    if principal:
        m = policy.membrane_for(principal)
        if m is None:
            sys.stderr.write("no membrane for principal %r\n" % principal)
            sys.exit(2)
        return m
    return policy.only()


def _parse_dest(s: str):
    host, _, port = s.rpartition(":")
    return host, int(port)


# --------------------------------------------------------------------------- #

def cmd_probe(_args) -> int:
    p = kernel_probe()
    print("bpf() available      :", p["bpf_available"])
    print("cgroup/skb loadable  :", p["cgroup_skb_loadable"])
    print("egress attach permit :", p["egress_attach"], "(%s)" % p["detail"]
          if p["detail"] else p["egress_attach"])
    return 0


def cmd_compile(args) -> int:
    policy = load_policy(args.policy)
    m = _pick(policy, args.principal)
    rep = load_membrane(m)
    print("membrane   :", m.name, "(principal %s, grant %s)" % (m.principal, m.grant))
    print("posture    : default=%s → in-kernel verdict %s" % (m.default, rep.verdict))
    print("allow-set  :", ", ".join("%s:%d" % (r.host, r.port) for r in m.allow) or "(none)")
    print("bpf load   :", rep.summary())
    if rep.verifier_log:
        print("verifier   :", rep.verifier_log)
    return 0


def cmd_enforce(args) -> int:
    policy = load_policy(args.policy)
    m = _pick(policy, args.principal)
    rep = load_membrane(m)
    dests = [_parse_dest(d) for d in args.connect]
    attempts = run_attempts(m, args.log, rep.mechanism, dests)
    for a in attempts:
        mark = "BLOCK" if a.action == "deny" else "ALLOW"
        print("  %-5s %s:%-5d  %-11s  %s" % (mark, a.host, a.port, a.outcome, a.reason))
    print("testified %d events → %s" % (len(attempts), args.log))
    return 0


def cmd_verify(args) -> int:
    policy = load_policy(args.policy)
    rep = verify_run(policy, args.log)
    print("chain      :", "intact" if rep.chain_ok else "BROKEN (%s)" % rep.error)
    print("events     : %d testified (%d allow, %d deny)"
          % (rep.n_events, rep.n_allow, rep.n_deny))
    if rep.mismatches:
        for at, rec, exp, dst in rep.mismatches:
            print("  MISMATCH attempt %s %s: recorded %s, policy says %s"
                  % (at, dst, rec, exp))
    print("membrane   :", "HELD ✓" if rep.held else "VIOLATED ✗")
    return 0 if rep.held else 1


def cmd_demo(args) -> int:
    policy = load_policy(args.policy)
    m = policy.only()
    out = args.out or tempfile.mkdtemp(prefix="vaked-guardd-")
    os.makedirs(out, exist_ok=True)
    log = os.path.join(out, "eventd", "log.jsonl")

    def step(n, label):
        print("\n#%d %s" % (n, label))

    print("=" * 70)
    print("agent-guardd — network-membrane vertical slice")
    print("  membrane %s · principal %s · grant %s · default %s"
          % (m.name, m.principal, m.grant, m.default))
    print("=" * 70)

    step(1, "compile + load the membrane posture as kernel eBPF")
    rep = load_membrane(m)
    print("   =>", rep.summary())
    if rep.verifier_log:
        print("   => verifier:", rep.verifier_log)

    step(2, "enforce egress (deny-by-default) + testify each verdict")
    # one allowed loopback dest from the allow-set, plus denials the policy must block
    allowed = [(r.host, r.port) for r in m.allow[:1]]
    denied = [("127.0.0.1", 4444), ("10.0.0.1", 9), ("8.8.8.8", 53)]
    attempts = run_attempts(m, log, rep.mechanism, allowed + denied)
    for a in attempts:
        mark = "BLOCK" if a.action == "deny" else "ALLOW"
        held = "held" if a.held else "LEAK"
        print("   %-5s %-15s:%-5d  %-11s  [%s]  %s"
              % (mark, a.host, a.port, a.outcome, held, a.reason))

    step(3, "verify the chain + prove the membrane held")
    v = verify_run(policy, log)
    print("   => chain %s; %d events (%d allow / %d deny); membrane %s"
          % ("intact" if v.chain_ok else "BROKEN",
             v.n_events, v.n_allow, v.n_deny,
             "HELD ✓" if v.held else "VIOLATED ✗"))

    step(4, "tamper check — flip one ledger byte, re-verify (must refuse)")
    tampered = _flip_one_byte(log)
    if tampered is None:
        print("   => (log empty; nothing to tamper)")
        tamper_ok = True
    else:
        v2 = verify_run(policy, log)
        tamper_ok = not v2.chain_ok
        print("   => flipped byte %d; re-verify chain: %s (%s)"
              % (tampered, "BROKEN — tamper detected ✓" if tamper_ok else "still intact ✗",
                 (v2.error or "")[:48]))

    ok = v.held and tamper_ok and rep.loaded
    print("\n" + "=" * 70)
    print("SLICE:", "CLOSED ✓ (declare → lower → load → enforce → testify → verify)"
          if ok else "INCOMPLETE ✗")
    print("  artifacts under:", out)
    print("=" * 70)
    return 0 if ok else 1


def _flip_one_byte(path: str) -> "int | None":
    """Flip one byte in the middle of the first payload to break the chain."""
    try:
        data = bytearray(open(path, "rb").read())
    except FileNotFoundError:
        return None
    if not data:
        return None
    # target a byte inside the first line's payload (after the first '{').
    i = data.find(b'"action"')
    pos = i + 10 if i >= 0 else len(data) // 2
    pos = min(pos, len(data) - 1)
    data[pos] ^= 0x20
    open(path, "wb").write(data)
    return pos


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="agent-guardd")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("probe"); sp.set_defaults(fn=cmd_probe)

    sp = sub.add_parser("compile")
    sp.add_argument("policy"); sp.add_argument("--principal")
    sp.set_defaults(fn=cmd_compile)

    sp = sub.add_parser("enforce")
    sp.add_argument("policy"); sp.add_argument("--principal")
    sp.add_argument("--log", required=True)
    sp.add_argument("--connect", action="append", default=[], required=True)
    sp.set_defaults(fn=cmd_enforce)

    sp = sub.add_parser("verify")
    sp.add_argument("policy"); sp.add_argument("--log", required=True)
    sp.set_defaults(fn=cmd_verify)

    sp = sub.add_parser("demo")
    sp.add_argument("policy"); sp.add_argument("--out")
    sp.set_defaults(fn=cmd_demo)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
