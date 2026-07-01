# Cross-Reference Map — Vaked Documentation Graph

> How the documentation interconnects: design docs → RFCs → specs → code → tests.  
> Part of the `docs/research/` research onboarding package.  
> Companion to `MASTER_RESEARCH_INDEX.md` and `RESEARCH_SUMMARY.md`.

---

## Core Dependency Arcs

Each arc traces a design decision from abstract concept to concrete artifact.

### Arc 1: Language Manifesto → Grammar → Examples → Compiler

```
docs/language/0001-language-manifesto.md     (why Vaked exists, design principles)
    │
    ▼
vaked/grammar/vaked-v0-plus.ebnf            (canonical EBNF, 29 kinds)
    │
    ├──▶ vaked/schema/builtins.vaked         (built-in types in Vaked itself)
    ├──▶ vaked/schema/parallel-types.md      (parallel type schema docs)
    │
    ▼
vaked/examples/*.vaked                       (~19 example declarations)
    │
    ▼
vakedc/ (Python compiler)                    (lexer → parser → graph → check → lower)
    │
    ├──▶ tests/spec/test_vakedc.py           (integration tests)
    ├──▶ tests/spec/test_examples_parse.py   (example parse tests)
    └──▶ tests/spec/golden/                  (golden output fixtures)
```

### Arc 2: Type System (0011) → Checker → POLA → Security

```
docs/language/0011-type-system.md            (structural conformance, POLA, generics)
    │
    ├──▶ vakedc/check.py                     (type checker implementation, stages 1–4)
    │       │
    │       └──▶ tests/spec/test_vakedc_check.py
    │
    ├──▶ SECURITY.md                         (POLA guarantees vs non-guarantees)
    │       │
    │       └──▶ docs/language/THREAT_MODEL.md   (formal POLA, attack scenarios)
    │
    └──▶ docs/decisions/base-language-spec.ralph-log.md  (ratification log)
```

### Arc 3: Lowering (0012) → Emitters → Artifacts → Provenance

```
docs/language/0012-lowering.md               (pure, total, hermetic lowering design)
    │
    ├──▶ vakedc/lower.py                     (lowering orchestrator)
    ├──▶ vakedc/emit.py                      (artifact emitters)
    │
    ├──▶ Generated artifacts:
    │       ├── flake.nix / NixOS modules
    │       ├── gen/zig/*.json (Zig daemon configs)
    │       ├── gen/catalog/*.jsonl (CrabCC indexes)
    │       ├── gen/RUNTIME.md
    │       └── provenance.json
    │
    ├──▶ tests/spec/test_vakedc_lower.py     (lowering tests)
    └──▶ tests/spec/test_lowering_fixtures.py
```

### Arc 4: MLIR Pipeline (0013 + 0019–0024) → Future Compiler Path

```
docs/language/0013-mlir-topology-compilation.md     (MLIR topology overview)
    │
    ├──▶ docs/language/0019-mlir-vaked-dialect.md   (Vaked MLIR dialect)
    ├──▶ docs/language/0020-mlir-hcp-dialect.md     (HCP MLIR dialect)
    ├──▶ docs/language/0021-mlir-pass-topology-analysis.md
    ├──▶ docs/language/0022-mlir-pass-wal-injection.md
    ├──▶ docs/language/0023-mlir-pass-aot-supervisor-index.md
    └──▶ docs/language/0024-mlir-lowering-staged-adoption.md
            │
            └──▶ docs/compiler/OPTIMIZATION_ROADMAP.md
```

### Arc 5: Wire Protocol RFCs → hcplang → Implementation

