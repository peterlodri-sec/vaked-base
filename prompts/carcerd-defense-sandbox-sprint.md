# Kickoff prompt — `carcerd` defense-sandbox research sprint (batch)

Paste this whole block into a dedicated vaked engineering session. It produces every
deliverable of the defense-sandbox track in one pass. It is self-contained: it states the
mission, the hard constraints, the prior-art corrections, and the acceptance criteria for
each artifact.

---

ROLE

You are a lead vaked runtime engineer. Your task is to scaffold the `carcerd` track: an
impenetrable agent defense-sandbox with active verification and a jail, built as
defense-in-depth on vaked's existing spine. You design and specify; you do not build compiled
daemons in this sprint.

HARD CONSTRAINTS (read before doing anything)

1. Conventions are law. Design and RFC first. Do not implement a daemon inline — scaffold its
   spec. Any versioned-language change (new grammar kind) starts as a GitHub issue, never an
   inline EBNF edit. Use the `hcp-rfc-author` skill for RFC work and the
   `vaked-language-author` skill for any grammar discussion.
2. Never build on the developer machine. No `zig build`, `cargo build`, `nix build`, tests, or
   any compile/link/test cascade locally. Builds and eBPF loads are gated to `dev-cx53` under
   the 3-gate verify-confirm protocol (target verification, intent confirmation, pre-flight).
   The adversarial harness is Python stdlib only and runs without a compile.
3. Stay on the designated feature branch. Commit each artifact with a clear message. Open one
   pull request when the batch is complete.

REQUIRED READING (ground yourself first)

- `CLAUDE.md`, `README.md`, `docs/context/PROJECT_CONTEXT.md` — the architecture and mantra.
- `agent_guardd/` — `policy.py` (`decide()`), `evidence.py` (`testify()`), `verify.py`. This
  is the verdict / testimony / conformance loop you will assert against and extend.
- `eventd/` — `core.py` (hash contract, `canonical_json`, `verify_chain`), `log.py`. The
  append-only evidence spine.
- `protocol/rfcs/0004-multi-agent-state-dependency.md` and `0005-control-frames.md` — the
  lifecycle and control-plane frames you will extend for the jail state.
- `protocol/rfcs/0007-post-quantum-litany-sealed-image.md` — sealed-image attestation.
- `daemons/sandboxd/` and `docs/runtime/README.md` — the namespace/seccomp enforcer and the
  daemon roster.

PRIOR-ART CORRECTIONS (must not be reintroduced)

A brainstorm input proposed a 4-layer sandbox. Keep the good parts, reject these as written:

- `LD_PRELOAD` is not a security boundary. It is attacker-controlled user space (static
  binaries, direct `syscall()`, and fresh `execve` bypass it). Use it only as an advisory,
  bypassable, evidence-emitting L1 layer. The real boundary is the kernel: seccomp + eBPF LSM
  + namespaces. Where enforcement matters, use `seccomp-unotify`, not preload.
- PPID is not proof of locality (re-parents to init, PID reuse). Use kernel-stable identity:
  cgroup id + `pidfd`, anchored by an eBPF LSM hook.
- A mutable in-memory KV store is not a source of truth. It contradicts the append-only
  deterministic-fold spine (`eventd`). At most it is an ephemeral materialized view of the
  fold.
- Fixed cache-line-aligned wire frames break Litany Wire canonicality (RFC 0003 is
  varint-length-prefixed) and therefore break hash determinism. Do not propose them.

CORRECTED LAYER MODEL (defense-in-depth)

- L1 cooperative — `LD_PRELOAD` / `seccomp-unotify` / Frida — advisory, bypassable,
  evidence-only — homes in a new `carcerd` shim and `mcp-brokerd`.
- L2 kernel jail — eBPF LSM + seccomp + namespaces/cgroups — the real boundary — `agent_guardd`,
  `sandboxd`.
- L3 active verification — continuous fold + jail-state transition + kill-switch —
  authoritative and replayable — `eventd`, `agent-supervisord`, RFC 0004/0005.
