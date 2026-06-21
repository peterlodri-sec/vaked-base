# Master Research Index — Vaked Ecosystem

> Auto-generated 2026-06-16 from live repository state.  
> Covers all documentation artifacts across `docs/`, `vaked/`, `protocol/`, `prompts/`, and top-level reference files.

---

## 1. Project Fundamentals (start here)

| File | Description |
|------|-------------|
| `README.md` | Front-page overview, repo map, recent news, core stack diagram |
| `GOALS.md` | Vision, milestones (Phase 0–5), design convictions |
| `ROADMAP_2026-2027.md` | Aggressive-staffing timeline: WP1–WP6, arxiv targets, engineer recruitment |
| `CHANGELOG.md` | v0.1 planned features: language, type system, compiler, verification |
| `SECURITY.md` | Security model: POLA guarantees vs non-guarantees, threat model pointer |
| `CONTRIBUTING.md` | Grammar-first discipline, testing guidelines, PR process |
| `LICENSE` | License file |
| `DEPLOY.md` | vakedos bare-metal NixOS host deployment guide |
| `VAKED_AGENTS.md` | Agent fleet index: active + proposed agents, triggers, models, workflows |
| `REVIEW_MAP.md` | Optimization pass on #103, commit-by-commit, agent lanes |
| `docs/context/PROJECT_CONTEXT.md` | Canonical overview: stack, mantra, runtime membranes, language identity |
| `docs/context/TIMELINE.md` | Chronological development timeline |

---

## 2. Language Design (the Vaked language itself)

### 2.1 Core Design Series (`docs/language/`)

| # | File | Topic |
|---|------|-------|
| 0001 | `docs/language/0001-language-manifesto.md` | Why Vaked exists, design principles |
| 0003 | `docs/language/0003-reference-map.md` | Reference map of the language |
| 0008 | `docs/language/0008-parallel-fibers-indexes-surfaces.md` | Parallel fibers, indexes, surfaces |
| 0009 | `docs/language/0009-kickoff-context-for-dedicated-session.md` | Kickoff context for dedicated language session |
| 0010 | `docs/language/0010-mirageos-unikernel-surface.md` | MirageOS unikernel surface |
| 0011 | `docs/language/0011-type-system.md` | Type system: structural conformance, POLA, generics |
| 0012 | `docs/language/0012-lowering.md` | Lowering: graph→artifacts pass |
| 0013 | `docs/language/0013-mlir-topology-compilation.md` | MLIR topology compilation |
| 0014 | `docs/language/0014-memory-primitive.md` | Memory primitive design |
| 0014 | `docs/language/0014-verification-scaffold.md` | Verification scaffold |
| 0015 | `docs/language/0015-workflow.md` | Workflow primitive |
| 0016 | `docs/language/0016-substrate-candidates.md` | Substrate candidates |
| 0017 | `docs/language/0017-namespace-roster.md` | Namespace roster |
| 0018 | `docs/language/0018-crypto-seal-capability-domain.md` | Crypto seal capability domain |
| 0019 | `docs/language/0019-mlir-vaked-dialect.md` | MLIR Vaked dialect (untracked) |
| 0020 | `docs/language/0020-mlir-hcp-dialect.md` | MLIR HCP dialect (untracked) |
| 0021 | `docs/language/0021-mlir-pass-topology-analysis.md` | MLIR pass: topology analysis (untracked) |
| 0022 | `docs/language/0022-mlir-pass-wal-injection.md` | MLIR pass: WAL injection (untracked) |
| 0023 | `docs/language/0023-mlir-pass-aot-supervisor-index.md` | MLIR pass: AOT supervisor index (untracked) |
| 0024 | `docs/language/0024-mlir-lowering-staged-adoption.md` | MLIR lowering staged adoption (untracked) |

### 2.2 Language Reference

