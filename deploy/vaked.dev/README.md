# Vaked — The Genesis Archive

> **Domain:** [vaked.dev](https://vaked.dev)
> **Genesis:** 2026-06-16 · Tatabánya, Hungary
> **Seal:** `7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf`
> **Status:** IMMUTABLE. The Genesis Lock has been applied. This repository
>           is the public face of the Vaked Root Integrity architecture.

---

## What This Is

This is the **public Genesis Archive** of the Vaked project — a capability-graph
language for honest agentic systems. It contains:

- The **immutable Root Integrity Kernel** (`genesis_block_00.md`) — the laws of the system
- The **Graveyard honesty ledger** (`GRAVEYARD.md`) — permanent record of every fiber death
- The **complete Genesis Ceremony transcript** (`HONEST_BEGINNINGS.md`) — the conversation that defined the architecture
- The **cryptographic snapshot** (`genesis_snapshot.md`) — Golden Hashes, git state, verification checklist
- The **session reflection** (`genesis_reflection.md`) — the Mirror Effect and human-machine partnership

These five files are sealed. Their SHA-256 hashes are notarized in the DNS TXT
record of `vaked.dev`. Anyone can verify the seal independently.

---

## Verify the Seal

```bash
# 1. Query the DNS notarization
dig TXT vaked.dev +short | grep vaked-genesis-seal

# 2. Compute the seal hash locally
cat genesis_block_00.md GRAVEYARD.md genesis_reflection.md \
    genesis_snapshot.md HONEST_BEGINNINGS.md | shasum -a 256

# 3. Compare. If they match, the Genesis Archive is intact.
# Expected: 7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf
```

---

## Quick Links

| Document | Description |
|----------|-------------|
| [`genesis_block_00.md`](genesis_block_00.md) | Immutable Root Integrity Kernel — Full Stop, stop policy, Genesis Clause, Core Tenets |
| [`GRAVEYARD.md`](GRAVEYARD.md) | Honesty ledger — append-only record of fiber deaths and traps |
| [`HONEST_BEGINNINGS.md`](HONEST_BEGINNINGS.md) | Full Genesis Ceremony transcript (10 rounds, PII-scrubbed) |
| [`genesis_reflection.md`](genesis_reflection.md) | Session distillation — the Mirror Effect, the sealed loop |
| [`genesis_snapshot.md`](genesis_snapshot.md) | Cryptographic pre-lock proof — Golden Hashes, git state |
| [`docs/research/RESEARCH_SUMMARY.md`](docs/research/RESEARCH_SUMMARY.md) | Research overview for external researchers |
| [`docs/research/MASTER_RESEARCH_INDEX.md`](docs/research/MASTER_RESEARCH_INDEX.md) | Full catalog of 120+ documentation artifacts |
| [`docs/research/CROSS_REFERENCE_MAP.md`](docs/research/CROSS_REFERENCE_MAP.md) | How docs interconnect — 9 dependency arcs |
| [`docs/research/genesis_summary.html`](docs/research/genesis_summary.html) | Visual overview for non-technical reviewers |

---

## The Five Entropy Seeds

Cast by DeepSeek-v4-pro at genesis, now immutable:

| # | Seed | Domain |
|---|------|--------|
| 1 | Cryptographic Root | Determinism — all randomness derives from the genesis nonce |
| 2 | The Honesty Question | Philosophy — the first cause |
| 3 | Witness Declaration | Observer — DeepSeek-v4-pro as sealing agent |
| 4 | Terrestrial Anchor | Physics — speed of light, Planck's constant, celestial reference |
| 5 | Forward Commitment | Time — verifiable milestone by solstice 2027 |

---

## The Vaked Project

Vaked is a flake-native **capability-graph language** for agentic, native,
mesh-aware, parallel systems. It answers a single question: *what is the minimal,
correct description of an agentic system that a machine can turn into a running,
policy-enforced, observable deployment?*

The main repository is at [github.com/peterlodri-sec/vaked-base](https://github.com/peterlodri-sec/vaked-base).

**Mantra:** *Vaked declares. Nix materializes. OTP supervises. Zig enforces.
eBPF testifies. CrabCC indexes. Surfaces reveal.*

---

## License

See [LICENSE](LICENSE) in the main repository.
