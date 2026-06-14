# WP3 + WP4 Kickoff Batch — Master Synthesis & Foundation Report

Date: 2026-06-14. Author: synthesis + completeness critic. Repo: `/tmp/vaked-base`.
Scope: tie the verified WP3-S1 / WP4-S1 foundation code to the full WP3 (HCP wire) +
WP4 (daemon MVP) sprint roadmap and the cross-cutting CI/workspace fixes.

> Constraint context: build target `dev-cx53` is OFF-LIMITS for 6h. All claims below are
> qualified as **M1-verified-now**, **claimed-by-subagent (pending parent verify)**, or
> **dev-cx53-only**. The kickoff docs' "RFC 0002 §4 / Appendix A" wording is **stale**;
> the real byte encoding is RFC 0002 **§6**, golden vectors live in worked examples
> **§6.1.1 / §6.3.1 / §6.6.1 / §6.7.1 / §10 / §10.1**, and the frame header is the WIRE
> layer's (RFC 0003), explicitly **not** hcpbin (RFC 0002 §4.2 + §6 scope note). Appendix A
> exists but is Zig/Erlang *codegen* examples, not vectors.

## 1. Foundation state (what is actually on disk vs. claimed)

| Foundation | On-disk now | Local verify result |
|---|---|---|
| `protocol/hcp/hcpbin/src/lib.rs` (WP3-S1 impl) | PRESENT (real `Reader`/`Writer` codec, not stub) | `cargo test` => **50 passed, 3 suites** on M1. Verified now. |
| `protocol/hcp/hcpbin/tests/golden.rs` (WP3-S1 tests) | PRESENT | Compiles + passes under the same run. Verified now. |
| `daemons/sandboxd/src/policy.zig` + `policy_test.zig` (WP4-S1) | **ABSENT** — only the stub `main.zig` is on disk | Cannot verify locally; subagent claims 14/14 tests, zig 0.16.0. |
| `daemons/sandboxd/build.zig` + `build.zig.zon` (WP4-S1 corrected) | on-disk `.zon` is the OLD stub | Current on-disk `.zon` **fails to parse** under local zig 0.16.0 (`.name = "sandboxd"` string; 0.16 wants enum-literal `.name = .sandboxd` + a `.fingerprint`). The WP4-S1 foundation's job is to replace it. |

**hcpbin (WP3-S1) is real, green, and self-consistent on M1.** It implements RFC 0002
§6.1 (minimal/strict LEB128 + zig-zag with declared-width `k`), §6.4 (strict `bool`),
§6.1 `bytes`, and §6.5 `hash` (length-prefixed, registry-validated for known algos,
opaque round-trip for unknown). The lib.rs scope note correctly disclaims string/float,
aggregates, and the frame header. The golden tests are written blind to the impl
(adversarial independence) and assert the exact §6.1.1 hex.

**sandboxd (WP4-S1) is asserted-but-not-on-disk in my transcript.** I have a one-line
claim, not the code. The single concrete on-disk signal is that the *stub it replaces*
does not build under local zig 0.16.0. That is evidence about the stub, not about the
foundation — but it means the parent MUST confirm the corrected `build.zig.zon` parses
under zig 0.16.0 before any PR leaves draft (see Risks).

## 2. WP3 roadmap — HCP wire protocol (Rust `litany` + `hcpbin`)

The verified S1 primitive codec is the base of a clean dependency spine. Deferred hcpbin
work (string/NFC, f32/f64, records, defaults, lists/maps, unions, enums, uuid, timestamp)
is fully enumerated by `rfc0002-to-tasks-matrix` and split across two plans:
`hcpbin-string-float-plan` (string@Unicode-15.1.0 + f32/f64 canonicalisation) and
`hcpbin-aggregate-plan` (records/frames, unions, lists/maps, enums).

| Sprint | Deliverable (corrected RFC anchors) | Verification tier |
|---|---|---|
| WP3-S1 ✅ | hcpbin primitives — RFC 0002 **§6.1/§6.4/§6.5** (NOT §4) | M1 cargo test, done |
| WP3-S2 | Litany **frame** codec — RFC **0003 §4** (frame header kind/corr/stream/seq/end lives here, not hcpbin); + deferred hcpbin scalars/aggregates | M1, claimed spec |
| WP3-S3 | Message routing — Votive demux + RFC 0004 lifecycle gate; trait seams for S4/S5; Python differential oracle | M1, spec on disk |
| WP3-S4 | `hcp.control` wire codec — RFC 0005 (7 control frames) + ControlPlane binding + hand-derived goldens | M1 |
| WP3-S5 | eventd integration (Litany ↔ append-only hash-chained log) | M1 oracle; **carries the JSON-vs-frame-bytes chain contradiction (see Risks)** |
| WP3-S6 | Docs + perf baseline (hcpbin vs protobuf/CBOR, ≤10µs/frame) | M1 docs; **≤10µs target is dev-cx53-only** |
| WP3-S7 | Wire hardening + fuzz/proptest/stress | M1 logic; stress dev-cx53 |
| WP3-S8 | Integration spec + #113 paper eval | M1 wire-size; conformance gated on OQ1 |

