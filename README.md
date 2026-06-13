# vaked-base

**The foundation monorepo for the Vaked agentic-runtime ecosystem.**

> Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.

## 📰 Recent news

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

## Developer Notes

> **This is a research and experimental project. Do not use in production.**

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

Current state at a glance — what's real, in flight, and ahead — as a graph: [`docs/context/TIMELINE.md`](docs/context/TIMELINE.md).

This is a **scaffold**. The language track (`vaked/`, `docs/language/`) carries real design content. The runtime (`daemons/`) and protocol (`protocol/`) subtrees are mostly **indexed stubs** — each subsystem gets its own design → plan → implementation cycle.

One **end-to-end vertical slice** is now closed, though: a `network` egress membrane declared in Vaked ([`vaked/examples/membrane/agent-egress.vaked`](vaked/examples/membrane/agent-egress.vaked)) is **lowered** to a policy (`gen/ebpf.policy.json`, the realized 0012 §7 `ebpf.policy` emitter), **enforced** by the `agent-guardd` reference impl ([`agent_guardd/`](agent_guardd) — which compiles + loads a real `cgroup/skb` eBPF program and enforces deny-by-default egress), **testified** onto the [`eventd`](eventd) hash chain, and **verified** to have held. Run it with `task slice`; details in [`docs/runtime/agent-guardd.md`](docs/runtime/agent-guardd.md).

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
