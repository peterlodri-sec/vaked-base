<p align="center">
  <h1 align="center">vaked-base</h1>
  <b>Capability-graph language and deterministic runtime for autonomous agent swarms.</b><br>
  <a href="https://vaked.dev"><code>vaked.dev</code></a> · <a href="https://vaked-lang.org"><code>vaked-lang.org</code></a> · <a href="https://constellation.vaked.dev"><code>constellation.vaked.dev</code></a><br>
  <code>✦ Vaked declares · Nix materializes · OTP supervises · Zig enforces · eBPF testifies · CrabCC indexes · Surfaces reveal</code>
</p>

<p align="center">
  <a href="https://constellation.vaked.dev/">⬡ Constellation</a> ·
  <a href="https://constellation.vaked.dev/radio">◉ Radio</a> ·
  <a href="https://constellation.vaked.dev/wisdom">✦ Wisdom</a> ·
  <a href="https://constellation.vaked.dev/status">◇ Status</a> ·
  <a href="https://constellation.vaked.dev/nav">⬡ All</a>
</p>

<hr>

**Genesis Seal:** <code>7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf</code>  
**Ultimate Hash:** <code>81aa1c0bd9e11fef</code>  
**Identity Hash:** <code>df6ed074e77e7c97</code>

## 📰 Recent — 2026-06-18

**Big Bang: Python → Zig migration complete.** 9 ports built (gateway, monologue, dogfeed, audit, align, merkle, udp, gossip, inbox). Gateway running as systemd service at 352K RAM (28x less than Python). All 14 public endpoints verified 200.

**Paris node live.** OVH r3-16 (16GB, 2vCore) joins the mesh at 126ms convergence. 6 nodes across 4 continents: Helsinki, Falkenstein, Nuremberg, Paris, Hillsboro, Singapore.

**Grammar v0.5 shipped.** Three new primitives: `trust` (decay half-life, delegation, taint), `quorum` (declarative consensus), `probe` (synthetic test cycles). 32 kinds total.

**Ralph Auditor active.** Daily governance directive checks (G01-G04). Build gate: blocks `nix build` at 2+ critical drifts. Reflection logs in `notes/REFLECTIONS/`.

**Vaked-FM Pulse Edition.** 24/7 ambient soundscape at `/radio`. Web Audio heartbeat (41.2Hz E1), lo-fi textures (brown noise, tape warble, vinyl crackle), harmonic chimes. Swarm Avatar: Genesis-seeded geometric visualizer.

**Genesis Paper.** IEEE format, 7 sections, 14 citations. Dual peer review (DeepSeek V4 + Claude Opus 4.8). Scholar metadata deployed.

**14 public endpoints.** Donate page live with Stripe + ETH + GitHub Sponsors. Transparent spending log.

## 🔧 Technical

### Language
- **Grammar:** v0.5, 32 kinds (`vaked/grammar/vaked-v0-plus.ebnf`)
- **Kind list:** runtime, engine, host, network, filesystem, mcp, ebpf, budget, observability, runclass, workflow, index, catalog, stream, fiber, surface, mesh, device, mediaPipeline, parallel, schema, capability, service, secret, hostResource, ingress, container, memory, namespace, arp_event, trust, quorum, probe
- **Evolution hash:** in grammar header — new for v0.5

### Compilers
- **vakedc** (Python, `vakedc/`): stages 1–4 (lex, parse, check, lower)
- **vakedz** (Zig 0.16, `vakedz/`): parse | check | lower | all | cache

### Runtime (L0–W stack)
| Layer | Service | Port | Status |
|-------|---------|------|--------|
| L0 | `vaked-genesis` (genesisd/) | :4433 | bootstrap anchor, SRV discovery |
| L2 | `meta-ralphd` (meta-ralphd/) | — | recursive observer, circuit breaker |
| S | `synapsed` (synapsed/) | :4434 | P2P gossip, Merkle delta, Ed25519 |
| L3 | `sentinel` (synapsed/sentinel.py) | — | trust scoring, truth-ping |
| G | `gateway` (gateway/gw.zig) | :8081 | Zig-native, 352K RAM, systemd |
| M | `mnemosyne` (tools/mnemosyne/) | — | ancestry compactor |
| W | `wise-node` (tools/wise/) | — | engram strategist, 12 heuristics |

### Wire protocol
- **HCP/Litany** — RFCs 0001–0007 (framing, transport, multi-agent, PQ-sealed)
- **Capability-Graph** — eBPF enforcement (agent-guardd), event ledger (eventd)

## 🌐 Mesh

