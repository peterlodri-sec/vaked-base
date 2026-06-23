# vaked-base

**The foundation monorepo for the Vaked agentic-runtime ecosystem.**

> Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.

## 📰 Recent news

**2026-06-13 — `swe_af` runs for real.** The lowered `workflow swe_af`
(`agentfield-swe.vaked` → `gen/workflow/swe_af.json`) is now executable: label an
issue `agent` and a GitHub-Actions pipeline runs `plan → code → review → publish`,
opening an advisory PR with every node testified to an [`eventd`](eventd) hash chain.
POLA is preserved end-to-end — the [`swe-af`](vaked-agents/ci/swe-af/README.md) agent
authors plan + code read-only (no GitHub token), and only the broker step writes
(`gh pr create`). The intended `dev-cx53` control-panel deploy is a follow-up runbook;
the GHA path is what's reachable and live. Design:
[`docs/superpowers/specs/2026-06-13-swe-af-gha-runner-design.md`](docs/superpowers/specs/2026-06-13-swe-af-gha-runner-design.md).

**2026-06-13 — the first end-to-end vertical slice landed ([#107](https://github.com/peterlodri-sec/vaked-base/pull/107)), one-shot by an agent.** A `network` egress membrane now goes declare → lower → load real eBPF → enforce → testify → verify. From the [PR disclaimer](https://github.com/peterlodri-sec/vaked-base/pull/107#issuecomment-4699358410):

> New **CI-triggered** and **cron-triggered** agents now run inside GitHub Actions on this repo, and a **self-hosted control plane on `crabcc.app`** is starting to get plugged into the same loop. […] Most of this work was one-shot […] by **Claude Code** […]. Where the sandbox kernel refused the cgroup-BPF attach, the daemon reports it and falls back to the reference datapath rather than faking in-kernel enforcement.

Peter's footnotes:

> _I asked for one vertical slice and got a kernel-eBPF spelunking expedition with a tamper-evident audit log — overdelivery is a hell of a drug._ (Peter)

> _The CI bots now peer-review each other while I supply the coffee and the occasional existential dread._ (Peter)

> _We declared a membrane, Nix materialized absolutely nothing yet, and it still passed CI — ship it._ (Peter)

Vaked is a flake-native **capability-graph language** for agentic, native, mesh-aware, parallel systems. It describes reproducible agent systems — runtime membranes, capability graphs, indexes, fibers, native surfaces, and mesh/device interactions — and compiles into ordinary Nix flakes, NixOS modules, Zig daemon configs, eBPF policy manifests, OpenTelemetry config, generated docs, and CrabCC indexes.

```text
Vaked source → typed semantic graph → generated artifacts
  ├── flake.nix / NixOS modules        (Nix materializes)
  ├── Zig daemon configs               (Zig enforces)
  ├── eBPF policy manifests            (eBPF testifies)
  ├── OTel collector config
  ├── CrabCC indexes / catalogs        (CrabCC indexes)
  └── docs
→ NixOS host → OTP supervision plane → Zig enforcement daemons → eBPF evidence → operator surfaces
```

## Repository map

| Path | Status | What lives here |
|------|--------|-----------------|
| `vaked/` | **language** | The Vaked language itself — `grammar/` (EBNF), `schema/`, `examples/` |
| `vakedc/` | **language** | `vakedc` — the prototype front-end: lexer + parser → Labeled Property Graph + type checker (0011 stages 1–4) + lowering (0012). Pipeline **parse → check → lower**: `python3 -m vakedc parse <file>`; `python3 -m vakedc check <file> [--json]`; `python3 -m vakedc lower <file> [--out DIR]` (checks first; refuses to emit on any diagnostic; writes `flake.nix`, `gen/…`, `provenance.json`) |
| `docs/language/` | **language** | Design series (`0001`-manifesto … `0008`-parallelism … `0010`-mirageos) + `references/` |
| `docs/context/` | **context** | `PROJECT_CONTEXT.md` — the canonical overview |
| `prompts/` | **context** | `dedicated-language-session.md` — kickoff prompt for the language-only session |
| `daemons/` | **runtime** (stub) | Roster of the OTP + Zig runtime daemons; per-daemon dirs land later |
| `eventd/` | **runtime** | Python reference impl of the append-only, hash-chained event log (the audit spine) |
| `agent_guardd/` | **runtime** | Python reference impl of `agent-guardd` — the `network`/`ebpf` membrane. Closes the first **end-to-end vertical slice**; see [`docs/runtime/agent-guardd.md`](docs/runtime/agent-guardd.md) |
| `docs/runtime/` | **runtime** (stub) | Runtime architecture + daemon responsibilities |
| `protocol/` | **protocol** (stub) | HCP / Litany wire protocol — `rfcs/`, daemon + tool roster |
| `docs/protocol/` | **protocol** (stub) | HCP / Litany overview |
| `vaked-agents/` | **agents** | The Vaked agent fleet — `ci/pr-review` (advisory CI reviewer); roadmap in [`vaked-agents/BACKLOG.md`](vaked-agents/BACKLOG.md). Fleet index: [`VAKED_AGENTS.md`](VAKED_AGENTS.md) |
| `tools/ralph/` | **tooling** | `ralph` — autonomous per-model decision loop over Vaked concept tracks (see [`tools/ralph/README.md`](tools/ralph/README.md)) |
| `hosts/` | infra | `vakedos` — the bare-metal NixOS **materialization target** (Vultr EPYC 4345P). Deploy guide: [`DEPLOY.md`](DEPLOY.md) |
| `flake.nix` | infra | Dev shell (Zig, BEAM/OTP, Rust-to-build-CrabCC, tooling) + `nixosConfigurations.vakedos` |
| `.mcp.json` | infra | Project MCP servers (github, context7, repowise, workspace-fs, playwright) |
| `.claude/skills/` | infra | Project skills: `vaked-language-author`, `hcp-rfc-author` |
| `docs/wiki/` | **docs** | [Minimal project wiki](docs/wiki/Home.md) — about, architecture, getting started |
| `vakedc/passes/` | **compiler** | **MLIR-mirror pass pipeline** — Stage-0 Python reference for the planned MLIR topology compilation. Pass 1 (topology analysis: cycle + depth + bound), Pass 2 (WAL injection per RFC 0004 §3.1), Pass 3 (AOT supervisor index gen). CLI: `python3 -m vakedc passes file.vaked --json` |
| `vakedc/mlir/` | **compiler** | **Stage-1 MLIR dialect definitions** — TableGen `.td` specs + C++ registration for the `vaked` and `hcp` MLIR dialects. Build: `bash tools/build-mlir-stage1.sh` (generates .inc files from LLVM/MLIR source). See `docs/context/DEV_GUIDE.md` |
| `docs/context/DEV_GUIDE.md` | **docs** | **Developer guide** for the compiler/MLIR layer — grammar, vakedc pipeline, pass pipeline, Stage-1 MLIR build, test corpus, contribution workflow |
| `tools/build-mlir-stage1.sh` | **tooling** | Zero-dep build script: fetches LLVM 19, builds mlir-tblgen, runs TableGen on dialect specs. Supports NixOS (`nix-shell`) and apt-based systems |
| `tools/vaked-mlir.py` | **tooling** | MLIR dev tool: `check` (validate .td files), `current-env` (versions), `build` (nix build), `sync <host>` (scp + remote build) |

## Developer Notes

> **This is a research and experimental project. Do not use in production.**

**Latest development:** This codebase is actively developed by a distributed team. Latest commits may not be from the repository owner (@peterlodri-sec); pull requests and contributions are welcomed. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and the [recruitment issue](https://github.com/peterlodri-sec/vaked-base/issues/141) (WP3 + WP4 engineers, June 24 start).

- **Bare-metal target only.** Vaked deploys to a bare-metal NixOS host. See [`DEPLOY.md`](DEPLOY.md) for hardware requirements and the deployment procedure.
- **No conventional OS support.** Vaked cannot be installed on macOS, standard Linux distributions, Windows, or WSL. The runtime requires direct kernel and eBPF access available only on a properly provisioned NixOS host.
- **Project scope.** This project encompasses three interrelated tracks: a capability-graph language (Vaked), a purpose-built operating system (vakedos — NixOS + OTP + Zig + eBPF), and a set of reference designs (daemons, wire protocol, agent fleet, tooling). They are designed as a cohesive whole; components are not independently installable.
- **No stability guarantees.** The language grammar, type system, compiler IR, and wire protocol are under active design. Breaking changes happen without notice.
- **Prototype compiler.** `vakedc` is a design-stage prototype. It may refuse valid programs, change its output format, or emit incorrect artifacts at any time.
- **Runtime is a stub.** The OTP supervision plane, Zig daemons, and eBPF policy layer are indexed stubs. Nothing deploys end-to-end yet beyond the dev shell and language tooling.
- **Nix is required.** The dev shell requires Nix with flakes enabled. The runtime target requires NixOS. There is no non-Nix install path.
- **eBPF kernel requirements.** eBPF policy enforcement requires a Linux kernel with BTF and CO-RE support (≥ 5.15). This is satisfied by the vakedos config but must be verified on any other host.
- **No package-manager install.** There is no `pip install`, `cargo install`, or `npm install` path. All tooling is consumed through `nix develop`.
- **Unsupported / research-only.** This is a personal research project with no SLA, support channels, or stability commitments.

## Start here

```text
docs/context/PROJECT_CONTEXT.md
docs/language/README.md
docs/language/0008-parallel-fibers-indexes-surfaces.md
prompts/dedicated-language-session.md
```

## Status

[![spec-tests](https://github.com/peterlodri-sec/vaked-base/actions/workflows/spec-tests.yml/badge.svg)](https://github.com/peterlodri-sec/vaked-base/actions/workflows/spec-tests.yml)

Verification dashboard: `python3 tools/specdash/build.py --serve`

**Latest:** ✅ MLIR pass pipeline (Stage-0 Python) shipped — 3 passes (topology → WAL → AOT index). CLI: `python3 -m vakedc passes`. Stage-1 MLIR dialect TableGen specs + build script in `vakedc/mlir/` and `tools/build-mlir-stage1.sh`. Differential corpus: 10/10 fixtures.  
**Verification:** `scripts/benchmark-100k-scalability.py` ([docs/language/0014-verification-scaffold.md](docs/language/0014-verification-scaffold.md))  
**Paper:** Language + evaluation ready for arxiv (PR #103, ~2–3 weeks to submission)  
**MLIR dev guide:** `docs/context/DEV_GUIDE.md` — comprehensive developer guide for the compiler & MLIR layer

Current state at a glance — what's real, in flight, and ahead — as a graph: [`docs/context/TIMELINE.md`](docs/context/TIMELINE.md).

This is a **scaffold**. The language track (`vaked/`, `docs/language/`) carries real design content. The runtime (`daemons/`) and protocol (`protocol/`) subtrees are mostly **indexed stubs** — each subsystem gets its own design → plan → implementation cycle.

One **end-to-end vertical slice** is now closed, though: a `network` egress membrane declared in Vaked ([`vaked/examples/membrane/agent-egress.vaked`](vaked/examples/membrane/agent-egress.vaked)) is **lowered** to a policy (`gen/ebpf.policy.json`, the realized 0012 §7 `ebpf.policy` emitter), **enforced** by the `agent-guardd` reference impl ([`agent_guardd/`](agent_guardd) — which compiles + loads a real `cgroup/skb` eBPF program and enforces deny-by-default egress), **testified** onto the [`eventd`](eventd) hash chain, and **verified** to have held. Run it with `task slice`; details in [`docs/runtime/agent-guardd.md`](docs/runtime/agent-guardd.md).

See [`docs/superpowers/specs/2026-06-08-vaked-base-scaffold-design.md`](docs/superpowers/specs/2026-06-08-vaked-base-scaffold-design.md) for the scaffold's design record, and [`CLAUDE.md`](CLAUDE.md) for working conventions (including the environment **patch-doctor** runbook).

## MLIR Compiler Layer — Stage 0 (Python) + Stage 1 (MLIR C++)

The Vaked compiler pipeline has a dedicated MLIR-mirror pass layer for multi-agent
topology compilation. See `docs/context/DEV_GUIDE.md` for the full developer guide.

### Stage 0 — Python reference passes (Working ✅)

Three passes that mirror the planned MLIR dialects:

```bash
python3 -m vakedc passes vaked/examples/operator-field.vaked --json
```

| Pass | MLIR Spec | What it does | Diagnostics |
|------|-----------|-------------|-------------|
| **1 — TopologyAnalysis** | 0021 | DFS cycle detection, critical-path depth, maxDepth bound | `E-WORKFLOW-CYCLE`, `E-WORKFLOW-DEPTH` |
| **2 — WALInjection** | 0022 | Inject WAL frames per dependency edge (RFC 0004 §3.1) | — (structural) |
| **3 — AOTIndexGeneration** | 0023 | Emit `gen/workflow/<name>.json` supervisor index | — (codegen) |

**Differential corpus:** 10/10 fixtures pass (4 determinism + 4 pass pipeline + 2 rejection).

### Stage 1 — MLIR TableGen + C++ (Build script ready ⚠️)

The `vakedc/mlir/` directory holds the MLIR dialect definitions and build
infrastructure. Two dialects fully specified:

| Dialect | Spec | Types | Ops | File |
|---------|------|-------|-----|------|
| `vaked` | 0019 | `!vaked.state_hash`, `!vaked.agent_id`, `!vaked.state<S>` | `agent`, `yield`, `execute_step`, `consume`, `execute_with_dep` | `VakedDialect.td` (247 lines) |
| `hcp` | 0020 | `!hcp.token`, `!hcp.hash`, `!hcp.data<T>` | `create_registration_token`, `write_ahead_log`, `fetch_canonical_data`, `rewind_scope` | `HcpDialect.td` (235 lines) |

**Build:** `bash tools/build-mlir-stage1.sh` on dev-cx53 — fetches LLVM 19 source,
builds `mlir-tblgen`, generates `.inc` files. C++ compilation is deferred due to
an MLIR 19 ODS include pattern issue (`GET_OP_CLASSES` vs `GET_TYPEDEF_LIST`
collision on `MLIR_DEFINE_EXPLICIT_TYPE_ID`).

**Fix applied:** A post-process step (`grep -v MLIR_DEFINE_EXPLICIT_TYPE_ID`)
generates filtered `*Types.cpp.inc` files for the type-only include path. The
remaining issue is that `GET_OP_CLASSES` itself generates type IDs that conflict
with the `.h.inc` declarations. The fix is to generate separate `.inc` files for
op declarations vs definitions using two distinct `mlir-tblgen` invocations, or
to patch `AddMLIR.cmake` to emit type IDs in a separate guarded block.

**Dev tool:** `python3 tools/vaked-mlir.py` — `check`, `current-env`, `build`, `sync`.

### How the pipeline fits together

```
.vaked source → vakedc parse → check → lower (artifacts)
                                            │
                                            ▼
                                   Pass 1 (topology analysis)
                                            │
                                            ▼
                                   Pass 2 (WAL injection)
                                            │
                                            ▼
                                   Pass 3 (AOT index gen)
                                            │
                                            ▼
                              gen/workflow/<name>.json
                              (supervisor index → agent-supervisord)
```

The Stage-0 Python passes serve as the **reference oracle** that Stage-1 MLIR
must reproduce byte-for-byte (0024 §2.1 observational equivalence). The diff
test harness in `tests/corpus/0024-differential/` validates both stages.

## Dogfooding — the `ralph` decision loop

[`tools/ralph/`](tools/ralph/README.md) is an autonomous, budget-capped loop that
continuously surfaces the most important open **decision** for each hard design
area (one OpenRouter model pinned per area) and appends it to a human-ratified,
hash-chained decision log. It dogfoods Vaked's own theories before they land in
the language — **parallel** (round-robins tracks), **immutable** (append-only
event ledger as the state-of-record), and **control** (pause/slow/step at
runtime) — and runs cheaply as a scheduled CI tick. See
[`tools/ralph/README.md`](tools/ralph/README.md) for tracks, commands, and the
CI host.


## Social

- 🐘 [@vakedbot@social.crabcc.app](https://social.crabcc.app/@vakedbot) — Mastodon bot for releases + updates