| File | Description |
|------|-------------|
| `docs/language/README.md` | Language docs overview |
| `docs/language/RELATED_WORK.md` | Prior systems and how Vaked compares |
| `docs/language/THREAT_MODEL.md` | Formal POLA statement, attack scenarios |
| `docs/language/references/parallel-reference-pack.md` | Parallel reference pack |
| `docs/language/references/session-2026-06-08-sparks.md` | Sparks from 2026-06-08 session |
| `docs/language/reviews/0024-publication-review.md` | Publication review of 0024 |

### 2.3 Grammar & Schema (`vaked/`)

| File | Description |
|------|-------------|
| `vaked/grammar/vaked-v0-plus.ebnf` | Canonical EBNF grammar (v0.3, 29 kinds) |
| `vaked/grammar/README.md` | Grammar overview |
| `vaked/schema/builtins.vaked` | Built-in type declarations in Vaked |
| `vaked/schema/parallel-types.md` | Parallel types schema documentation |

### 2.4 Examples (`vaked/examples/`)

| File | Description |
|------|-------------|
| `vaked/examples/agentfield-swe.vaked` | SWE agent field workflow declaration |
| `vaked/examples/crabcc-umami.vaked` | CrabCC Umami analytics declaration |
| `vaked/examples/editorial-pipeline.vaked` | Editorial pipeline declaration |
| `vaked/examples/operator-field.vaked` | Operator field declaration |
| `vaked/examples/redteam-swarm.vaked` | Red-team swarm declaration |
| `vaked/examples/supply-chain-pipeline.vaked` | Supply chain pipeline declaration |
| `vaked/examples/swe-swarm-100k-workers-scalability.vaked` | 100k workers scalability test |
| `vaked/examples/swe-swarm-1m-workers-scalability.vaked` | 1M workers scalability test |
| `vaked/examples/swe-swarm-loadtest.vaked` | SWE swarm loadtest |
| `vaked/examples/types/` | Type example declarations |
| `vaked/examples/namespace/` | Namespace example declarations |
| `vaked/examples/lowering/` | Lowering example declarations |
| `vaked/examples/lowering-agentfield/` | AgentField lowering examples |
| `vaked/examples/primitives/` | Primitive example declarations |
| `vaked/examples/engines/` | Engine example declarations |
| `vaked/examples/containers/` | Container example declarations |
| `vaked/examples/membrane/` | Membrane example declarations |

---

## 3. Compiler (`vakedc` + `vakedz`)

### 3.1 Python Front-end (`vakedc/`)

| File | Description |
|------|-------------|
| `vakedc/README.md` | vakedc overview: parse→check→lower pipeline |
| `vakedc/__init__.py` | Package init |
| `vakedc/__main__.py` | CLI entry point |
| `vakedc/lexer.py` | Lexer (NFC gate) |
| `vakedc/parser.py` | Parser (PEG-ordered recursive descent) |
| `vakedc/graph.py` | Labeled Property Graph construction |
| `vakedc/check.py` | Type checker (stages 1–4) |
| `vakedc/resolve.py` | Symbol table + ref resolution |
| `vakedc/lower.py` | Lowering: graph→artifacts |
| `vakedc/emit.py` | Artifact emitters |
| `vakedc/lsp.py` | LSP server |

### 3.2 Zig Front-end (`vakedz/`)

| File | Description |
|------|-------------|
| `vakedz/README.md` | vakedz overview: cache-native Zig port |
| `vakedz/build.zig` | Zig build system |
| `vakedz/build.zig.zon` | Zig package manifest |
| `vakedz/src/` | Zig source (lexer + parser + checker + lowerer) |
| `vakedz/test/` | Zig test suite |

### 3.3 Compiler Documentation

| File | Description |
|------|-------------|
| `docs/compiler/OPTIMIZATION_ROADMAP.md` | Compiler optimization roadmap |

---

## 4. Wire Protocol (HCP / Litany)

### 4.1 RFC Series (`protocol/rfcs/`)

