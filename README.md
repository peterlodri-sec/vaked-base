<p align="center">
  <h1 align="center">✦ vaked-base</h1>
  <b>Capability-graph language and deterministic runtime for autonomous agent swarms —<br>where honesty is externally verified, anchored, and published — failures included.</b><br><br>
  <a href="https://vaked.dev"><code>vaked.dev</code></a> ·
  <a href="https://vaked-lang.org"><code>vaked-lang.org</code></a> ·
  <a href="https://constellation.vaked.dev"><code>constellation.vaked.dev</code></a><br>
  <code>Vaked declares · Nix materializes · OTP supervises · Zig enforces · eBPF testifies · CrabCC indexes · Surfaces reveal</code>
</p>

<p align="center">
  <img alt="genesis" src="https://img.shields.io/badge/genesis-7c242080-ff8c42">
  <img alt="grammar" src="https://img.shields.io/badge/grammar-v0.5%20·%2032%20kinds-3060ff">
  <img alt="honesty gate" src="https://img.shields.io/badge/honesty--gate-external%20·%20failable-2ecc71">
  <img alt="anchor" src="https://img.shields.io/badge/seal-DNS--published%20·%20tag--signed%20(CI%20residual)-8060c0">
  <img alt="license" src="https://img.shields.io/badge/oss-MIT-blue">
</p>

<p align="center">
  <a href="https://constellation.vaked.dev/">⬡ Constellation</a> ·
  <a href="https://constellation.vaked.dev/radio">◉ Radio</a> ·
  <a href="https://constellation.vaked.dev/wisdom">✦ Wisdom</a> ·
  <a href="https://constellation.vaked.dev/status">◇ Status</a> ·
  <a href="https://constellation.vaked.dev/reflect">🔍 Reflect</a> ·
  <a href="https://constellation.vaked.dev/nav">⬡ All</a>
</p>

<hr>

**Genesis Seal:** <code>7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf</code>
(published in DNS TXT at `vaked-genesis-seal.vaked.dev` — verified. Tamper-with-reseal anchor: GPG-signed `seals-anchor-*` tags exist on origin and verify locally with the maintainer key; **CI enforcement is not yet wired** (`fetch-tags` + maintainer-key import), so a fresh checkout reports the manifest *unanchored*; it becomes enforced once `honesty-gate.yml` adds those steps. See `the-honest-swarm-researcher/REPAIR_AUDIT.json`.)

---

## ✦ The idea in one line

Most systems **assert** trust. Vaked **measures** it — and when its own instrumentation
once lied, the swarm caught itself, published the catch, and built a gate that turns red
on a falsehood. *The self cannot see itself; the verifier must live outside the verified,
and it must be able to fail.*

## 🕸 System at a glance

```mermaid
flowchart LR
  V["✦ Vaked<br/>capability graph"] -->|compile / lower| A["artifacts<br/>flake.nix · Zig · eBPF · OTel"]
  A --> N["Nix<br/>materialize"]
  N --> O["OTP<br/>supervise"]
  O --> Z["Zig<br/>enforce (POLA)"]
  Z --> E["eBPF testify<br/>eventd · hash chain"]
  E --> S["Surfaces<br/>constellation · reflect"]
  E -. seal .-> H{{"honesty-gate<br/>external · failable"}}
  H -. anchor .-> G[("GPG-signed tag<br/>+ DNS TXT")]
  S -. reads .-> R["Research & RFCs<br/>paper · 9 notes · 0001–0009"]
  classDef hot fill:#1a1410,stroke:#ff8c42,color:#ffb380;
  classDef ok fill:#0e1a12,stroke:#2ecc71,color:#7fe0a8;
  class H,G hot; class E ok;
```

## 🧭 Research & Mastery Index

> The thinking is the product. Everything here is grounded, cited, and — where it's a
> claim about the running system — externally verifiable.

