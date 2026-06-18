# RFC v0.9 — Free Energy Principle & Swarm Consensus

- **Status:** Draft
- **Created:** 2026-06-18
- **Genesis:** 7c242080

## Abstract

Karl Friston's Free Energy Principle states that living systems minimize
"surprise" (variational free energy) by maintaining internal models that
predict sensory input. When prediction error occurs, the system acts to
reduce it — either by updating the model (perception) or changing the
environment (action).

This RFC maps the Free Energy Principle onto the Vaked Swarm's consensus
panel architecture, establishing the `Judge` agent as a Generative Model
that minimizes divergence between predicted swarm state and actual mesh
telemetry.

## Mapping

| Biological System | Swarm Equivalent |
|-------------------|-----------------|
| Sensory input | Mesh telemetry (/status, /mesh.json) |
| Internal model | CapabilityGraph + Genesis Seal |
| Prediction error | Drift (Sentinel G01-G04 checks) |
| Action | Auto-tune optimization (io_uring, tc) |
| Free energy | Divergence between predicted/actual state |
| Generative model | Judge agent (consensus panel) |

## Implementation

1. The Judge agent maintains a predicted state vector `P(t)` from the
   CapabilityGraph and historical /reflect logs.
2. Actual state `A(t)` arrives from /mesh.json every 100ms.
3. Variational free energy `F = KL(P || A)` is computed as the
   Kullback-Leibler divergence.
4. If `F > threshold`, the swarm acts:
   - Perception: update internal model (evolution_hash increment)
   - Action: trigger auto-tune optimization

## ASCII Summary

```
┌─────────────────────────────────────────────────────────┐
│              FREE ENERGY PRINCIPLE IN SWARM             │
│                                                         │
│   SENSORY INPUT          INTERNAL MODEL                 │
│   ┌──────────┐           ┌──────────────┐              │
│   │ /status  │──────────▶│ Capability   │              │
│   │ /mesh    │           │ Graph + Seal │              │
│   └──────────┘           └──────┬───────┘              │
│                                 │                       │
│                          PREDICTION ERROR               │
│                          ┌──────▼───────┐              │
│                          │  F = KL(P||A) │             │
│                          │  Drift > θ?   │             │
│                          └──────┬───────┘              │
│                                 │                       │
│                    ┌────────────┴────────────┐         │
│                    ▼                         ▼         │
│              PERCEPTION                   ACTION       │
│         (update evolution_hash)    (auto-tune io_uring)│
│                                                         │
│   JUDGE = GENERATIVE MODEL                             │
│   Predicts state, minimizes surprise, drives action.   │
└─────────────────────────────────────────────────────────┘
```

## References

- Friston, K. (2010). The free-energy principle: a unified brain theory?
- Vaked Swarm: /reflect, /wisdom, /status
- Genesis Seal: 7c242080
