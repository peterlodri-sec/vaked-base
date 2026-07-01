# Vaked Security Membranes: an Object-Capability Architecture Chapter

Status: **Architecture chapter (draft)** | Created: 2026-06-14 | Track: Security / Runtime
Method: external claims primary-source-verified (deep-research, adversarial 3-vote, abstain-safe); Vaked internals repo-grounded with IMPLEMENTED / DESIGN-ONLY / ABSENT labels. No claim is left hand-wavy: each carries a citation or an explicit status tag.

## 0. The distinction this chapter exists to make

A reader who sees "object-capability" and "membrane" in the same document will assume Vaked is a Miller-style ocap runtime: unforgeable references, forwarding-proxy membranes, transitive revocation. **It is not, and saying so plainly is the point.**

- **Object-capability theory** (Miller) enforces authority *at runtime* through unforgeable references and proxy membranes.
- **Vaked** moves the authority proof to **compile-time static type-checking** (POLA certified before any code runs) and then enforces *coarse, per-kind* boundaries at runtime through **single-purpose daemons** (network egress, filesystem, process), not per-reference proxies.

> Vaked's `RELATED_WORK.md` states it directly: "Traditional object capabilities rely on runtime membranes and unforgeable object references. Vaked moves the enforcement to static type-checking ... a compile-time proof of POLA compliance, not a runtime enforcement mechanism." [INTERNAL: docs/language/RELATED_WORK.md]

So in this chapter, **"membrane" = a per-kind runtime enforcement boundary owned by a daemon** (the `network`/`fs`/`process`/`ebpf` membranes of `PROJECT_CONTEXT.md`), *not* a Miller forwarding proxy. The ocap vocabulary Vaked borrows (attenuation, POLA, delegation) is a *type-system discipline*; the ocap mechanisms Vaked does **not** implement (proxy shells, transitive revocation) are named here as ABSENT so no reader over-reads the guarantee.

## 1. Object-capability theory (external, verified)

All claims in this section are confirmed against primary sources by adversarial verification (3-0 votes).

