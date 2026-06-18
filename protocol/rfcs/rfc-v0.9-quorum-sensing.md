# RFC v0.9 — Quorum Sensing & Compute Governance

- **Status:** Draft · **Created:** 2026-06-18 · **Genesis:** 7c242080

## Abstract

Bacteria use quorum sensing — chemical signaling molecules (autoinducers) that
accumulate proportionally to population density. When concentration crosses a
threshold, the colony triggers coordinated group behavior: biofilm formation,
virulence, bioluminescence. No single bacterium "decides." The decision emerges
from local chemical concentration.

This RFC proposes a Quorum-Gated compute protocol for the Vaked Swarm's 3D
parallelization architecture. High-compute operations (Shadow-Critic sessions,
100-model deliberation) only trigger when a local "compute-load" threshold is
met — preventing resource waste on low-value tasks.

## Mapping

| Bacterial System | Swarm Equivalent |
|-----------------|-----------------|
| Autoinducer molecule | Local compute-load metric |
| Concentration threshold | Quorum gate trigger value |
| Quorum sensing receptor | Sentinel load monitor |
| Coordinated behavior | Shadow-Critic + Consensus panel |
| Biofilm formation | Persistent State-Hydration |

## Implementation

1. Each node maintains a local `compute_load` counter (active sub-agents).
2. When `compute_load > quorum_threshold`, the node emits a "quorum signal"
   (appends to /reflect with kind=QUORUM_REACHED).
3. Adjacent nodes receiving 2+ quorum signals trigger their own Shadow-Critic
   sessions — creating a wave of compute activation.
4. When `compute_load < quorum_threshold`, nodes return to idle (baseline).

## ASCII Summary

```
┌──────────────────────────────────────────────────────────┐
│              QUORUM SENSING IN 3D SWARM                  │
│                                                          │
│   NODE A          NODE B          NODE C                │
│   ┌─────┐         ┌─────┐         ┌─────┐              │
│   │ ██  │  load=3 │ ███ │  load=5 │ ██  │ load=2       │
│   └──┬──┘         └──┬──┘         └──┬──┘              │
│      │    quorum     │    quorum     │                   │
│      │    signal     │    signal     │                   │
│      ▼               ▼               ▼                   │
│   ┌─────────────────────────────────────┐              │
│   │        QUORUM GATE (θ=4)            │              │
│   │  "2+ nodes above threshold → ACT"   │              │
│   └─────────────────────────────────────┘              │
│                    │                                     │
│                    ▼                                     │
│   ┌─────────────────────────────────────┐              │
│   │   SHADOW-CRITIC + CONSENSUS PANEL   │              │
│   │   (coordinated compute activation)  │              │
│   └─────────────────────────────────────┘              │
│                                                          │
│   Below threshold: nodes idle, conserve resources.      │
│   Above threshold: swarm activates as one organism.     │
└──────────────────────────────────────────────────────────┘
```

## Governance

The grammar v0.5 `quorum` kind already models consensus thresholds. This RFC
extends it to compute-load gating — the `quorum` primitive gains a `trigger`
clause:

```ebnf
quorum_decl += "trigger" "(" "compute_load" ">" positive_integer ")"
              "action" "(" ident ")" ;
```

## References

- Miller, M.B. & Bassler, B.L. (2001). Quorum sensing in bacteria.
- Vaked grammar v0.5: quorum primitive
- Genesis Seal: 7c242080
