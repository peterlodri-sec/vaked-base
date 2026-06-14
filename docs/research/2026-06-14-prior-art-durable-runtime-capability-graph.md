# Prior Art & Lessons — Durable Runtime, Capability Graph, Multi-Target Compilation

> Deep-research synthesis (2026-06-14). Five angles, ~24 primary sources, claims
> tagged with confidence after adversarial verification. Informs Vaked's runtime,
> security, and compiler design. Artifacts are derived; treat this as a reference,
> not a spec — versioned decisions belong in `docs/language/` and `protocol/rfcs/`.

## TL;DR — five highest-value findings

1. **The compiler is the moat.** Every durable-workflow runtime's worst footguns
   (Temporal/Azure non-determinism errors) and every eBPF security mistake
   (enforcing on an observe-only hook) are *runtime* failures a typed semantic
   graph can turn into *compile* errors. This is the differentiated bet.
2. **"eBPF testifies, Zig enforces" is defensible but stricter than the kernel
   requires** — it leaves fail-closed, race-free enforcement on the table
   (`bpf_lsm` + cgroup/connect hooks).
3. **Deny-by-default egress ≈ object-capability "no ambient authority" ~1:1** —
   but a network membrane gates *channels*; it cannot *wrap/attenuate a capability
   travelling inside an allowed connection*. That gap is the sharpest design edge.
4. **Do not build Vaked "fibers" on Zig `async`/`await` — those keywords do not
   exist.** Target the new `std.Io` colorblind model (0.16; backends experimental).
5. **Adopt MLIR-style progressive lowering, not N direct emitters** — lower through
   intermediate dialects so capability/policy intent survives until each backend
   pass needs it.

## 1. Durable / agentic workflow runtimes

- Temporal/Cadence/Azure Durable use **event sourcing + deterministic replay**:
  workflow code re-runs from history on recovery and **must be deterministic** (no
  I/O, time, random in control flow). [docs.temporal.io/workflow-definition/determinism-constraints;
  learn.microsoft.com durable-task-code-constraints]
- Mutating a running workflow breaks replay → explicit **versioning markers**
  (`patched()`/Worker Versioning). [docs.temporal.io/patching]
- **DBOS** = Postgres-backed checkpointing; exactly-once *for DB ops* via
  single-transaction checkpoint (medium — vendor framing, DB-scoped). [docs.dbos.dev]
- **AWS Step Functions** = declarative JSON (ASL); Standard = exactly-once/durable,
  Express = at-least-once — chosen per workflow. [docs.aws.amazon.com/step-functions]
- **Replay cost grows with history** (Azure long-loop degradation, medium).

**Lessons:** `eventd/` (hash-chained log) makes event-sourced durability natural,
but it imposes the determinism tax → make the determinism boundary a language
construct (pure control-flow nodes; only `step`/`activity` nodes touch the world).
Pin each live execution to its compiled graph hash; require explicit migration to
mutate a running graph. Assume at-least-once for agent steps → require idempotency
keys. Design history compaction / continue-as-new from day one.

## 2. Object-capability model ↔ the capability graph

- A capability = **unforgeable reference fusing designation + authority**; **no
  ambient authority**. [Miller, "Capability Myths Demolished"; en.wikipedia.org/wiki/Object-capability_model]
- **"Only connectivity begets connectivity"** (gain a cap via initial/parenthood/
  endowment/introduction) → the live reference set *is* the authority graph.
- **Membrane** = transitive wrapping + single kill-switch → revoke a whole subgraph
  at once. [tvcutsem.github.io/membranes]
- **Confused deputy** = ambient authority + designation/authority separation; caps
  structurally avoid it. seL4 / Cap'n Proto / SES are production capability systems;
  Pony refcaps are a *different* (compile-time aliasing) notion — don't conflate.

**Maps cleanly:** deny-by-default egress = "no ambient authority"; the egress
allow-set = a node's out-edges. Static analysis: transitive reachability, POLA
violations, confused-deputy shapes. Implement "runtime membrane" as an
epoch/generation flip in eBPF maps (one write inerts the subgraph).

**Sharp edge:** eBPF gates channels; it **cannot wrap references in transit** — it
cannot downgrade a token/handle passed *inside* an allowed connection, so app-layer
delegation is invisible to the graph. Either keep all delegation inside
Vaked-minted capabilities, or have capability-aware Zig daemons parse a
CapTP/Cap'n-Proto-style protocol and re-derive edges. IP/port/cgroup egress is
closer to a network ACL than a true capability (NAT/shared-IP/DNS erode
unforgeability) → bind caps to cgroup/process identity + flow attestation; give each
membrane its own attenuated egress identity, not a shared deputy.

## 3. Multi-target declarative compilation

- **CUE**: types+values in one **unification lattice** (commutative/associative/
  idempotent); non-Turing-complete by design. [cuelang.org]
- **Nickel**: sound **gradual typing** + runtime **contracts** at boundaries +
  metadata-aware merge. [nickel-lang RATIONALE]
- **Dhall**: total/terminating, no general recursion — *termination ≠ tractability*.
- **MLIR**: dialects coexist; **progressive lowering** avoids LLVM IR's premature
  information loss. [mlir.llvm.org/docs/Rationale]
