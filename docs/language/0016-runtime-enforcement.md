# 0016 — Runtime Enforcement: from compile-time POLA proof to kernel-enforced egress

## §1 Status / dependencies

Normative (Stage-1 scope). This note specifies the minimal runtime layer that
turns a **subset** of Vaked's compile-time POLA checks into kernel-enforced
predicates. It depends on:

- [`0011-type-system.md`](./0011-type-system.md) — the validated typed semantic
  graph and the capability attenuation order (§4); §4.5 is explicit that the
  compile-time check is the authority of record and that runtime enforcement is
  out of scope *there*. This note is where that runtime layer is specified.
- [`0012-lowering.md`](./0012-lowering.md) — the lowering contract (pure, total,
  hermetic; §2), the emitter registry (§3.4), the generated-header (§6.1) and
  provenance (§6.2) conventions, and the **deferred `ebpf.policy` registry slot**
  (§7). This note **supersedes** the "no concrete format is approved yet"
  deferral in 0012 §7 for `ebpf.policy`: the manifest format and the
  grant→tuple compilation specified in §4.2 below are the approved Stage-1
  mapping. The other deferred slots (`otel.config`, `systemd.units`,
  `surface.launcher`) remain deferred.
- [`0014-typed-capability-graph.md`](./0014-typed-capability-graph.md) — the
  typed capability graph (§3) and the zero-proof containment guarantee (§7); the
  egress allow-list is compiled from the resolved capability grant-sets this
  doc makes traversable at compile time.
- PR #249's eBPF observe/enforce type law (the `ebpf` capability domain
  `none < observe < attach_ro < attach_rw` and the rule that an *enforcing*
  program may not be emitted for an *observe-only* hook) — see
  [`vaked/schema/parallel-types.md`](../../vaked/schema/parallel-types.md).

**Grammar unchanged.** The `ebpf` kind (with `hook` / `intent` / `target`) and
the `net` / `ebpf` capability domains already exist; this note adds no new
surface syntax. It specifies an emitter, a manifest format, and a daemon
contract.

## §2 Abstract

Today's POLA guarantee (0011 §4, 0014 §7) is **compile-time only**: `vakedc check`
proves the static authority assignment is POLA-consistent, but nothing prevents a
running workload from exceeding it. This note specifies the minimal runtime layer
that turns a **subset** of those checked properties into **kernel-enforced
predicates**:

1. a lowered **`ebpf.policy` manifest** — canonical JSON projected from the
   capability grant-sets (§4.2), filling the 0012 §7 deferral slot;
2. a single Zig daemon, **`agent-guardd`**, that loads the manifest, builds a
   per-cgroup BPF egress allow-map, and attaches it (§4.1); and
3. the enforcement chain **authority-decision → BPF allow-list → kernel verdict
   → audit event** (§5).

The compile-time proof remains the authority of record; the runtime is a *lossy
partial projection* of it (§3).

## §3 Scope / Non-goals

This section is deliberately, brutally honest about what Stage 1 does **not**
do. The runtime layer is a partial, lossy projection of the compile-time graph,
and the failure to say so plainly is itself a credibility risk.

### In scope (Stage 1)

- **Network egress allow-list per cgroup**, enforced at the `cgroup_connect`
  hook (cgroup v2), compiled from the capability grant-sets (`net.egress`,
  `net.lan`, `net.loopback`; 0011 §4, parallel-types `net` domain).
- **Default-deny.** A cgroup with no matching allow-tuple is denied egress. The
  manifest never produces an allow-all rule.