```
protocol/rfcs/0001-hcp.md                     (Hyper-Capability Protocol)
    │
    ├──▶ protocol/rfcs/0002-hcplang.md        (wire description language)
    │       │
    │       └──▶ protocol/hcplang/grammar.ebnf
    │
    ├──▶ protocol/rfcs/0003-litany-wire.md    (wire format)
    ├──▶ protocol/rfcs/0004-multi-agent-state-dependency.md
    ├──▶ protocol/rfcs/0005-control-frames.md
    ├──▶ protocol/rfcs/0006-transport-identity-distribution.md
    ├──▶ protocol/rfcs/0007-post-quantum-litany-sealed-image.md
    │
    └──▶ docs/decisions/hcp-litany.ralph-log.md  (ratification log)
```

### Arc 6: Runtime Daemons — Design → Stub → Test

```
docs/runtime/README.md                        (runtime overview)
    │
    ├──▶ docs/runtime/agent-guardd.md         (network/eBPF membrane design)
    │       │
    │       └──▶ agent_guardd/                (Python reference stub)
    │               ├── bpf.py, enforce.py, evidence.py, policy.py, verify.py
    │               └──▶ tests/spec/test_agent_guardd.py
    │
    ├──▶ docs/superpowers/specs/2026-06-12-eventd-design.md
    │       │
    │       └──▶ eventd/                      (Python reference stub)
    │               ├── core.py, log.py, runtime.py, statedep.py
    │               └──▶ tests/spec/test_eventd.py
    │
    ├──▶ docs/superpowers/specs/2026-06-13-memoryd-design.md
    │       │
    │       └──▶ agent_memoryd/               (Python reference stub)
    │               └──▶ tests/test_memoryd.py
    │
    └──▶ docs/superpowers/specs/2026-06-13-sandboxd-design.md
            │
            └──▶ agent_sandboxd/              (Python reference stub)
                    └──▶ tests/test_sandboxd.py
```

### Arc 7: Agent Fleet — Design → Implementation → CI

```
VAKED_AGENTS.md                               (fleet index)
    │
    ├──▶ docs/agents/ci.md                    (CI agent details)
    │
    ├──▶ vaked-agents/BACKLOG.md              (proposed agents)
    │
    ├──▶ Active agent specs:
    │       ├── docs/superpowers/specs/2026-06-13-swe-af-gha-runner-design.md
    │       ├── docs/superpowers/specs/2026-06-12-ralph-tracks-design.md
    │       └── docs/superpowers/specs/2026-06-12-agent-supervisord-design.md
    │
    ├──▶ Implementation plans:
    │       ├── docs/superpowers/plans/2026-06-11-ralph.md
    │       ├── docs/superpowers/plans/2026-06-12-ralph-tracks.md
    │       └── docs/superpowers/plans/2026-06-13-swe-af-gha-runner.md
    │
    └──▶ CI workflows: .github/workflows/*.yml
            ├── pr-review.yml, swe-af.yml, ralph-tracks.yml
            ├── merge-train.yml, docs-keeper.yml
            └── label-tagger.yml, provost.yml
```

### Arc 8: Project Governance → Decisions → Roadmap

```
GOALS.md                                      (vision + milestones)
    │
    ├──▶ ROADMAP_2026-2027.md                 (aggressive staffing timeline)
    │
    ├──▶ docs/decisions/RATIFY.md             (ratification process)
    │       │
    │       └──▶ docs/decisions/*.ralph-log.md
    │               ├── base-language-spec.ralph-log.md
    │               ├── graph-concept.ralph-log.md
    │               ├── hcp-litany.ralph-log.md
    │               └── mlir-topology.ralph-log.md
    │
    └──▶ CHANGELOG.md                         (version history)
```

### Arc 9: Research Papers → Supporting Docs

```
docs/papers/vaked-language-v0.1.md            (arxiv #103 target)
    │
    ├──▶ docs/language/0001-language-manifesto.md
    ├──▶ docs/language/0011-type-system.md
    ├──▶ docs/language/0012-lowering.md
    ├──▶ docs/language/RELATED_WORK.md
    └──▶ scripts/benchmark-100k-scalability.py

docs/papers/vaked-security-membranes-architecture.md
    │
    ├──▶ SECURITY.md
    ├──▶ docs/language/THREAT_MODEL.md
    ├──▶ docs/runtime/agent-guardd.md
    └──▶ agent_guardd/

docs/papers/v1.0-artifact-governance.md
    │
    └──▶ docs/papers/v1.0-release-governance.md
```