- CDK/CDKTF/Pulumi = transpilers; Pulumi native + *bridged* providers
  (leaky-abstraction lesson).

**Lessons:** make merge the core graph op (order-independent partial graphs);
stay non-Turing-complete on purpose but watch graph blowup; use progressive
lowering (capability-graph dialect → resource dialect → per-backend dialects for
flake.nix / Zig config / eBPF / OTel) — don't flatten policy into target syntax
early; insert boundary contracts where targets have hard validity rules; treat all
artifacts as **derived, never hand-edited** + regen-verify in CI (the landing-guru
cache-coherence pattern).

## 4. Supervision + fibers (OTP plane ↔ Zig daemons)

- OTP strategies `one_for_one`/`one_for_all`/`rest_for_one`; **restart-storm
  breaker** (terminate if > MaxR restarts in MaxT s; defaults 1/5s). [erlang.org sup_princ]
- BEAM shared-nothing message passing = basis of "let it crash".
- **Structured concurrency** (Sústrik 2016 / Smith nurseries): child lifetimes
  nested in parent; an error **cancels siblings then re-raises**. [vorpus.org]
- **Divergence:** structured concurrency **cancels** on fault; OTP **restarts**.
- Java virtual threads GA in JDK 21 (M:N); `StructuredTaskScope` still preview.
- **Zig: `async`/`await`/`suspend`/`resume` DO NOT EXIST** (only in bootstrap
  stage1; gone with stage2). Direction = colorblind async via **`std.Io`**
  (`io.async`→`Future`, `future.await`, `io.concurrent`, `Group`, `error.Canceled`).
  0.16.0 (min target, 2026-04-14) has `std.Io`; io_uring/evented backends
  experimental. [ziglang.org 0.16 notes; andrewkelley.me; kristoff.it]

**Lessons:** supervision = unit of recovery; fibers = unit of cancellation (not the
same). Do **not** design fibers on Zig language `async` — target `std.Io`, treat
evented backend as experimental, spec as a design→plan cycle. Two-level
cancellation: OTP plane → daemon (signal) → daemon fiber scopes (`error.Canceled`).
Inherit the restart-storm breaker per daemon; pick the strategy from real
capability-graph dependency edges. "Let it crash" only buys safety at the
OS-process boundary — keep daemons single-purpose so an in-daemon fault = one
restartable unit.

## 5. eBPF enforcement + Nix attestation

- Verifier rejects non-terminating programs; **512-byte stack**; no arbitrary
  memory. [docs.ebpf.io/verifier; kernel.org]
- **Hook point decides enforce vs observe** — kprobes/tracepoints are
  observe-only and **cannot change the system**; enforcement needs verdict hooks:
  `bpf_lsm` (≥5.7, 0=allow/-errno=deny), cgroup connect/skb, XDP/tc, override/signal.
  [linuxfoundation eBPF threat model; kernel.org prog_lsm]
- **Tetragon enforces in-kernel**; **Falco is detection-only**.
- **SIGKILL ≠ reliable prevention** (TOCTOU). [tetragon enforcement; datadoghq]
- **Nix reproducibility is a tracked goal, not a guarantee**; attestation = SLSA +
  in-toto; reproducibility strengthens attestation via independent rebuild.
  [reproducible.nixos.org; slsa.dev]

**Lessons:** keep "eBPF testifies" as default but add a **`bpf_lsm` enforcement
tier** for a few high-value invariants (exec/egress allowlist). Encode
observe-vs-enforce in the graph and reject "enforce" on observe-only hooks at
compile time. Put the block in the cgroup/connect hook (fail-closed, in-kernel);
let the Zig daemon own policy compilation + allowlist map, not the per-packet
verdict. Prefer `bpf_override_return`/LSM-deny over SIGKILL. Pair Nix with
in-toto/SLSA so the artifact chain carries signed, independently-rebuildable
provenance; don't overclaim "reproducible = trusted".

## Cross-cutting strategy

1. **Push runtime footguns into the type system** (determinism boundary,
   observe-vs-enforce hook typing, POLA/reachability) — all vakedc lowering checks.
2. **Progressive lowering** is the spine that keeps capability/policy/determinism
   semantics first-class until each backend consumes them.
3. **Doctrine correction:** "eBPF witnesses *and* (for a curated set) fail-closed
   enforces via bpf_lsm/cgroup; Zig daemons own policy + map population; Nix+in-toto
   attests at build." Fixes the TOCTOU + network-membrane attenuation gaps honestly.
4. **Name the durability substrate** (`eventd` → event-sourced) and make its
   determinism a compile-time contract.

## Confidence & caveats

- **Verify before betting:** DBOS exactly-once (DB-scoped); Azure long-loop
  degradation (single source); exact Zig version that dropped stage1 async (the
  fact is solid, the "0.11.0" label is not directly quoted); Go ~2KB stack figure.
- **Adversarial corrections applied:** "eBPF can enforce" only at verdict hooks;
  SIGKILL has TOCTOU gaps; Nix reproducibility tracked-not-guaranteed; Pony refcaps
  ≠ ocap authority caps; membrane attenuation depends on correct return-value wrapping.

## Follow-up issues

The three compiler checks below were filed as `agent`-labelled issues:
determinism-boundary enforcement, observe-vs-enforce hook typing, and
capability-graph POLA/reachability lints.