- **Refusal to emit or load an enforcing program from an observe-only hook.**
  The emitter refuses `intent: "enforce"` on a hook that only holds
  `ebpf.observe` (PR #249's type law); the daemon **re-validates** the same
  predicate at load time (§4.1).
- **Tamper-evident audit.** Every verdict (allow/deny) is streamed to `eventd`
  (the append-only, hash-chained event log) and on to `otelcol`.

### Out of scope / honest caveats

- **Tamper-*evident*, not tamper-*proof*.** The audit chain detects tampering;
  it does not prevent it. A `root` adversary can detach the BPF program, stop
  `agent-guardd`, or rewrite the cgroup map. Stage 1 buys *detection*, not
  *prevention*, against a privileged adversary.
- **Not confused-deputy or semantic-correctness enforcement.** The kernel
  enforces *syscall/packet predicates* (this cgroup may `connect()` to this
  CIDR:port), not *intent*. An in-policy connection initiated for the wrong
  reason — a confused deputy, or an LLM that "hallucinates" a request to an
  allowed endpoint — is **allowed**. Semantic correctness is not a kernel
  predicate and is explicitly out of scope.
- **Stage 1 is egress only.** Filesystem (`fs.*`), process (`process.*`), and
  MCP (`mcp.*`) membranes are deferred to later stages. Their grant-sets are
  *not* projected to a kernel predicate yet.
- **The compile-time POLA proof remains the authority of record.** The runtime
  is a **lossy partial projection**. Graph guarantees with **no kernel
  projection in Stage 1**, and which therefore remain enforced *only* at
  compile time:
  - the `used(p) ⊑ granted(p)` use-check (which is itself not yet implemented —
    0011 §4.5);
  - delegation/attenuation along mesh `->` edges *as authority semantics* (the
    kernel sees the resulting egress tuples, not the delegation structure that
    produced them);
  - `fs.*`, `process.*`, `mcp.*`, and `ebpf.attach_rw` authority beyond the
    egress projection;
  - generic-consistency, schema, and constraint guarantees (0011 §3, §5).
- **DNS name↔IP mismatch is a Stage-1 limitation.** A `net.egress` grant
  expressed against a DNS name is resolved to CIDR(s) at manifest-build time;
  the kernel map keys on IP/CIDR. A name whose resolution changes after the map
  is built, or DNS rebinding, is **not** caught by the egress map alone. Stage 1
  documents this as a known gap (a DNS oracle is daemon-design future work; see
  [`docs/runtime/README.md`](../runtime/README.md)).
- **Compromised root / kernel out of scope.** A compromised `root`, a kernel
  exploit, ring-0 code, or a rootkit defeats the whole layer. So does a kernel
  whose eBPF verifier is itself buggy. These are assumed-trusted (§6) and
  out-of-scope.

## §4 Minimal architecture

### §4.1 Single daemon responsibility — `agent-guardd`

`agent-guardd` (Zig; the `ebpf` + `network` membrane daemon in
[`docs/runtime/README.md`](../runtime/README.md)) is a **faithful loader**, not a
decision-maker. Its Stage-1 responsibilities, and only these:

1. **Read the manifest** (`gen/ebpf/<mesh>.policy.json`), verifying its 0012
   §6.1 generated header and §6.2 provenance hash.
2. **Re-validate observe/enforce at load** (defense-in-depth against #249's
   compile-time check): reject any entry with `intent: "enforce"` on a hook
   whose authority is observe-only, *before* loading any program. The
   compile-time check and the load-time check are independent; both must pass.
3. **Build the per-cgroup BPF egress allow-map** from the manifest's egress
   tuples (§4.2).
4. **Attach** the egress program at the `cgroup_connect` hook for each cgroup.
5. **Stream verdicts** (allow/deny, with the matched tuple) to `eventd`.

`agent-guardd` makes **no policy decisions**. Every allow/deny is determined by
the manifest, which is determined by the compile-time graph. The daemon's only
authority is *faithfulness to the manifest*; it is in the trusted set (§6)
precisely because of that narrow responsibility.

### §4.2 Manifest → BPF mapping

The emitter projects mesh nodes plus their resolved capability grant-sets into a
set of egress tuples:

```text
{ cgroup, family, proto, cidr, port }
```

- `cgroup` — the cgroup v2 path/id the mesh node's workload runs under.
- `family` — `AF_INET` / `AF_INET6`.
- `proto` — `tcp` / `udp`.
- `cidr` — destination network (from the resolved `net.egress` / `net.lan` /
  `net.loopback` grant, with DNS names resolved to CIDR(s) at build time — see
  the §3 DNS caveat).
- `port` — destination port (or a wildcard sentinel where the grant is
  port-agnostic).

These tuples become keys in a kernel **LPM_TRIE** (for the CIDR longest-prefix
match) and/or **hash** allow-map. A `cgroup_connect` whose `{family, proto,
dest-cidr, port}` matches an allow key for that cgroup is **allowed**; everything
else is **denied** (default-deny).

The manifest is **canonical JSON** — a stable, sorted, byte-deterministic
encoding carrying a 0012 §6.1 generated header and §6.2 provenance — **never
compiled bytecode**. Emitting JSON rather than a compiled BPF object preserves
0012 §2 hermeticity: lowering performs no compilation, no toolchain invocation,
and no IO; building and loading the actual BPF program is the daemon's job at
runtime, not lowering's. (This mirrors how lowering emits Nix expressions, not
build outputs.)

### §4.3 Where authority becomes a kernel predicate

The single trust-reduction path is:

```text
holds net.egress(<dest>)   (graph edge, 0011 §4 / 0014 §3)
        │  emitter (§4.2)
        ▼
{cgroup, family, proto, cidr, port}   (manifest tuple)
        │  agent-guardd map build (§4.1)
        ▼
LPM_TRIE / hash allow-map key   (kernel)
        │  cgroup_connect program
        ▼
ALLOW / DENY verdict   (kernel)
```

This **edge → tuple → key → verdict** path is the entire trust reduction from a
declared capability to a kernel decision. Anything not expressible as such a
tuple is, by construction, not enforced in Stage 1 (§3).

## §5 Enforcement-chain diagram

