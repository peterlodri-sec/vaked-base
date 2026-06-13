# vaked-base

**The foundation monorepo for the Vaked agentic-runtime ecosystem.**

> Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.

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
| `docs/runtime/` | **runtime** (stub) | Runtime architecture + daemon responsibilities |
| `protocol/` | **protocol** (stub) | HCP / Litany wire protocol — `rfcs/`, daemon + tool roster |
| `docs/protocol/` | **protocol** (stub) | HCP / Litany overview |
| `vaked-agents/` | **agents** | The Vaked agent fleet — `ci/pr-review` (advisory CI reviewer); roadmap in [`vaked-agents/BACKLOG.md`](vaked-agents/BACKLOG.md) |
| `tools/ralph/` | **tooling** | `ralph` — autonomous per-model decision loop over Vaked concept tracks (see [`tools/ralph/README.md`](tools/ralph/README.md)) |
| `hosts/` | infra | `vakedos` — the bare-metal NixOS **materialization target** (Vultr EPYC 4345P). Deploy guide: [`DEPLOY.md`](DEPLOY.md) |
| `flake.nix` | infra | Dev shell (Zig, BEAM/OTP, Rust-to-build-CrabCC, tooling) + `nixosConfigurations.vakedos` |
| `.mcp.json` | infra | Project MCP servers (github, context7, repowise, workspace-fs, playwright) |
| `.claude/skills/` | infra | Project skills: `vaked-language-author`, `hcp-rfc-author` |

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

Current state at a glance — what's real, in flight, and ahead — as a graph: [`docs/context/TIMELINE.md`](docs/context/TIMELINE.md).

This is a **scaffold**. The language track (`vaked/`, `docs/language/`) carries real design content. The runtime (`daemons/`) and protocol (`protocol/`) subtrees are **indexed stubs** — each subsystem gets its own design → plan → implementation cycle. Nothing here is implemented yet beyond the dev shell and the language design docs.

See [`docs/superpowers/specs/2026-06-08-vaked-base-scaffold-design.md`](docs/superpowers/specs/2026-06-08-vaked-base-scaffold-design.md) for the scaffold's design record, and [`CLAUDE.md`](CLAUDE.md) for working conventions (including the environment **patch-doctor** runbook).

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