The "RFC 0002 §4 / Appendix A" correction is carried by **WP3-S6** and the
**rfc0002-to-tasks-matrix** (which also schedules a docs-fix for issue #167 and both
kickoff docs).

## 3. WP4 roadmap — daemon MVP (Zig)

| Sprint | Deliverable | Verification tier |
|---|---|---|
| WP4-S1 | sandboxd build shell + CLI/policy skeleton | claimed M1 (zig build test); NOT on disk |
| WP4-S2 | sandboxd isolation backend — namespaces + cgroups v2 + seccomp-bpf (pure Zig); RFC 0001 §5 / RFC 0004 §6,§3.1 | M1 compile-only (`-Dtarget=x86_64-linux`); namespace/cgroup effects dev-cx53/Linux |
| WP4-S3 | agent-supervisord OTP skeleton — one_for_one, oracle-port bridge | M1 vs devshell |
| WP4-S4 | eventd Zig port — byte-identical to Python ref across 11 goldens; eBPF skeleton | M1 goldens; eBPF dev-cx53 |
| WP4-S5 | capability enforcement hooks (sandboxd + supervisord + eventd); guardd/memoryd oracles | M1 logic |
| WP4-S6 | NixOS VM integration (3 daemons on vakedos config) | Linux-only live gate; M1 oracle/compile slice |
| WP4-S7 | vakedos deploy test (#114) — nixosTest, 3-tier split | dev-cx53/Linux |

The `sandboxd-seccomp-plan` resolves the design's network-namespace / cgroup-ownership
Open item and defines the cgroup-v2-leaf ↔ agent_guardd eBPF attach coordination contract.

## 4. Cross-cutting fixes (these gate the whole batch's credibility)

1. **CI vacuous-green (issue #7) — CONFIRMED REAL.** I inspected `.github/workflows/ci-gate.yml`:
   its jobs are Python smoke/spec/ralph + nix-parse/nix-check/agent-guard only. **There is
   no `cargo test` and no `zig build` job anywhere in CI.** Every Rust and Zig deliverable in
   both work packages is currently un-built and un-tested by CI — a PR that breaks hcpbin or
   sandboxd would go green. `ci-gate-build-extension` (adds real cargo-test for `protocol/hcp`
   + zig-build for `daemons`, plus `classify.py` path-group fixes) is therefore not optional
   polish; it is the precondition that makes every other WP3/WP4 acceptance criterion
   enforceable. Sequence it first.
2. **No root Cargo workspace — CONFIRMED.** There is no root `Cargo.toml`; `hcpbin` is a lone
   crate with its own manifest. `cargo-workspace` (members `protocol/hcp/*`, swe-af excluded,
   wired into the nix devShell) is the structural pre-start gate so the crates build under
   `nix develop` and so the new CI cargo-test job has a workspace to target. Acceptance is
   structural (`cargo metadata` + `cargo check --workspace`), not test-pass — correct framing.
3. **Stale §4/Appendix-A references.** Carried by WP3-S6 + the matrix; must also patch issue
   #167 and both kickoff plan files (lines 24/41/43 of wp3-kickoff still say "§4" / "Appendix A").

## 5. Dependency spine (build order)

```
cargo-workspace + ci-gate-build-extension   (pre-start gates; do first)
        │
WP3-S1 hcpbin primitives ✅ ── string-float-plan ─┐
        │                       aggregate-plan ───┤── WP3-S2 frame codec (RFC 0003 §4)
        │                                          └── §10/§10.1 worked frames
        ▼                                                    │
WP3-S3 routing ── WP3-S4 control ── WP3-S5 eventd bridge ◀───┘  (JSON-vs-bytes reconcile)
WP4-S1 sandboxd shell ── WP4-S2 isolation+seccomp ── WP4-S3 supervisord
WP4-S4 eventd Zig port ──(shared §6.8 corpus, UNOWNED)── WP4-S5 caps ── WP4-S6/S7 integration
```

The WP3-S5 eventd bridge and WP4-S4 eventd Zig port both depend on hcpbin canonicality
(§6.8/§9). Their byte agreement is the §6.8 cross-impl requirement — currently **unassigned**
(see Missing).
