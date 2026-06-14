# Vaked end-to-end demonstration — language → compiler → runtime, across swarms

Date: 2026-06-14 · Goal: *demonstrate the agentic-workflow language, compiler, and
runtime (Vaked) end-to-end on different swarms.*

This is the executable counterpart to the research batch: instead of arguing the
design is sound, it runs the full `vakedc` pipeline (`parse → check → lower`)
against nine existing swarm declarations and records what each produces. Every run
below is reproducible with the stdlib-only Python front-end — no external
toolchain.

## What "end-to-end" means here

```
.vaked source ──parse──▶ LPG ──check (0011)──▶ 0 diagnostics ──lower (0012)──▶ artifact tree
```

`lower` refuses to emit on any diagnostic, so a passing `lower` is itself the
proof that the graph type-checked. The artifacts are the runtime stack: a Nix
spine, an OTP supervision tree, per-fiber Zig daemon config, a workflow DAG, an
eventd replay contract, a CrabCC catalog, and a provenance manifest.

## Stage 1 — `check` across nine swarms (all clean)

```
swe-swarm-100k-workers-scalability       rc=0  no diagnostics
swe-swarm-1m-workers-scalability         rc=0  no diagnostics
swe-swarm-loadtest                       rc=0  no diagnostics
redteam-swarm                            rc=0  no diagnostics
supply-chain-pipeline                    rc=0  no diagnostics
agentfield-swe                           rc=0  no diagnostics
editorial-pipeline                       rc=0  no diagnostics
operator-field                           rc=0  no diagnostics
crabcc-umami                             rc=0  no diagnostics
```

Command: `python3 -m vakedc check vaked/examples/<name>.vaked`

Nine distinct agentic topologies — a 100k-worker SWE swarm, a 1M-worker swarm, a
red-team kill-chain, a supply-chain ceremony, the agentfield SWE loop, an
editorial pipeline, an operator field, and a CrabCC indexing pipeline — all type-
check against the same built-in capability catalog.

## Stage 2 — `lower` to artifacts (deterministic)

Command: `python3 -m vakedc lower vaked/examples/<name>.vaked --out <dir>`

| Swarm | Files | Notable artifacts |
|-------|------:|-------------------|
| swe-swarm-100k | 9 | `gen/otp/swe_swarm_100k_sup.erl`, `gen/workflow/swarmPipeline.json`, `gen/zig/miner.json` |
| swe-swarm-1m | 9 | `gen/otp/swe_swarm_1m_sup.erl`, `gen/workflow/swarmPipeline.json`, `gen/zig/miner.json` |
| redteam-swarm | 9 | `gen/otp/redteam_swarm_sup.erl`, `gen/workflow/killchain.json`, `gen/catalog/targetIntel.jsonl`, `gen/zig/evidenceMiner.json` |
| supply-chain-pipeline | 9 | `gen/otp/supply_chain_sup.erl`, `gen/workflow/ceremony.json`, `gen/zig/provenanceMiner.json` |
| agentfield-swe | 11 | `gen/otp/agent_field_sup.erl`, `gen/workflow/swe_af.json`, `gen/colmena/hive.nix`, `gen/memory/palace.json` |

Every tree carries the same spine — `flake.nix`, `gen/RUNTIME.md`,
`gen/eventd.json`, `gen/otp/vaked_fiber_worker.erl`, and `provenance.json` — plus
the per-swarm projections. The artifact count varies with the declaration
(agentfield-swe additionally lowers a Colmena hive and a memory-palace contract),
which is the point: artifacts are projections of the graph, not a fixed template.

## Stage 3 — the runtime layers, materialized

The tagline mapped to files emitted by the runs above:

| Layer | Mechanism | Artifact (example) |
|-------|-----------|--------------------|
| Vaked declares | typed capability graph | the `.vaked` source / LPG |
| Nix materializes | flake + NixOS modules | `flake.nix`, `gen/colmena/hive.nix` |
| OTP supervises | supervision tree | `gen/otp/<name>_sup.erl`, `vaked_fiber_worker.erl` |
| Zig enforces | per-fiber daemon config | `gen/zig/<miner>.json` |
| eBPF testifies | replay / evidence contract | `gen/eventd.json` |
| CrabCC indexes | source/intel catalog | `gen/catalog/*.jsonl` |
| Surfaces reveal | operator-facing notes | `gen/RUNTIME.md` |

## Stage 4 — the workflow DAG is real and bounded

The lowered `gen/workflow/*.json` carries the **precomputed critical-path depth**
alongside the steps and edges — e.g. the swarm pipeline lowers to a 3-step DAG
with `depth = 3`, and the workflow record keeps `maxDepth` as the declared bound.
This is the `E-WORKFLOW-DEPTH` check made into a durable artifact: the runtime
receives the depth the compiler proved, not a number it must recompute.

```json
{ "on": "...", "budget": "...", "maxDepth": <bound>,
  "steps": [...], "edges": [...], "depth": <proven critical path> }
```

## Why this demonstrates the thesis

1. **Language** — nine structurally different agentic swarms are expressible in
   the same v0.3 grammar (29 kinds) with no per-example grammar changes.
2. **Compiler** — the same 0011 type system checks all nine; the same 0012
   lowering emits deterministic artifact trees; a single diagnostic anywhere
   blocks emission.
3. **Runtime** — the emitted artifacts are the concrete stack (Nix/OTP/Zig/eBPF/
   CrabCC), so "compiles" ends at a runnable host description, not at an AST.

The PR-pipeline dogfood (`pr-multimodel-pipeline.vaked`) is the tenth swarm — the
one that models the very loop that produced this PR — and it lowers the same way
(9 artifacts), closing the self-referential loop the batch set out to prove.
