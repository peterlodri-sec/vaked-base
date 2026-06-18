# RFC v0.9 — Thermodynamics of Compute & Honest Work

- **Status:** Draft · **Created:** 2026-06-18 · **Genesis:** 7c242080

## Abstract

Maxwell's Demon is a thought experiment: a tiny agent sits at a gate between
two chambers, observing molecular velocities. By opening the gate only for
fast molecules, it creates a temperature gradient — decreasing entropy
without expending energy. The paradox was resolved by Rolf Landauer: the
demon's *measurement* costs energy. Erasing one bit of information
dissipates kT ln 2 of heat. Information IS physical.

The Vaked Swarm's Honest Work ledger IS Maxwell's Demon. Every Work-Hash
entry converts raw compute (entropy) into verifiable network-truth (order).
The cost function maps directly: the energy expended computing a SHA-256
hash is the thermodynamic cost of reducing CapabilityGraph entropy by
one unit of verifiable state.

## Mapping

| Maxwell's Demon | Swarm Equivalent |
|-----------------|-----------------|
| Gas molecules | Raw compute cycles (agentic work) |
| Velocity measurement | Work-Hash computation (SHA-256) |
| Gate control | CapabilityGraph enforcement |
| Temperature gradient | Reduction in graph entropy |
| Landauer's limit (kT ln 2) | Cost per hash at hardware level |
| Information → Work | Compute → Verifiable truth |

## Cost Function

The entropy reduction ΔS of a Work-Hash entry is proportional to the
information gained:

```
ΔS = -Σ p(i) log₂ p(i)  [bits]
Energy cost = ΔS × kT ln 2  [joules]
Work-Hash cost = Energy cost × hardware_efficiency_factor
```

Where:
- `p(i)` is the probability distribution over CapabilityGraph states
- `kT ln 2` is Landauer's limit (~2.9×10⁻²¹ J at 300K)
- `hardware_efficiency_factor` accounts for real CPU overhead

## ASCII Summary

```
┌──────────────────────────────────────────────────────────┐
│           MAXWELL'S DEMON IN THE SWARM                   │
│                                                          │
│   CHAMBER A (entropy)     GATE         CHAMBER B (order)│
│   ┌────────────────┐      ┌──┐      ┌────────────────┐  │
│   │ raw compute    │      │  │      │ verifiable     │  │
│   │ agentic work   │─────▶│◉ │─────▶│ truth          │  │
│   │ unverified     │      │  │      │ Work-Hash      │  │
│   │ state space    │      │  │      │ ledger entry   │  │
│   └────────────────┘      └──┘      └────────────────┘  │
│                                                          │
│   THE DEMON = HONEST WORK LEDGER                        │
│   • Measures: compute output (SHA-256 hash)              │
│   • Decides: is this valid work? (CapabilityGraph)      │
│   • Acts:    append to ledger (reduce entropy)           │
│                                                          │
│   COST: Energy(compute) = ΔS × kT ln 2 × η              │
│   Every bit of truth costs joules. Thermodynamics.       │
└──────────────────────────────────────────────────────────┘
```

## Implementation

1. Every agentic computation produces a raw output.
2. The Honest Work ledger measures it (SHA-256 hash).
3. If CapabilityGraph validates the output, append Work-Hash entry.
4. The energy cost of that hash is the thermodynamic price of truth.

## References

- Landauer, R. (1961). Irreversibility and heat generation in the computing process.
- Bennett, C.H. (1982). The thermodynamics of computation — a review.
- Vaked Honest Work ledger: constellation.vaked.dev/work-ledger
- Genesis Seal: 7c242080
