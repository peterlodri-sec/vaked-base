# Changelog

All notable changes to Vaked are documented here. This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Comprehensive evaluation suite: benchmarking harness, determinism oracle, case studies
- Research documentation: RELATED_WORK.md and THREAT_MODEL.md positioning Vaked against prior systems
- SECURITY.md: security model, threat analysis, vulnerability reporting process
- CONTRIBUTING.md: grammar-first design discipline, testing guidelines, PR process
- Examples: operator-field.vaked, agentfield-swe.vaked, memory.vaked with POLA verification
- Provenance tracking (§6.2 of 0012): artifact-to-source mapping for auditable infrastructure
- Deterministic lowering: byte-identical artifact generation across runs

### Changed
- (none yet — v0.1 is the first release)

### Removed
- (none yet)

### Fixed
- (none yet)

## [v0.1] — 2026-06-30 (Planned)

### Added
- **Language (Goal 1):** Grammar v0.3 EBNF fully specified; all primitives implemented
  - `runtime`, `fiber`, `index`, `catalog`, `stream`, `mesh`, `surface`, `device`, `mediaPipeline`, `parallel`
  - Structured typing with record/list/scalar/path types
  - Schema conformance with closed refinement constraints
  
- **Type System (Goal 2):** Decidable, side-effect-free checking
  - Structural conformance checking (§1.1 of 0011)
  - Closed constraint set: `in`, `oneof`, `matches`, bounds, `required`/`optional`/`default`
  - Capability taxonomy with partial-order attenuation (§4 of 0011)
  - POLA enforcement: use-check and delegation-attenuation rules
  - Generics support: `Index<T>`, `Catalog<T>`, `Stream<T>`, `Fiber<I,O>`, `Mesh<Node,Edge>`
  
- **Compiler (Goal 3):** Deterministic multi-target lowering
  - Parse: lexer (NFC gate) + parser (PEG-ordered recursive descent)
  - Resolve: symbol table + ref resolution
  - Elaborate: schema/capability registry + defaults
  - Check: conformance + constraints + POLA (0011 §6 four-stage pipeline)
  - Lower: pure graph-to-text rendering (0012 §1–6)
    - Targets: `flake.nix` (Nix spine, §4), `gen/RUNTIME.md`, `gen/zig/*.json` (fiber configs), `gen/catalog/*.jsonl` (indexes), `provenance.json` (§6.2)
    - Deferred emitters (stubs): eBPF policy, OTel config, systemd units, surface launchers
  
- **Verification & Tests:**
  - Differential oracle: vakedc accept/reject verdict matches EBNF recognizer
  - Golden snapshots: LPG and lowering output verified against hand-authored fixtures
  - Determinism oracle: repeated compilation produces byte-identical artifacts
  - Spec coverage: tests for all 0011/0012 rules (positive and negative cases)

- **Documentation:**
  - Design series (0001–0016): language manifesto, primitives, type system, lowering, RFCs
  - README.md: project overview, repo structure, quick start
  - SECURITY.md: security model and threat analysis
  - CONTRIBUTING.md: grammar-first discipline, testing, PR process
  - RELATED_WORK.md: positioning against Nickel, CUE, Dhall, OPA, SPIFFE, MLIR, Nix
  - THREAT_MODEL.md: POLA guarantees, attack scenarios, runtime enforcement boundaries

- **Case Studies & Evaluation:**
  - `operator-field.vaked`: simple orchestration (2 fibers, 2 capability domains)
  - `agentfield-swe.vaked`: multi-principal SWE agents (8 fibers, complex delegation, generics)
  - `memory.vaked`: observability/tracing (eBPF domain extension, typed streams)
  - Benchmark suite: parse/check/lower timing, artifact sizes, determinism verification
  - Baseline results: 19/19 examples parse/check/lower deterministically (< 100ms each stage for typical 1500-line files)

### Changed
- (initial release)

### Removed
- (initial release)

### Known Limitations
- **Vaked is research software.** The language and compiler are not stable; breaking changes may occur between releases without deprecation notice until v1.0.
- **Zig daemons and eBPF enforcement are not yet implemented.** Until they exist, POLA is verified statically but not enforced at runtime.
- **vakedc is a Python prototype.** Not production-hardened; performance acceptable for typical declarations (~1500 lines) but may not scale to very large configs.
- **No revocation model.** The type system does not model capability revocation during execution; this is a runtime OTP supervisor responsibility.

## Roadmap

| Version | Target | Scope |
|---------|--------|-------|
| **v0.2** | 2026-10-31 | Zig daemon implementations (sandboxd, agent-guardd, eventd) with syscall enforcement |
| **v0.3** | 2026-12-31 | eBPF policy layer for audit and enforcement |
| **v1.0** | 2027-03-31 | Production hardening: Rust rewrite, formal verification, security audit |

---

## Format Notes

This changelog follows [Keep a Changelog](https://keepachangelog.com/) conventions:

- **Added:** New features
- **Changed:** Changes in existing functionality
- **Removed:** Deprecated or removed features
- **Fixed:** Bug fixes
- **Deprecated:** Features marked for removal in a future release
- **Security:** Security-related fixes and announcements

Releases with a version number are stable snapshots. Unreleased changes are subject to change.