| RFC | File | Topic |
|-----|------|-------|
| 0001 | `protocol/rfcs/0001-hcp.md` | HCP: Hyper-Capability Protocol |
| 0002 | `protocol/rfcs/0002-hcplang.md` | hcplang: wire protocol description language |
| 0003 | `protocol/rfcs/0003-litany-wire.md` | Litany: wire format |
| 0004 | `protocol/rfcs/0004-multi-agent-state-dependency.md` | Multi-agent state dependency |
| 0005 | `protocol/rfcs/0005-control-frames.md` | Control frames |
| 0006 | `protocol/rfcs/0006-transport-identity-distribution.md` | Transport, identity, distribution |
| 0007 | `protocol/rfcs/0007-post-quantum-litany-sealed-image.md` | Post-quantum Litany sealed image |

### 4.2 Protocol Implementation

| File | Description |
|------|-------------|
| `protocol/README.md` | Protocol overview |
| `protocol/hcplang/grammar.ebnf` | hcplang grammar |
| `protocol/hcplang/examples/` | hcplang examples |

---

## 5. Runtime Daemons

### 5.1 Daemon Designs

| File | Description |
|------|-------------|
| `daemons/README.md` | Daemon roster overview |
| `docs/runtime/README.md` | Runtime overview |
| `docs/runtime/agent-guardd.md` | agent-guardd: network/eBPF membrane design |

### 5.2 Reference Daemons (Python stubs)

#### `agent_guardd/` — Network/eBPF Membrane

| File | Description |
|------|-------------|
| `agent_guardd/__init__.py` | Package init |
| `agent_guardd/__main__.py` | CLI entry point |
| `agent_guardd/bpf.py` | eBPF program management |
| `agent_guardd/enforce.py` | Policy enforcement |
| `agent_guardd/evidence.py` | Evidence collection |
| `agent_guardd/policy.py` | Policy definitions |
| `agent_guardd/verify.py` | Verification |

#### `eventd/` — Append-only Hash-chained Event Log

| File | Description |
|------|-------------|
| `eventd/__init__.py` | Package init |
| `eventd/__main__.py` | CLI entry point |
| `eventd/core.py` | Core event chain |
| `eventd/log.py` | Log management |
| `eventd/runtime.py` | Runtime |
| `eventd/statedep.py` | State dependency |

#### `agent_memoryd/` — Memory Daemon

| File | Description |
|------|-------------|
| `agent_memoryd/__init__.py` | Package init |
| `agent_memoryd/__main__.py` | CLI entry point |
| `agent_memoryd/capability.py` | Capability management |
| `agent_memoryd/daemon.py` | Daemon core |
| `agent_memoryd/eventd.py` | Event integration |
| `agent_memoryd/store.py` | Memory store |

#### `agent_sandboxd/` — Sandbox Daemon

| File | Description |
|------|-------------|
| `agent_sandboxd/__init__.py` | Package init |
| `agent_sandboxd/__main__.py` | CLI entry point |
| `agent_sandboxd/cgroup.py` | cgroup management |
| `agent_sandboxd/daemon.py` | Daemon core |
| `agent_sandboxd/eventd.py` | Event integration |
| `agent_sandboxd/namespace.py` | Namespace management |
| `agent_sandboxd/policy.py` | Policy definitions |

---

## 6. Design Decisions (`docs/decisions/`)

| File | Description |
|------|-------------|
| `docs/decisions/RATIFY.md` | Ratification process |
| `docs/decisions/base-language-spec.ralph-log.md` | Ralph decision log: base language spec |
| `docs/decisions/graph-concept.ralph-log.md` | Ralph decision log: graph concept |
| `docs/decisions/hcp-litany.ralph-log.md` | Ralph decision log: HCP/Litany |
| `docs/decisions/mlir-topology.ralph-log.md` | Ralph decision log: MLIR topology |

---

## 7. Specifications & Plans (`docs/superpowers/`)

### 7.1 Design Specs