- **Canonical source.** The model is grounded in Mark S. Miller, *Robust Composition: Towards a Unified Approach to Access Control and Concurrency Control*, PhD thesis, Johns Hopkins University, May 2006. [Source: erights.org/talks/thesis/; worrydream.com/refs/Miller_2006_-_Robust_Composition.pdf] (Note: arXiv:1907.07154 is a 2019 *secondary* report citing Miller and must NOT be cited as the origin - this was explicitly refuted in verification.)
- **Only connectivity begets connectivity** (Miller's heading; the question's "Rule of Connectivity"). All access derives from previous access; two disjoint object subgraphs cannot become connected because no one can introduce them. For Alice to authorize Bob to reach Carol, Alice must already hold both capabilities. Permission is analyzable by **graph reachability**. [Source: Miller 2006 §9.2.5; Agorics "Capability Myths Demolished"]
- **Four acquisition paths** (Miller's "Rule of Acquisition"): **initial conditions, parenthood (creation), endowment, introduction (message passing)**. Mutation alone cannot acquire a reference. [Source: Miller 2006 §9.2.1-9.2.4]
- **Unforgeability depends on memory safety.** Even knowing Carol's memory address, Bob cannot synthesize a reference to Carol - one of four pointer-safety properties (integrity, confidentiality, unforgeability, unspoofability) that safe-language references have and C/C++ pointers lack. The guarantee is *contingent* on language-level memory safety and non-forgeable references. [Source: Miller 2006]
- **Object-capability patterns are wrapper/closure constructions** (e.g. a read-only forwarder) that hide private state from untrusted linked code, formalized as *robust safety*: a program exporting only properly-wrapped values cannot have its invariants violated by any untrusted environment. [Source: Swasey, Garg, Dreyer, OOPSLA 2017, DOI 10.1145/3133913]
- **Revocation and attenuation** use the **caretaker pattern** (Redell, 1974) and the **membrane pattern** (Marc Stiegler): a membrane wraps an object subgraph so that revoking the membrane's caretaker revokes *all* references that passed through it - **transitive revocation** ("all caretakers revoke together"). [Source: verified, 3-0; "transitive" is a faithful paraphrase, not Miller-verbatim]

**The load-bearing caveat for Vaked:** every one of these guarantees is a *runtime, reference-level* property contingent on a memory-safe object graph. Vaked has no such runtime object graph for agents; it has a *compiled topology* and *OS/kernel boundaries*. The theory is the vocabulary, not the implementation.

## 2. What the sandbox primitives actually give (external, verified)

- **Bubblewrap (bwrap)** is a coarse, configuration-driven sandbox: Linux user/mount/pid/net namespaces, seccomp filters, and bind-mounted filesystem views. It ships **no built-in security policy** and is **explicitly not a complete sandbox** and **not an ocap runtime** - it gives namespace/FS/seccomp isolation, never per-reference capability attenuation or revocation. [Source: bubblewrap README; Arch man page]
- **Nix flakes / reproducibility.** `flake.lock` pins every input to a content hash; closures are pinned; sandboxed builds aim at bit-identical outputs, reducing environment drift. But reproducibility is **empirical/probabilistic, not a hard guarantee**, and it is **build-time, not run-time** - **reproducibility is not isolation**. [Source: official Nix docs]

**Consequence:** a sandbox (Bubblewrap) bounds *what a process can touch*; reproducibility (Nix) bounds *what was built*. Neither is object-capability attenuation. Vaked's runtime membranes are of the *sandbox* family, and its provenance is of the *reproducibility* family - so the chapter must not claim ocap revocation from either.

## 3. What a Vaked membrane actually is (repo-grounded, status-labeled)

| Membrane aspect | Vaked reality | Status |
|---|---|---|
| **Proxy shell** (Miller forwarding proxy) | Not used. Vaked enforces directly via eBPF/namespaces, not by wrapping references. | **ABSENT** |
| **Attenuation rules** | Type-checked partial order on grants; `granted(receiver) <= granted(sender)` along every delegation edge. Compile-time only. [docs/language/THREAT_MODEL.md Rule 2; 0011 §4] | **IMPLEMENTED (static)** |
| **Delegation tree** | Mesh edges form the authority-flow graph; the checker enforces monotone (non-increasing) authority. | **IMPLEMENTED (static)** |
| **Revocation state** | Vaked specifies authority *statically*; mid-execution revocation is a runtime membrane op, "not Vaked's job" - deferred to the OTP supervisor + Zig daemons. [THREAT_MODEL.md §1.3] | **DESIGN-ONLY** |
| **Audit emission** | Every enforcement decision testifies to the `eventd` append-only hash-chained log; tamper-evident. [agent_guardd/evidence.py; eventd/] | **IMPLEMENTED** |

**The network membrane today.** `agent_guardd` owns the `network`/`ebpf` membranes: deny-by-default egress (`policy.py: decide()` - allow-rule match wins, else deny; non-IP host denied as un-attestable). The eBPF program is **loaded and verifier-probed but not left attached as the live enforcer** (the userspace reference datapath is authoritative today; the allow-set-aware cgroup/skb program is the follow-on). So the honest claim is: *deny-by-default egress is enforced in userspace and testified to eventd; kernel-level eBPF enforcement is probed, not live.* [agent_guardd/policy.py, bpf.py, docs/runtime/agent-guardd.md] [IMPLEMENTED (userspace) / DESIGN-ONLY (live eBPF)]

**Bubblewrap in Vaked:** deferred. `sandboxd` (process membrane) uses **raw namespaces/cgroups**, not bwrap. [docs/superpowers/specs/2026-06-13-sandboxd-design.md] [ABSENT/deferred]

## 4. Threat model

| # | Threat | Mitigation layer | Status | Citation |
|---|--------|------------------|--------|----------|
| T1 | Agent declares authority it was never granted | Compile-time attenuation check (`granted(r) <= granted(s)`) rejects the graph before lowering | IMPLEMENTED (static) | THREAT_MODEL Rule 2 |
| T2 | Agent exceeds granted egress at runtime | `agent_guardd` deny-by-default egress; non-allow-listed destination dropped | IMPLEMENTED (userspace) | policy.py |
| T3 | Compromised daemon tampers with the audit trail | `eventd` hash chain; any byte change breaks the chain | IMPLEMENTED | eventd/core.py, verify.py |
| T4 | Compromised agent must lose authority mid-flight (revocation) | OTP supervisor revokes the daemon's membrane | DESIGN-ONLY | THREAT_MODEL §1.3 |
| T5 | Forged kernel-level egress enforcement bypass | eBPF cgroup attach as live per-destination enforcer | DESIGN-ONLY | agent-guardd.md |
| T6 | Peer impersonation across hosts | SPIFFE/SPIRE SVID checked at TLS before frame parse (identity, NOT attenuation) | DESIGN-ONLY | RFC 0006 |
| T7 | Authority leaks via state-dependency frames | `DependencyRegistration` carries topology epoch, no capability grant; preceptord decides admission | DESIGN-ONLY | RFC 0004, 0005 |
| T8 | Build/env drift smuggles unverified bytes | Nix flake.lock pinning + provenance.json chain (reproducibility, NOT isolation) | IMPLEMENTED (provenance) | GOALS.md, lower.py |

## 5. Membrane lifecycle (state diagram)

This is the *daemon-enforcement* lifecycle, not an ocap proxy lifecycle. Revocation states are DESIGN-ONLY.

```
            compile (vakedc)                 boot (agent-supervisord)
   .vaked  ----------------->  membrane spec  ----------------->  [ARMED]
   topology   attenuation                JSON / supervisor index      |
   (T1 gate)  checked                                                 | request egress
                                                                      v
                                                          decide(host,port)  --deny--> [DENIED] -> testify(eventd)
                                                                      | allow
                                                                      v
                                                              [PERMITTED] -> testify(eventd)
                                                                      |
                          (DESIGN-ONLY) supervisor revoke / RewindEvent
                                                                      v
                                                              [REVOKED] -> membrane re-armed or daemon restarted
```

States ARMED / DENIED / PERMITTED are IMPLEMENTED (userspace datapath + eventd). REVOKED is DESIGN-ONLY (OTP supervisor, RFC 0004 §6 RewindEvent pauses; it does not auto-retry-loop - it pauses until explicit recovery).

## 6. Capability attenuation examples

Attenuation in Vaked is a **type-system partial order**, checked at compile time:

```
# delegation edge sender -> receiver must satisfy granted(receiver) <= granted(sender)

fs.repo_rw  >  fs.repo_ro            # read-write strictly dominates read-only
@orchestrator{grant=fs.repo_rw} -> @worker{grant=fs.repo_ro}   # OK: attenuates
@orchestrator{grant=fs.repo_ro} -> @worker{grant=fs.repo_rw}   # REJECTED at check time: amplification
```

This is the *static analogue* of the ocap read-only-wrapper pattern (Swasey/Garg/Dreyer): instead of a runtime forwarder that drops the write method, Vaked's checker proves the receiver's grant is a lower bound before lowering. **No runtime proxy exists** - the guarantee is "the compiled topology never grants amplification", enforced afterward by the daemons that materialize each grant.

## 7. Stress tests (honest answers)

- **An agent leaks a reference.** In ocap theory this is contained: a capability is unforgeable, and the leak only transfers authority the leaker already held (Rule of Connectivity). In *Vaked* there is no runtime reference to leak - authority is the compiled topology + daemon-enforced membranes. Leaking a *secret/handle* is a runtime-secret problem (out of the membrane model); the membrane still denies egress the topology never granted. **Vaked does not get ocap's leak-containment for free** - it gets coarse egress denial. [Inference, grounded in T1/T2]
- **A membrane is revoked mid-tool-call.** DESIGN-ONLY today. Per RFC 0004 §6, a RewindEvent does not loop or retry-count; it voids the anchor and the consumer re-enters verification and **pauses until explicit recovery** (handled by `agent-supervisord`, outside MLIR). Vaked has no transitive ocap revocation; revocation is daemon/supervisor-level and currently unimplemented. [DESIGN-ONLY: RFC 0004, THREAT_MODEL §1.3]
- **What is unforgeable in practice?** Not agent references (there are none at runtime). What is tamper-evident is the **eventd hash chain** (cryptographic, IMPLEMENTED) and **PQC-signed provenance** (RFC 0007, DESIGN). The ocap notion of unforgeable references requires a memory-safe object graph Vaked does not have; the practical unforgeability is *evidentiary* (the log), not *referential*. [IMPLEMENTED (log) / theory-contingent]
- **What must each layer enforce separately?**
  - **Compiler (vakedc):** attenuation/POLA, acyclicity, depth bounds - reject amplifying or malformed topologies (T1). [IMPLEMENTED]
  - **Runtime daemons (Zig/Python ref):** the per-kind membranes - egress deny-by-default, fs mounts, process namespaces (T2). [IMPLEMENTED userspace / DESIGN-ONLY Zig+eBPF-live]
  - **Kernel (eBPF):** evidence + (future) live per-destination egress enforcement (T5). [DESIGN-ONLY live]
  - **Supervisor (OTP):** lifecycle, restart, and revocation (T4). [DESIGN-ONLY]

## 8. Implementation invariants for .hcplang

`.hcplang` has **no capability primitive**; `@cap=network` is a *generic attribute* (the grammar accepts any `@ident(args)`), and capability *semantics* live in `preceptord`, not the language. [INTERNAL: protocol/hcplang/grammar.ebnf; RFC 0001 capability-scoping prose] The invariants a Vaked frame layer must hold (today by convention, candidates for enforcement):

1. **Frame header carries no grant.** Authority is decided by `preceptord` from the proven SPIFFE identity, not from frame fields (RFC 0006: identity checked at TLS before parse). [DESIGN]
2. **`@cap` is advisory until parsed.** A `@cap=network` annotation is a policy hint; it MUST be evaluated by `preceptord` before dispatch, never trusted as self-asserted authority. [INTERNAL]
3. **Attenuation is proven upstream, not in the frame.** The wire layer transports; it does not attenuate. Per-reference attenuation is explicitly out of the wire model. [Inference, consistent with RFC 0003 "frame body is opaque"]
4. **Audit is mandatory, not optional.** Every admitted frame's effect testifies to eventd; non-canonical frames are frame-level errors, not chained. [INTERNAL: RFC 0001 §canonicality]

## 9. Honest summary

Vaked is a **compile-time-attenuated, daemon-enforced, evidence-audited** authority system that **borrows ocap vocabulary** but **does not implement runtime object capabilities**. Its real guarantees today: static POLA proof (IMPLEMENTED), deny-by-default userspace egress (IMPLEMENTED), tamper-evident audit (IMPLEMENTED). Its aspirational guarantees: live eBPF enforcement, revocation, PQC-sealed provenance (all DESIGN-ONLY). What it categorically lacks: ocap proxy shells and transitive revocation (ABSENT). Stating this boundary is the security claim - everything stronger would be hand-waving.

## Appendix: sources

External (deep-research, adversarial 3-0 unless noted; abstain-safe applied):
- Miller, *Robust Composition* (PhD, JHU, May 2006) - [erights.org/talks/thesis](http://www.erights.org/talks/thesis/), [PDF mirror](https://worrydream.com/refs/Miller_2006_-_Robust_Composition.pdf)
- Miller/Yee/Shapiro, *Capability Myths Demolished* - [Agorics PDF](https://papers.agoric.com/assets/pdf/papers/capability-myths-demolished.pdf)
- Swasey, Garg, Dreyer, *Robust and Compositional Verification of Object Capability Patterns*, OOPSLA 2017 - [DOI 10.1145/3133913](https://dl.acm.org/doi/10.1145/3133913)
- Bubblewrap - README + Arch man page (namespace/seccomp sandbox, not a complete sandbox, no built-in policy)
- Nix flakes / reproducibility - official Nix docs (flake.lock content-hash pinning; reproducibility is build-time, empirical, not isolation)
- Caretaker pattern (Redell 1974); membrane pattern (Marc Stiegler) - transitive revocation
- Refuted (1-2): arXiv:1907.07154 as canonical origin - it is a secondary 2019 report; do not cite as foundational.
- Abstained (fetch failed, NOT refuted): erights.org direct (ECONNREFUSED) and JHU handle (403) - corroborated via mirrors.

Internal (repo-grounded, file:line in body): RELATED_WORK.md, THREAT_MODEL.md (Rule 2, §1.3), 0011-type-system.md, PROJECT_CONTEXT.md, agent_guardd/{policy,bpf,evidence,verify}.py, eventd/, RFC 0001/0004/0005/0006/0007, sandboxd design spec, protocol/hcplang/grammar.ebnf.

Method note: external claims passed 3-vote adversarial verification; rate-limited/forbidden fetches were marked ABSTAIN (never auto-refuted) and corroborated via mirrors. Internal claims are labeled IMPLEMENTED / DESIGN-ONLY / ABSENT so no aspirational capability reads as a runtime guarantee.