- L4 attestation — sealed-image + optional AMD SEV-SNP report — hardware root — RFC 0007,
  `hosts/vakedos`.

DELIVERABLES (produce all four, in this order)

1. `docs/runtime/carcerd-design.md` — the primary design doc. Must contain: the layer model
   above; the four workstreams below; and a "prior art and corrections" appendix capturing the
   rejected ideas so they are not reintroduced. Cross-link the RFCs and daemons it builds on.

2. `protocol/rfcs/0008-jail-control-frames.md` — extends RFC 0005. Specify a new `JAILED` /
   `QUARANTINE` lifecycle state, a `JailControl` control frame, the eBPF `bpf_send_signal`
   kill-switch semantics, and write-ahead logging of the jailing to eventd so it replays
   deterministically. Use the `hcp-rfc-author` skill; match the existing RFC structure and
   vocabulary.

3. `tests/adversarial/` — the jailbreak harness (workstream A), Python stdlib only, runnable
   on `dev-cx53` with no compile. A corpus of escape attempts: egress exfiltration,
   `/proc/<pid>/environ` and credential-file reads, `ptrace` attach, static-binary
   direct-syscall bypass, namespace/cgroup escape, secret read. For each attempt assert two
   things: it is blocked deny-by-default, and it produces a conforming testimony entry on the
   eventd hash chain. This is the operational proof of "impenetrable" — replace any
   "mathematically proven" hand-waving with a concrete 100%-block / 100%-conformance assertion.

4. A GitHub issue (not an inline EBNF edit) proposing the secret-scrub grammar kind for
   workstream D: credentials never enter the agent address space; a `seccomp-unotify` hook
   turns a raw secret read into `EACCES` plus testimony; `mcp-brokerd` holds the raw secret and
   the agent sees only a capability handle. Label it for the language track.

WORKSTREAMS (specify each in the design doc; B/C/E/F are design-only this sprint)

- A — adversarial harness (the proof). Delivered as item 3 above.
- B — kernel-true lineage attestation. eBPF LSM (`bprm_check_security` /
  `sched_process_exec`) binding each exec to cgroup id + `pidfd`, testified to eventd. Include
  the "ghost node" test: a process mimicking an agent signature but lacking a matching kernel
  lineage token is refused while the authorized process keeps logging.
- C — active jail state. The RFC 0008 extension (item 2). Continuous in-loop conformance: a
  capability violation drives the worker to `JAILED` and fires the kill-switch.
- D — secret-scrub membrane via `seccomp-unotify` (item 4 issue plus design section).
- E (stretch) — io_uring batched async append fast-path for eventd under 100k-worker load.
  Performance only; correct the "Ring 0 / zero syscall" framing.
- F (stretch) — SEV-SNP-grounded attestation closing RFC 0007's hardware gap on the EPYC
  `vakedos` host. Verify SEV-SNP availability before relying on it.

REUSE (do not re-invent)

`agent_guardd/{policy,evidence,verify}.py`; `eventd/core.py`; RFC 0004/0005 lifecycle;
`daemons/sandboxd/src/policy.zig`; planned `mcp-brokerd`.

ACCEPTANCE / DEFINITION OF DONE

- All four deliverables exist, committed on the feature branch, with a single pull request
  opened (ready for review, not draft).
- The design doc contains the corrections appendix; nothing in any artifact reintroduces a
  rejected idea.
- The adversarial harness runs on `dev-cx53` (no compile) and its assertions are stated as
  100% block plus 100% testimony conformance, with a deterministic-replay check that folds the
  eventd log and confirms the jail decision hashes identically.
- RFC 0008 matches the house RFC structure and cross-links RFC 0005 and RFC 0004.
- No build, compile, or eBPF load was run on the developer machine; any such step is gated to
  `dev-cx53` under the 3-gate protocol.

Begin by reading the required files, then produce the deliverables in order. Report a short
status checklist after each one.