| Date | File | Topic |
|------|------|-------|
| 2026-06-08 | `docs/superpowers/specs/2026-06-08-vaked-base-scaffold-design.md` | Initial scaffold design |
| 2026-06-09 | `docs/superpowers/specs/2026-06-09-vaked-grammar-v0.2-design.md` | Grammar v0.2 design |
| 2026-06-10 | `docs/superpowers/specs/2026-06-10-vaked-type-system-design.md` | Type system design |
| 2026-06-10 | `docs/superpowers/specs/2026-06-10-vakedc-checker-design.md` | vakedc checker design |
| 2026-06-10 | `docs/superpowers/specs/2026-06-10-vakedc-lower-design.md` | vakedc lower design |
| 2026-06-10 | `docs/superpowers/specs/2026-06-10-vakedc-parser-prototype-design.md` | vakedc parser prototype design |
| 2026-06-10 | `docs/superpowers/specs/2026-06-10-vaked-lowering-design.md` | Lowering design |
| 2026-06-11 | `docs/superpowers/specs/2026-06-11-ralph-decide-design.md` | Ralph decide design |
| 2026-06-12 | `docs/superpowers/specs/2026-06-12-agent-supervisord-design.md` | Agent supervisord design |
| 2026-06-12 | `docs/superpowers/specs/2026-06-12-control-plane-design.md` | Control plane design |
| 2026-06-12 | `docs/superpowers/specs/2026-06-12-eventd-design.md` | eventd design |
| 2026-06-12 | `docs/superpowers/specs/2026-06-12-otp-supervision-lowering-design.md` | OTP supervision lowering design |
| 2026-06-12 | `docs/superpowers/specs/2026-06-12-ralph-tracks-design.md` | Ralph tracks design |
| 2026-06-13 | `docs/superpowers/specs/2026-06-13-memoryd-design.md` | memoryd design |
| 2026-06-13 | `docs/superpowers/specs/2026-06-13-sandboxd-design.md` | sandboxd design |
| 2026-06-13 | `docs/superpowers/specs/2026-06-13-sealed-image-spike.md` | Sealed image spike |
| 2026-06-13 | `docs/superpowers/specs/2026-06-13-spire-pqc-design.md` | SPIRE PQC design |
| 2026-06-13 | `docs/superpowers/specs/2026-06-13-swe-af-gha-runner-design.md` | SWE AF GHA runner design |
| 2026-06-13 | `docs/superpowers/specs/2026-06-13-swe-economic-research-design.md` | SWE economic research design |
| 2026-06-13 | `docs/superpowers/specs/2026-06-13-vaked-swe-x402-service-design.md` | Vaked SWE X402 service design |
| 2026-06-13 | `docs/superpowers/specs/2026-06-13-vakedz-zig-frontend-design.md` | vakedz Zig frontend design |
| 2026-06-13 | `docs/superpowers/specs/2026-06-13-wasm-worker-isolation-design.md` | WASM worker isolation design |
| 2026-06-14 | `docs/superpowers/specs/2026-06-14-0024-differential-corpus-design.md` | 0024 differential corpus design |

### 7.2 Implementation Plans

| Date | File | Topic |
|------|------|-------|
| 2026-06-11 | `docs/superpowers/plans/2026-06-11-ralph.md` | Ralph implementation plan |
| 2026-06-12 | `docs/superpowers/plans/2026-06-12-ralph-tracks.md` | Ralph tracks implementation plan |
| 2026-06-13 | `docs/superpowers/plans/2026-06-13-swe-af-gha-runner.md` | SWE AF GHA runner plan |
| 2026-06-13 | `docs/superpowers/plans/2026-06-13-vakedz-zig-frontend.md` | vakedz Zig frontend plan |
| 2026-06-14 | `docs/superpowers/plans/2026-06-14-v1.0-followups-plan.md` | v1.0 follow-ups plan |

### 7.3 Research Notes

| File | Description |
|------|-------------|
| `docs/superpowers/research/2026-06-13-vakedz-fanout-research.md` | vakedz fanout research |

---