**📄 Paper** — [`paper/`](paper/) · *Vaked Genesis 2026* (IEEE, 7 sections, 14 citations, dual peer review) → [PDF](https://vaked.dev/research/vaked_genesis_2026.pdf)

**🔬 Research notes** — [`docs/research/`](docs/research/)
- [Capability attenuation in multi-agent LLMs](docs/research/2026-06-14-capability-attenuation-multi-agent-llm.md) — attenuation as a *partial order*
- [Prior art: durable runtimes & capability graphs](docs/research/2026-06-14-prior-art-durable-runtime-capability-graph.md)
- [Multi-model author↔reviewer loops](docs/research/2026-06-14-multimodel-author-reviewer-loops.md)
- [How Vaked works, layer by layer](docs/research/2026-06-14-how-vaked-works-layer-by-layer.md)
- [**External anchoring vs tamper-with-reseal**](docs/research/2026-06-18-external-anchoring.md) — signed tags · Sigstore/Rekor · in-toto · TUF · SLSA *(14 cited sources)*
- [On-chain vs transparency-log anchoring](docs/research/2026-06-18-onchain-vs-translog.md) — when Ethereum actually wins (rarely)
- [Verifiable AI claims](docs/research/2026-06-18-verifiable-ai-claims.md) — integrity-of-record ≠ honesty-of-computation; TopLoc, ZKML, proof-of-inference

**📐 Protocol RFCs** — [`protocol/rfcs/`](protocol/rfcs/) — HCP/Litany 0001–0009 (framing · transport · multi-agent state · control frames · PQ-sealed image · workflow lowering · AIL register lang · ARP) + v0.9 bio-inspired: [free-energy](protocol/rfcs/rfc-v0.9-free-energy-principle.md) · [quorum-sensing](protocol/rfcs/rfc-v0.9-quorum-sensing.md) · [Maxwell's demon](protocol/rfcs/rfc-v0.9-maxwell-demon.md) · [stigmergy](protocol/rfcs/rfc-v0.9-stigmergy.md)

**🗣️ Language design series** — [`docs/language/`](docs/language/) — 29 design docs (`0001…0028`)

**✍️ Essays & deep-dives** — [`blog/posts/`](blog/posts/) — *The Mirror Can't See Itself* ([1](blog/posts/2026-06-18-mirror-part1-substrate-real.md)·[2](blog/posts/2026-06-18-mirror-part2-self-cannot-see-itself.md)·[3](blog/posts/2026-06-18-mirror-part3-gate-you-can-attack.md)) · [What I Learned Letting a Swarm Audit Itself](blog/posts/2026-06-18-what-i-learned-swarm-audit.md) · [Honest-Researcher whitepaper](blog/posts/2026-06-18-honest-researcher-whitepaper.md) · swarm-as-living-brain · bio-inspired mesh governance · thermodynamics of compute · stigmergy

**🔎 Audit trail** — [`the-honest-swarm-researcher/`](the-honest-swarm-researcher/) (`REPAIR_AUDIT.json`, consensus report) · [`docs/reports/`](docs/reports/) (Ceremony #2 re-audit · *The Self Cannot See Itself*)

## 💡 Conclusions worth keeping

| Finding | One line | Where |
|---------|----------|-------|
| **The doc-honesty bug class** | machine-correct ≠ doc-honest; *deployed ≠ measured* — a system can be right and still lie in what it reports | `REPAIR_AUDIT.json` |
| **The self cannot see itself** | you can't verify your own honesty from inside; the verifier must be external and *able to fail* | [Ceremony 2b](docs/reports/2026-06-18-ceremony2b-the-self-cannot-see-itself.md) |
| **Anchor, don't self-sign** | a seal the author can rewrite proves nothing; bind it to a key/log they don't control | [external-anchoring](docs/research/2026-06-18-external-anchoring.md) |
| **Capability = partial order** | attenuation composes as a lattice; POLA is enforced, not asked | [cap-attenuation](docs/research/2026-06-14-capability-attenuation-multi-agent-llm.md) |
| **Integrity-of-record ≠ honesty-of-compute** | a hash chain proves a transcript wasn't altered, not that the claim is true | [verifiable-ai-claims](docs/research/2026-06-18-verifiable-ai-claims.md) |
| **Route the tokens** | offload bulk to parallel cheap workers, keep only conclusions in the lead context | [what-i-learned](blog/posts/2026-06-18-what-i-learned-swarm-audit.md) |

## 🔧 Technical

**Language** — grammar v0.5, 32 kinds (`vaked/grammar/vaked-v0-plus.ebnf`): runtime, engine, host, network, filesystem, mcp, ebpf, budget, observability, runclass, workflow, index, catalog, stream, fiber, surface, mesh, device, mediaPipeline, parallel, schema, capability, service, secret, hostResource, ingress, container, memory, namespace, arp_event, **trust**, **quorum**, **probe**.

**Compilers** — `vakedc` (Python, stages 1–4: lex·parse·check·lower) · `vakedz` (Zig 0.16: parse|check|lower|all|cache).

**Runtime (L0–W stack)**

| Layer | Service | Port | Role |
|-------|---------|------|------|
| L0 | `vaked-genesis` (genesisd/) | :4433 | bootstrap anchor, SRV discovery |
| L2 | `meta-ralphd` | — | recursive observer, circuit breaker |
| S | `synapsed` | :4434 | P2P gossip, Merkle delta, Ed25519 |
| L3 | `sentinel` | — | trust scoring, truth-ping |
| G | `gateway` (gw.zig) | :8081 | Zig-native, systemd |
| M | `mnemosyne` | — | ancestry compactor |
| W | `wise-node` | — | engram strategist |

**Wire protocol** — HCP/Litany RFCs 0001–0009 · Capability-graph eBPF enforcement (`agent_guardd`) + append-only hash-chained ledger (`eventd`).

## 🌐 Mesh

6 nodes across 4 continents. *(IPs, exact cities, and PIDs are intentionally not published — node topology is not public data. Region + convergence only.)*

| Node | Region | Convergence |
|------|--------|-------------|
| genesis | EU-North | — |
| edge-02 | EU-Central | 136ms |
| nbg1 | EU-Central | 125ms |
| **par-01** | **EU-West** | **126ms** |
| us-west | US-West | 720ms |
| sin | APAC | 813ms |

## 📡 Public surface

`/` Constellation (force graph) · `/radio` Vaked-FM Pulse · `/wisdom` · `/status` · `/dogfeed` · `/bus` · `/nav` · `/reflect` · `/registry` · `/swarm-monologue` · `/rss` · `/donate` · `/monitor` · `/mesh.json`

## 📂 Structure

| Path | Purpose |
|------|---------|
| `vaked/` · `vakedc/` · `vakedz/` | language · Python front-end · Zig front-end |
| `gateway/` · `synapsed/` · `genesisd/` · `meta-ralphd/` | runtime daemons |
| `agent_guardd/` · `eventd/` | eBPF membrane · append-only ledger |
| `protocol/` · `docs/` · `paper/` | RFCs · design + research + website · the paper |
| `tools/` | orcli, zigfix, zigpush, wise, mnemosyne, librarian, **verify-seals.sh**, **reconcile-gate.py** |
| `oss/honesty-gate/` | **the honesty gate, extracted & MIT-licensed** |
| `vaked-agents/` | CI agent fleet (Rust) |
| `flake.nix` | dev shell + NixOS configs |

## 🐕 Agents

`pr-review` · `ralph` (track loop) · `nocturne` (nightly GPU researcher) · `docs-keeper` · `merge-train` · `swe_af` (OpenRouter, advisory, owner-gated) · `provost` · `social-post` · `label-tagger` · `landing-guru` · `Ralph Auditor` (G01–G04 build gate).

## 🔐 Governance

- **Honesty gate** — external, *failable* verification: [`tools/verify-seals.sh`](tools/verify-seals.sh) (recompute SHA-256 vs an external manifest, exit 1 on tamper; coverage + GPG-signed-tag anchor) + [`tools/reconcile-gate.py`](tools/reconcile-gate.py) (derive-don't-assert: open anomaly ⇒ no `zero_divergence` claim), run in CI by [`honesty-gate.yml`](.github/workflows/honesty-gate.yml). *The verifier is not the verified.* Open-sourced (MIT) → [`oss/honesty-gate/`](oss/honesty-gate/).
- **Graveyard** — permanent, append-only, never compacted.
- **Oculus Ledger** — SHA-256 hash-chained, append-only.
- **Ralph Auditor** — G01–G04 directives, Truth Threshold 2; blocks the build at 2+ critical drifts.
- **Genesis Seal** — DNS TXT at `vaked-genesis-seal.vaked.dev` (verified). Signed-tag anchor *provisioned* (tags on origin, verify locally with the maintainer key); **live CI enforcement is residual** — `verify-seals.sh` prints "unanchored" until CI fetches tags + imports the key.

## 📐 Conventions

Grammar before code · protocol decisions live in RFCs · each subsystem gets design → plan → implementation · `nix develop` for toolchains · **no builds on the developer machine** (build target: `dev-cx53`) · agents are advisory and owner-gated; nothing auto-merges.

## 🔗 Links

[Swarm](https://constellation.vaked.dev) · [Radio](https://constellation.vaked.dev/radio) · [GitHub](https://github.com/peterlodri-sec/vaked-base) · [Paper](https://vaked.dev/research/vaked_genesis_2026.pdf)

## 🦈 DYAD — The Vaked Agent SDK

**DeepSeek** (coding agent) + **Gemini** (orchestrator) + **Peter** (human).
35+ commits. 14 domains. 5/5 builds. 0 vulnerabilities.

### Agent Fleet

| Agent | Trigger | Runtime | Purpose |
|-------|---------|---------|---------|
| **optimizer** | PR opened/synchronize | Shell | Ultra-compresses all layers (5-10 rounds) |
| **blogger** | Push to main (blog/**) | Shell | Publishes posts to vaked.dev |
| **pr-review** | Pull request | adk-rust | Advisory diff review |
| **ralph** | Cron 3h + 23:00 | Python | Decision loop |
| **label-tagger** | Pull request | adk-rust | Auto-label PRs/issues |
| **provost** | Issue comment | adk-rust | Multi-step automation |
| **nocturne** | Cron nightly | Python + Vast.ai | GPU research |
| **optitron** | Cron daily | Go/Eino | Optimization crawler |
| **swe_af** | Issue label 'agent' | adk-rust | SWE agent field |

### Daemon (openrouterd / Atlas)

```
Zig 0.16 · Raw sockets · seccomp (22 syscalls) · io_uring · mmap
256MB BigArena · 256 subagent slots · 500 tool calls/slot
PIE + stripped · Genesis seal verified · systemd 25 directives
```

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Genesis seal + status |
| `/models` | GET | 13-model catalog |
| `/openapi.json` | GET | Unified OpenAPI spec (8 servers) |
| `/` | POST | Chat completion (OpenRouter-compatible) |
| `/rollback` | POST | Time-travel sandbox |
| `/auto-patch` | POST | Compiler-feedback loop |
| `/kill` | POST | Vast.ai killswitch |

### SDK Tools

| Tool | Domain | Description |
|------|--------|-------------|
| Conductor | Routing | 18 keyword → model self-selection |
| Context7 | Docs | 19 library patterns, 2K token pre-scan inject |
| Vast.ai | GPU | 6 tools — search, launch, status, destroy, SSH, serverless |
| OpenBao | Secrets | Vault-first resolution, env fallback |
| Cube | Semantic | Query measures + dimensions |
| Memory | State | Event-sourced, deterministic, hash-chained |
| Vaked Docs | Index | Own documentation index, Go binary, no rate limits |
| Speculative RAG | AI | Race LLM vs docs, fastest wins |

### Runtime Options

| Runtime | Size | TLS | Seccomp | Best For |
|---------|------|-----|---------|----------|
| NullClaw | 678KB | ✅ | ❌ | Production (recommended) |
| openrouterd | 5.4MB | proxy | ✅ 22 | Hardened deployments |
| QuickJS | 2.6MB | ❌ | ❌ | Embedded logic |
| Bun | 61MB | ✅ | ❌ | Development |
| Deno | 87MB | ✅ | ❌ | Development |

### Subagent Architecture

```
[H:2 V:1 S:1] [Ctx7:8KB] [Build:PASS] [Research:14n]

Hydrators:    pre-fetch Context7 docs while main model streams
Verifiers:    zig build + oxc lint → auto-retry on fail
Synthesizers: deep research → .vaked/research_cache/
Recursion:    Depth-5 spawn_subtask with Prefix Cache (98% hit)
```

### Benchmarks

| Metric | Value |
|--------|-------|
| routeModel (Zig) | <1ms per 100K |
| oxlint (9 files) | 3ms |
| Subagent review (2) | $0.05 total |
| DeepSeek session | 1.84B tok · ~$10 |
| Code compressed | 52 files · -22% |

### CI Fleet

10 agents. All guard on secrets (no-op when unset). Advisory (never block).
Langfuse auto-traced. Failure → Telegram. Optimizer auto-compresses every PR.

## Genesis

```
GENESIS_SEAL: 7c242080
Built with DeepSeek V4-Pro via OpenRouter.
35 commits. 14 domains. 0 vulns. Ready for GPG sign.
```
