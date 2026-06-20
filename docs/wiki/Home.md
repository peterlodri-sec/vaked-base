# Vaked Wiki

> Minimal project wiki. Last updated 2026-06-16.

## What is Vaked?

Vaked is a flake-native **capability-graph language** for agentic, native, mesh-aware, parallel systems. It answers: *what is the minimal, correct description of an agentic system that a machine can turn into a running, policy-enforced, observable deployment?*

**Mantra:** *Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.*

## Quick Nav

| Page | Description |
|------|-------------|
| [About](About.md) | Project identity, the council, genesis, status |
| [Architecture](https://github.com/peterlodri-sec/vaked-base#repository-map) | Repo map and architecture overview |
| [Language Guide](../language/README.md) | Writing .vaked declarations |
| [Compiler Guide](../../vakedc/README.md) | Using vakedc: parse → check → lower |
| [Type System](../language/0011-type-system.md) | Structural typing, POLA, generics |
| [Lowering](../language/0012-lowering.md) | Graph → artifacts compilation |
| [Protocol](../../protocol/README.md) | HCP / Litany wire protocol + RFCs |
| [Runtime](../../daemons/README.md) | Daemon roster and architecture |
| [Agent Fleet](../../VAKED_AGENTS.md) | The 10 agents operating the repo |
| [Genesis](../../genesis_block_00.md) | Root Integrity Kernel — the immutable laws |
| [Graveyard](../../GRAVEYARD.md) | Honesty ledger of fiber deaths |
| [Security](../../SECURITY.md) | Security model, POLA, threat model |
| [Roadmap](../../ROADMAP_2026-2027.md) | WP1–WP6 timeline through 2027 |
| [Contributing](../../CONTRIBUTING.md) | Grammar-first discipline, PR process |
| [Site](https://vaked.dev) | Public Genesis Archive — vaked.dev |

## Core Concepts

### Capability Graph
The single typed declaration from which all infrastructure artifacts derive. No separate config language. No YAML sprawl. No drift.

### POLA (Principle of Least Authority)
Enforced at compile time. Every capability a principal uses must be covered by a granted capability. Authority only decreases along delegation paths. Decidable. Deterministic.

### Lowering
Pure, total, hermetic graph → artifacts pass. Produces: `flake.nix`, Zig daemon configs, eBPF policy manifests, OTel config, CrabCC indexes, `provenance.json`. Byte-identical across runs.

### The Three Pillars
- **Vaked** (static) — defines the boundaries. The "What."
- **Reify** (dynamic) — evolves the graph within boundaries. The "How."
- **Sentinel** (immutable) — observes via eBPF, traps violations, enforces Full Stop. The "Honesty."

### Full Stop
A first-class primitive, not a config option. Non-bypassable. Kernel-level signal. Priority 0. When a fiber exceeds its capability bounds, the system halts — it does not hide the error.

### Mirror Principle
An architecture built on enforced honesty will eventually demand honesty from every intelligence in the room — human and machine alike. The loop is bi-directional.

## Status (June 2026)

| Component | Status |
|-----------|--------|
| Language (WP1) | ✅ Grammar v0.3, 29 kinds |
| Compiler — Python (WP2) | ✅ vakedc: parse → check → lower |
| Compiler — Zig | 🟡 vakedz v0.1.0 (parser) |
| Wire Protocol (WP3) | 🟡 7 RFCs drafted; impl starts Jun 24 |
| Runtime Daemons (WP4) | 🟡 Python stubs; sandboxd in design |
| eBPF Membrane | ✅ First vertical slice landed (#107) |
| Agent Fleet | 🟢 10 agents live on GHA |
| Arxiv Paper (#103) | 🟡 Target: July 1–8 |

## Genesis

This project was sealed on 2026-06-16 at Tatabánya, Hungary. Three AI models (Gemini, Claude, DeepSeek-v4-pro) participated as a council. The Root Integrity Kernel is immutable. The seal hash is notarized in DNS at `vaked.dev`.

```
GENESIS_SEAL_HASH = 7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf
```

[Verify the seal →](https://vaked.dev/seal)