## 8. Research Papers (`docs/papers/`)

| File | Description |
|------|-------------|
| `docs/papers/vaked-language-v0.1.md` | Vaked language v0.1 paper (arxiv #103 target) |
| `docs/papers/vaked-security-membranes-architecture.md` | Security membranes architecture paper |
| `docs/papers/research-token-compression-agent-comms-2026.md` | Token compression for agent communications |
| `docs/papers/v1.0-artifact-governance.md` | v1.0 artifact governance |
| `docs/papers/v1.0-release-governance.md` | v1.0 release governance |

---

## 9. Infrastructure

| File | Description |
|------|-------------|
| `docs/infrastructure/1M-SCALABILITY-HARDWARE-SPEC.md` | 1M-worker scalability hardware spec |
| `docs/agents/ci.md` | CI agent details |
| `docs/agents/llmproxy-proposal.md` | LLM proxy proposal |
| `flake.nix` | Nix flake: dev shell + nixosConfigurations.vakedos |
| `pyproject.toml` | Python project config |
| `Taskfile.yml` | Task runner definitions |
| `deploy/llmproxy/config.yaml` | LLM proxy config |
| `deploy/llmproxy/docker-compose.yml` | LLM proxy Docker Compose |

---

## 10. Prompts & Agent Configurations

| File | Description |
|------|-------------|
| `prompts/dedicated-language-session.md` | Kickoff prompt for language-only session |
| `prompts/ci-agent-briefing.md` | CI agent briefing |
| `prompts/fix-all-issues.arp.md` | Fix-all-issues prompt (untracked) |
| `CLAUDE.md` | Claude Code project instructions (authoritative) |
| `CLAUDE.original.md` | Original CLAUDE.md (untracked) |
| `.claude/skills/` | Skill definitions (vaked-language-author, hcp-rfc-author, etc.) |
| `.deepseek/` | DeepSeek-specific config |

---

## 11. Test Infrastructure

| File | Description |
|------|-------------|
| `tests/smoke.py` | Smoke tests |
| `tests/test_memoryd.py` | memoryd tests |
| `tests/test_sandboxd.py` | sandboxd tests |
| `tests/spec/README.md` | Spec tests overview |
| `tests/spec/run_all.py` | Spec test runner |
| `tests/spec/ebnf.py` | EBNF recognizer tests |
| `tests/spec/test_vakedc.py` | vakedc integration tests |
| `tests/spec/test_vakedc_check.py` | vakedc checker tests |
| `tests/spec/test_vakedc_lower.py` | vakedc lowerer tests |
| `tests/spec/test_examples_parse.py` | Example parse tests |
| `tests/spec/test_agentfield_load.py` | AgentField load tests |
| `tests/spec/test_agentfield_lowering.py` | AgentField lowering tests |
| `tests/spec/test_lowering_fixtures.py` | Lowering fixtures tests |
| `tests/spec/test_otp_lowering.py` | OTP lowering tests |
| `tests/spec/test_eventd.py` | eventd tests |
| `tests/spec/test_agent_guardd.py` | agent-guardd tests |
| `tests/spec/test_grammar_selfcontained.py` | Grammar self-containment tests |
| `tests/spec/test_doc_links.py` | Doc link validation tests |
| `tests/spec/test_telebot.py` | Telebot tests |
| `tests/spec/test_yardmaster.py` | Yardmaster tests |
| `tests/spec/fixtures/` | Test fixtures |
| `tests/spec/golden/` | Golden test files |
| `tests/corpus/0024-differential/` | 0024 differential corpus (untracked) |

---

## 12. Tools & Scripts

| File | Description |
|------|-------------|
| `tools/ralph/` | Autonomous track decision loop |
| `tools/dockeeper/` | Doc/spec/RFC drift gate |
| `tools/yardmaster/` | Merge-train conductor |
| `tools/telebot/` | Telegram interactive control surface |
| `tools/diagrams/` | Diagram generation |
| `tools/seal/` | Crypto seal tooling |
| `tools/specdash/` | Spec dashboard |
| `tools/rfc-incoherence-hunter/` | RFC incoherence hunter |
| `tools/vaked-run.sh` | Vaked run script |
| `tools/vaked-run.ab` | Vaked run (AppBundle) |
| `scripts/benchmark-100k-scalability.py` | 100k scalability benchmark |
| `scripts/docs-validator.sh` | Doc validation script |
| `scripts/gather-context.sh` | Context gathering script |
| `scripts/network-membrane-slice.sh` | Network membrane slice script |
| `scripts/web-search.sh` | Web search script |
| `scripts/draft-toot.sh` | Mastodon draft script |
| `install.sh` | Install script |
| `generate_images.py` | Image generation |

---

## 13. CI/CD Workflows (`.github/workflows/`)

| Workflow | Purpose |
|----------|---------|
| `ci-gate.yml` | Smart CI gate with size-based tier scaling |
| `cleanup.yml` | Cleanup workflow |
| `corpus-0024.yml` | 0024 corpus workflow |
| `diagrams.yml` | Diagram generation |
| `docs-keeper.yml` | Doc drift gate |
| `label-tagger.yml` / `label-tagger-build.yml` | Auto-labeling |
| `merge-train.yml` | Merge train conductor |
| `pr-review.yml` / `pr-review-build.yml` / `pr-review-audit.yml` | PR review agent |
| `pr-self-checkin.yml` | PR self-check-in fallback |
| `provost.yml` / `provost-build.yml` | Product-owner coordination agent |
| `ralph-tracks.yml` | Ralph decision loop |
| `social-post.yml` | Mastodon social posting |
| `spec-tests.yml` | Spec test suite |
| `swe-af.yml` / `swe-af-build.yml` | SWE agent field |
| `telebot.yml` | Telegram bot |
| `telegram-post.yml` | Telegram posting |
| `vaked-ci-respond.yml` | @vaked-ci comment responder |
| `vakedz-ci.yml` | vakedz CI |

---

## 14. Sessions & History

| File | Description |
|------|-------------|
| `sessions/language-track/` | Historical language-track session logs |
| `vaked-agents/BACKLOG.md` | Agent fleet backlog |

---

## Quick Reference: By Research Interest

| Interest | Start here |
|----------|-----------|
| **Language design** | `GOALS.md` → `docs/language/0001-language-manifesto.md` → `vaked/grammar/vaked-v0-plus.ebnf` |
| **Type system / POLA** | `docs/language/0011-type-system.md` → `SECURITY.md` → `docs/language/THREAT_MODEL.md` |
| **Compiler architecture** | `vakedc/README.md` → `docs/language/0012-lowering.md` → `docs/compiler/OPTIMIZATION_ROADMAP.md` |
| **Wire protocol** | `protocol/README.md` → `protocol/rfcs/0001-hcp.md` → `protocol/rfcs/0003-litany-wire.md` |
| **Runtime / daemons** | `daemons/README.md` → `docs/runtime/README.md` → `docs/superpowers/specs/2026-06-12-eventd-design.md` |
| **Agent fleet** | `VAKED_AGENTS.md` → `docs/agents/ci.md` → `vaked-agents/BACKLOG.md` |
| **Scalability** | `docs/infrastructure/1M-SCALABILITY-HARDWARE-SPEC.md` → `vaked/examples/swe-swarm-1m-workers-scalability.vaked` |
| **Security** | `SECURITY.md` → `docs/language/THREAT_MODEL.md` → `docs/papers/vaked-security-membranes-architecture.md` |
| **Research papers** | `docs/papers/vaked-language-v0.1.md` → `docs/papers/vaked-security-membranes-architecture.md` |
| **Project management** | `ROADMAP_2026-2027.md` → `docs/context/PROJECT_CONTEXT.md` → `docs/decisions/RATIFY.md` |

---

*Total cataloged artifacts: 120+ files across 14 research domains.*