---

## Spec → Design → Plan → Code Traceability

Every implementation artifact traces back to a spec, which traces back to a language design doc.

| Implementation | Spec (design) | Plan | Language Doc |
|---------------|---------------|------|-------------|
| `vakedc/lexer.py` | `2026-06-10-vakedc-parser-prototype-design.md` | — | `vaked-v0-plus.ebnf` |
| `vakedc/parser.py` | `2026-06-10-vakedc-parser-prototype-design.md` | — | `vaked-v0-plus.ebnf` |
| `vakedc/check.py` | `2026-06-10-vakedc-checker-design.md` | — | `0011-type-system.md` |
| `vakedc/lower.py` | `2026-06-10-vakedc-lower-design.md` | — | `0012-lowering.md` |
| `vakedc/emit.py` | `2026-06-10-vaked-lowering-design.md` | — | `0012-lowering.md` |
| `vakedz/` (Zig) | `2026-06-13-vakedz-zig-frontend-design.md` | `2026-06-13-vakedz-zig-frontend.md` | `vaked-v0-plus.ebnf` |
| `agent_guardd/` | `docs/runtime/agent-guardd.md` | — | — |
| `eventd/` | `2026-06-12-eventd-design.md` | — | — |
| `agent_memoryd/` | `2026-06-13-memoryd-design.md` | — | — |
| `agent_sandboxd/` | `2026-06-13-sandboxd-design.md` | — | — |
| `tools/ralph/` | `2026-06-11-ralph-decide-design.md` | `2026-06-11-ralph.md` | — |
| `tools/yardmaster/` | `2026-06-12-ralph-tracks-design.md` | `2026-06-12-ralph-tracks.md` | — |
| `swe-af` agent | `2026-06-13-swe-af-gha-runner-design.md` | `2026-06-13-swe-af-gha-runner.md` | `agentfield-swe.vaked` |
| `vakedos` host | `docs/infrastructure/1M-SCALABILITY-HARDWARE-SPEC.md` | — | `hosts/vakedos/`, `flake.nix` |

---

## RFC Interdependency Graph

```
0001-hcp ───────────────────────────────────────────────┐
  │ (defines the protocol)                              │
  ├──▶ 0002-hcplang (wire description language)          │
  │       │                                              │
  │       └──▶ protocol/hcplang/grammar.ebnf             │
  │                                                      │
  ├──▶ 0003-litany-wire (wire format)                    │
  │       │                                              │
  │       └──▶ protocol/hcplang/examples/                │
  │                                                      │
  ├──▶ 0004-multi-agent-state-dependency                 │
  │       │                                              │
  │       └──▶ relies on 0003 (Litany frames)            │
  │                                                      │
  ├──▶ 0005-control-frames                               │
  │       │                                              │
  │       └──▶ relies on 0003, 0004                      │
  │                                                      │
  ├──▶ 0006-transport-identity-distribution              │
  │       │                                              │
  │       └──▶ relies on 0003, 0005                      │
  │                                                      │
  └──▶ 0007-post-quantum-litany-sealed-image ◄───────────┘
          │
          └──▶ relies on 0003, 0006
          └──▶ docs/language/0018-crypto-seal-capability-domain.md
```

---

## Key Cross-Cutting Threads

### Thread: "From declaration to evidence"

```
.vaked source
  → vakedc parse (LPG)
    → vakedc check (POLA verified)
      → vakedc lower (artifacts emitted)
        → Nix builds daemons
          → OTP supervises
            → Zig enforces (eBPF loaded)
              → eventd testifies (hash-chained log)
                → surfaces reveal (operator dashboards)

Docs tracing this thread:
  GOALS.md → 0001 → 0011 → 0012 → 0012 §6.2
  → daemons/README.md → docs/runtime/agent-guardd.md
  → SECURITY.md → docs/language/THREAT_MODEL.md
```

