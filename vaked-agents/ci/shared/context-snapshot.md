<!-- generated 2026-06-14 from GOALS.md · TIMELINE.md · rfcs/ · ROADMAP · events.jsonl — do not edit manually -->
## Vaked project status

**Snapshot:** 2026-06-13 · **Grammar:** v0.3 · **Front-end:** `vakedc` (parse → check → lower)

### Phases (milestone map)
- Phase 0 🟡 (4/6): Language foundation
- Phase 1 ⬜ (0/4): Compiler maturity
- Phase 2 ⬜ (0/4): Runtime: stubs → real
- Phase 3 ⬜ (0/3): Wire protocol
- Phase 4 ⬜ (0/3): Surfaces and observability
- Phase 5 ⬜ (0/3): Language v1

### Work packages
  WP1 ✅: Language (EBNF, grammar, v0.3) (n/a)
  WP2 ✅: Compiler (vakedc, Python) (n/a)
  WP3 ⏳: Wire Protocol (Litany, RFC 0002–0006 impl) (16 weeks)
  WP4 ⏳: Daemon MVP (sandboxd, agent-supervisord, eventd) (12 weeks)
  WP5 📋: Formalization (optional, scope TBD) (TBD)
  WP6 📋: Materialization (vakedos integration) (post-WP4)

### Protocol RFCs (all Draft)
  0001 RFC 0001 — HCP (Harness Control Protocol)
  0002 RFC 0002 — `.hcplang` (HCP schema language)
  0003 RFC 0003 — Litany Wire (HCP transport & framing)
  0004 RFC 0004 — Multi-Agent State Dependency (registration, GC, rewind)
  0005 RFC 0005 — Control-Plane Frames (pause / resume / slow / step / rewind)
  0006 RFC 0006 — Transport Identity & Distribution (the inter-host fabric)
  0007 RFC 0007 — Post-Quantum Litany & Sealed Image-as-Code Attestation

### Ralph decision tracks
  base-language-spec
  graph-concept
  mlir-topology
  hcp-litany

### Area labels → file paths
  area/language: vaked/ grammar · schema · examples
  area/compiler: vakedc/ parse → check → lower
  area/docs: docs/ design series · context · references
  area/protocol: protocol/ HCP/Litany RFCs · wire formats
  area/runtime: daemons/ OTP · Zig · eBPF
  area/agents: vaked-agents/ CI + fleet agents

### Recent ralph decisions (last 5, chronological)
  graph-concept iter 2 ($0.0215)
  mlir-topology iter 2 ($0.0117)
  hcp-litany iter 2 ($0.0464)
  base-language-spec iter 2 ($0.0421)
  graph-concept iter 3 ($0.0237)