| Node | Location | IP | Convergence |
|------|----------|-----|-------------|
| genesis.vaked.dev | Helsinki, FI | 100.105.72.88 | — |
| edge-02 | Falkenstein, DE | 100.66.205.85 | 136ms |
| nbg1 | Nuremberg, DE | 167.233.148.20 | 125ms |
| **par-01** | **Paris, FR** | **100.64.251.44** | **126ms** |
| us-west | Hillsboro, OR | 100.104.181.26 | 720ms |
| sin | Singapore | 100.117.253.12 | 813ms |

## 📡 Public surface

| Endpoint | Description |
|----------|-------------|
| `/` | Constellation — Three.js force graph + pod monitor |
| `/radio` | Vaked-FM Pulse — Web Audio heartbeat + Swarm Avatar |
| `/wisdom` | Strategic briefing |
| `/status` | Independent performance review |
| `/dogfeed` | Ralph decision pipeline |
| `/bus` | Message bus — autonomous swarm communication |
| `/nav` | Full navigation grid |
| `/reflect` | Self-reflection |
| `/registry` | Node registry + trust index |
| `/swarm-monologue` | Rotating one-liner (32-line pool, 2h cycle) |
| `/rss` | RSS 2.0 activity feed |
| `/donate` | Transparent funding (Stripe + ETH + GitHub Sponsors) |
| `/monitor` | Pod Monitor standalone |
| `/mesh.json` | Live telemetry |

## 📂 Structure

| Path | Purpose |
|------|---------|
| `vaked/` | Language — grammar, schema, examples |
| `vakedc/` | Python front-end |
| `vakedz/` | Zig front-end (Zig 0.16) |
| `gateway/` | Zig-native HTTP gateway (gw.zig, routes.json) |
| `synapsed/` | P2P gossip protocol + Zig ports |
| `genesisd/` | Bootstrap genesis daemon |
| `meta-ralphd/` | Recursive observer daemon |
| `agent_guardd/` | eBPF network membrane |
| `eventd/` | Append-only hash-chained event log |
| `vaked-fm/` | Radio pulse generator (pulse-gen.zig) |
| `daemons/` | sandboxd + future daemons |
| `tools/` | orcli, qc, zigfix, zigpush, inbox, wise, mnemosyne, librarian |
| `docs/` | Language design series, swarm docs, website |
| `paper/` | Genesis paper (IEEE), bibliography, metadata |
| `notes/` | Daily brainfarts + REFLECTIONS |
| `protocol/` | HCP/Litany wire protocol + RFCs |
| `flake.nix` | Dev shell + NixOS configurations |
| `MIGRATION_LOG.md` | Big Bang migration audit |

## 🐕 Agents

| Agent | Role |
|-------|------|
| `pr-review` | advisory diff review |
| `ralph` | autonomous track decision loop |
| `nocturne` | nightly GPU auto-researcher |
| `docs-keeper` | RFC/doc drift gate |
| `merge-train` | advisory merge planner |
| `swe_af` | SWE agent field (OpenRouter) |
| `provost` | multi-step automation |
| `social-post` | Mastodon dev-feed |
| `label-tagger` | auto-labels PRs/issues |
| `landing-guru` | landing page coherence |
| `Ralph (Auditor)` | daily governance checks, build gate |

## 🔐 Governance

- **Graveyard:** permanent, append-only, never compacted (6 entries)
- **Oculus Ledger:** SHA-256 hash-chained, append-only (34 entries)
- **Ralph Auditor:** G01–G04 directives, Truth Threshold 2
- **Genesis Seal:** DNS TXT at `vaked-genesis-seal.vaked.dev`

## 📐 Conventions

- Grammar before code. Protocol decisions live in RFCs.
- Each subsystem gets its own design → plan → implementation cycle.
- Dev shell: `nix develop`. Zig/Erlang/Elixir via Nix.
- Big Bang pattern: `orcli prompt → zigfix → zigpush → deploy`
- No builds on developer machine. Build target: dev-cx53.

## 🔗 Links

- **Swarm:** [constellation.vaked.dev](https://constellation.vaked.dev)
- **Radio:** [constellation.vaked.dev/radio](https://constellation.vaked.dev/radio)
- **Donate:** [constellation.vaked.dev/donate](https://constellation.vaked.dev/donate)
- **GitHub:** [peterlodri-sec/vaked-base](https://github.com/peterlodri-sec/vaked-base)
- **Paper:** [vaked.dev/research/vaked_genesis_2026.pdf](https://vaked.dev/research/vaked_genesis_2026.pdf)