### Thread: "The agent that builds itself"

```
vaked/examples/agentfield-swe.vaked     (declares the SWE agent workflow)
  → vakedc lower
    → gen/workflow/swe_af.json           (lowered workflow)
      → .github/workflows/swe-af.yml     (CI executes it)
        → swe-af agent runs              (plans, codes, reviews, publishes)
          → pr-review agent reviews      (another Vaked-declared agent)
            → eventd testifies            (evidence chain)

Docs tracing this thread:
  VAKED_AGENTS.md → agentfield-swe.vaked
  → 2026-06-13-swe-af-gha-runner-design.md
  → 2026-06-13-swe-af-gha-runner.md
  → swe-af.yml → pr-review.yml → eventd/
```

### Thread: "Scale from 1 to 1M workers"

```
vaked/examples/swe-swarm-100k-workers-scalability.vaked
vaked/examples/swe-swarm-1m-workers-scalability.vaked
  → scripts/benchmark-100k-scalability.py
    → 100k at 273ms avg parse, deterministic
      → docs/infrastructure/1M-SCALABILITY-HARDWARE-SPEC.md
        → EPYC 4345P, 256GB RAM, NVMe RAID
          → projected 1M workers

Docs tracing this thread:
  GOALS.md → ROADMAP_2026-2027.md
  → swe-swarm-*.vaked → benchmark-100k-scalability.py
  → 1M-SCALABILITY-HARDWARE-SPEC.md
```

---

## Document Type Taxonomy

| Type | Location | Count | Purpose |
|------|----------|-------|---------|
| **Language design** | `docs/language/0001–0024` | 22 | Why + how of language constructs |
| **Grammar** | `vaked/grammar/` | 1 EBNF | Canonical syntax |
| **Schema** | `vaked/schema/` | 2 | Built-in types, parallel types |
| **Examples** | `vaked/examples/` | ~19 | Real Vaked declarations |
| **RFCs** | `protocol/rfcs/` | 7 | Wire protocol specifications |
| **Specs** | `docs/superpowers/specs/` | 23 | Design specs for implementations |
| **Plans** | `docs/superpowers/plans/` | 5 | Implementation checklists |
| **Decisions** | `docs/decisions/` | 5 | Ratified architecture decisions |
| **Papers** | `docs/papers/` | 5 | Research papers for publication |
| **Context** | `docs/context/` | 2 | Overview + timeline |
| **Reference** | `docs/language/references/` | 2 | Reference packs, session sparks |
| **Runtime docs** | `docs/runtime/` | 2 | Daemon architecture |
| **Infrastructure** | `docs/infrastructure/` | 1 | Hardware specs |
| **Compiler docs** | `docs/compiler/` | 1 | Optimization roadmap |
| **Agent docs** | `docs/agents/` | 2 | CI + LLM proxy proposals |
| **Top-level** | Root `*.md` | 10 | README, GOALS, ROADMAP, SECURITY, etc. |

---

## How to Navigate the Graph

1. **If you have a research question** → Start with `RESEARCH_SUMMARY.md` for the domain entry point, then follow the arc in this map.
2. **If you're tracing a specific implementation** → Use the Spec → Design → Plan → Code table above.
3. **If you're reviewing a paper** → Follow Arc 9: Papers → Supporting Docs.
4. **If you're implementing a new daemon** → Follow Arc 6: Design → Stub → Test, then Arc 7 for CI integration.
5. **If you're writing a new RFC** → Follow Arc 5: check RFC interdependencies, then ratify via Arc 8.

---

*This cross-reference map is part of the `docs/research/` package alongside `MASTER_RESEARCH_INDEX.md` (full catalog) and `RESEARCH_SUMMARY.md` (executive overview).*
