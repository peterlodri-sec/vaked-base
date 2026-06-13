# agent-guardd — the network-membrane vertical slice

> Vaked declares. Nix materializes. **Zig enforces. eBPF testifies.** eventd
> witnesses. Surfaces reveal.

This is the first **end-to-end vertical slice** through the whole Vaked stack:
one `.vaked` declaration of a network egress membrane that **lowers** to a policy
artifact, is **enforced** by a daemon, **testifies** every decision onto the
tamper-evident event log, and is **verified** to have held — declaration to
evidence, closed.

`agent-guardd` owns the `network` and `ebpf` membranes in the roster
([`docs/runtime/README.md`](README.md)): *deny-by-default egress, DNS oracle,
eBPF cgroup maps*. The implementation here is the **Python reference / oracle**
([`agent_guardd/`](../../agent_guardd)) for the eventual Zig daemon — the same
`#15` pattern [`eventd/`](../../eventd) follows (Python fixes the bytes + the
decision; Zig reproduces them). The hyphenated daemon name maps to the
importable module `agent_guardd`.

## The loop

```text
Vaked declares     network agentEgress { default = "deny"; allow = [ egress(h,p) ] }
    │                                     vaked/examples/membrane/agent-egress.vaked
    ▼ vakedc lower  (0012 §7, ebpf.policy emitter — realized)
gen/ebpf.policy.json   { membranes: [ { principal, grant, default, allow:[…] } ] }
    │
    ▼ agent-guardd load_membrane()
Zig enforces       compile posture → real cgroup/skb BPF → BPF_PROG_LOAD
                   (kernel verifier accepts) → attach @ BPF_CGROUP_INET_EGRESS
    │
    ▼ Guard.connect()   deny-by-default decision per (host, port)
eBPF testifies     Event.Ebpf payload per verdict  ─┐
    │                                                │ single decision function,
    ▼ eventd append                                  │ two datapaths (kernel + ref)
eventd (immutable) hash-chained log.jsonl  ──────────┘
    │
    ▼ verify_run()
Surfaces reveal    chain intact ∧ every verdict conforms to the declared policy
                   ⇒ "the membrane held"
```

## What is real here, and what is honest

The slice is built to be **run and checked**, not asserted. Concretely:

| Leg | Status in this repo |
|-----|---------------------|
| **Declare → lower** | Real. `network` is grammar-legal; the [`ebpf.policy`](../language/0012-lowering.md) emitter (previously a deferred §7 no-op) now compiles the membrane into `gen/ebpf.policy.json`, deterministically, with provenance. |
| **Compile → load eBPF** | Real. `agent-guardd` assembles a real `BPF_PROG_TYPE_CGROUP_SKB` program for the deny-by-default posture and loads it via the `bpf()` syscall; the **in-kernel verifier accepts it** (returns a program fd + the "processed N insns" trace). No libbpf/BTF needed — the ABI is driven directly. |
| **Attach → in-kernel enforce** | Host-dependent. On a capable host (vakedos: real cgroup2 delegation) the program attaches at `BPF_CGROUP_INET_EGRESS` and enforces in-kernel. Inside a nested container (CI, this sandbox) the attach is **refused (EINVAL)** — reported, not hidden. |
| **Decide + testify** | Real, everywhere. The deny-by-default decision and the per-verdict `Event.Ebpf` testimony run in the userspace **reference datapath** — the byte-for-byte mirror of the kernel program's decision. This is authoritative wherever the attach is unavailable. |
| **Witness (eventd)** | Real. Testimony is appended to the [`eventd`](../../eventd) hash chain (single-writer, fsync, boot-verify). |
| **Verify** | Real. `verify_run` proves the chain is intact **and** every recorded verdict conforms to the *declared* policy. A forged-but-chained event is caught as a conformance mismatch; a single flipped byte is refused as tamper. |

The one link that the kernel sandbox can withhold is **attach**, and the daemon
says so out loud rather than faking enforcement. The security-critical decision
(deny-by-default) and the audit spine are real on every host.

## Run it

```bash
# 1. lower the membrane to its policy artifact
python3 -m vakedc lower vaked/examples/membrane/agent-egress.vaked --out /tmp/slice

# 2. probe what the kernel allows here (load? egress attach?)
python3 -m agent_guardd probe

# 3. the whole loop, BuildKit-style: load BPF → enforce → testify → verify → tamper-check
python3 -m agent_guardd demo /tmp/slice/gen/ebpf.policy.json

# or the one-shot task (lower + demo)
task slice
```

Sub-commands: `probe`, `compile <policy>`, `enforce <policy> --log L --connect host:port …`,
`verify <policy> --log L`, `demo <policy>`.

## Tests

[`tests/spec/test_agent_guardd.py`](../../tests/spec/test_agent_guardd.py) covers
the loop end to end: the emitter output, the deny-by-default decision, enforce +
testify + verify (membrane held), a forged-event conformance catch, byte-flip
tamper detection, and the BPF bytecode + real load (tolerant of a sandbox that
forbids the syscall). Registered in [`tests/spec/run_all.py`](../../tests/spec/run_all.py).

## Next (faithful follow-ups)

- A `cgroup/skb` program that parses the dest IP and enforces the **allow-set**
  in-kernel (not just the posture) — bounded packet access with the verifier as
  judge; the reference datapath already defines the exact bytes it must match.
- The DNS oracle leg (`network` membrane: name→policy resolution).
- The Zig port of the daemon, with this module as the conformance oracle.
- An operator surface subscribed to `stream.ebpfEvents` rendering the egress
  flow map (the `surface` leg of the mantra).