```text
COMPILE TIME (vakedc — pure, total, hermetic; 0011 §6, 0012 §2)
  parse → resolve → check
     │   E-CAP-* (ref-validity, mesh-edge attenuation) proven
     │   E-EBPF-ENFORCE-ON-OBSERVE proven (#249 type law)
     ▼
  validated typed semantic graph (0011 §6.1 stage 3 artifact; 0014)
     │
     │  ebpf.policy emitter (§4.2; fills 0012 §7 deferral)
     ▼
  gen/ebpf/<mesh>.policy.json   (canonical JSON + §6.1 header + §6.2 provenance)
─────────────────────────────────────────────  [ TRUST BOUNDARY ]
RUN TIME (NixOS host; OTP supervision plane)
  agent-supervisord (OTP)  supervises  agent-guardd (Zig)
     │
     ▼
  agent-guardd:  load manifest
              →  re-validate observe/enforce (§4.1.2)
              →  build per-cgroup egress allow-map (§4.2)
              →  attach cgroup_connect program
     │
     ▼
  KERNEL  cgroup_connect  →  allow / deny verdict
     │
     ▼
  eventd  (append-only, hash-chained audit spine)
     │
     ▼
  otelcol  (telemetry export)
```

## §6 Threat model

| Tier | Components / assumptions |
|------|--------------------------|
| **Trusted** | `vakedc` and its compile-time proofs (0011 §4/§6, 0014 §7); the manifest's *faithfulness* to the graph; `agent-guardd` as a faithful loader (§4.1); the NixOS-pinned toolchain (`trust = pinned{…}`, 0012 §4.2); the `eventd` writer (append-only, hash-chained). |
| **Untrusted** | The supervised agent workload itself; its peers; fiber data; MCP responses and any content flowing through the workload. |
| **Assumed** | SHA-256 collision/preimage resistance (audit-chain integrity); key custody for the chain; correctness of the host kernel and its **eBPF verifier**; cgroup v2 isolation; **the program is attached before the workload starts** (no TOCTOU launch gap — `agent-supervisord` orders attach-before-exec). |
| **Out of scope** | Compromised `root` / ring-0 / rootkit (can detach the program or stop the daemon — §3); side channels and covert channels; physical and firmware attacks; the agent's *semantic* behavior, including in-policy "hallucinated" egress (confused deputy); DNS rebinding (§3); unpinned-input supply-chain (anything outside `trust = pinned{…}`). |

## §7 Stage-1 stub acceptance criteria

Stage 1 is "done" when:

1. **`emit_ebpf_policy(graph, nodes)`** replaces the `emit_deferred` no-op for the
   `ebpf.policy` registry slot (0012 §3.4/§7). It is a **pure function**
   (0012 §2): canonical JSON, with a 0012 §6.1 generated header and §6.2
   provenance; **default-deny**; **one allow-tuple per resolved egress grant**;
   and it **refuses** `intent: "enforce"` on observe-only hooks
   (`E-EBPF-ENFORCE-ON-OBSERVE`, #249).
2. **The reference manifest → BPF mapping passes the kernel verifier** and
   round-trips: a destination in the allow-set is allowed; one outside it is
   denied.
3. **The `agent-guardd` Stage-1 skeleton** builds with **0 warnings**, loads the
   fixture manifest, and **rejects a corrupted enforce-on-`kprobe` entry** (an
   enforce intent on an observe-only hook) at load time (§4.1.2).
4. **A reference example** — `vaked/examples/ebpf/` — a `mesh` with one
   `net.egress` grant runs end to end: `vakedc lower` →
   `gen/ebpf/<mesh>.policy.json` → daemon → **allow** for the granted
   destination, **deny** for a non-granted destination, **both** recorded as
   hash-chained `eventd` entries.
5. **RFC-level honesty gate.** The §3 Scope/Non-goals and §6 Threat-model
   sections explicitly assert the out-of-scope tier (tamper-evident ≠
   tamper-proof; egress-only; no semantic/confused-deputy enforcement;
   compile-time proof is the authority of record). This honesty assertion is a
   gating criterion, not optional prose.

## §8 Cross-references

- 0011 — type system: capability attenuation order and the informal POLA
  soundness argument ([`0011-type-system.md`](./0011-type-system.md) §6, §4.5)
- 0012 — lowering: hermetic emitter contract (§3.4) and the `ebpf.policy`
  deferral this note supersedes (§7) — [`0012-lowering.md`](./0012-lowering.md)
- 0014 — typed capability graph: traversable grant-sets (§3) and zero-proof
  containment (§7) — [`0014-typed-capability-graph.md`](./0014-typed-capability-graph.md)
- 0017 — POLA formalization (deferred mechanization of the property a subset of
  which this note enforces) — [`0017-pola-formalization.md`](./0017-pola-formalization.md)
- PR #249 eBPF observe/enforce type law and the `net` / `ebpf` capability
  domains — [`vaked/schema/parallel-types.md`](../../vaked/schema/parallel-types.md)
- Daemon roster (`agent-supervisord`, `agent-guardd`, `eventd`, `otelcol`) and
  membrane mapping — [`docs/runtime/README.md`](../runtime/README.md)
