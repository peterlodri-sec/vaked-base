# RFC v0.9 — Stigmergic Routing & Reflection-Log Pheromones

- **Status:** Draft · **Created:** 2026-06-18 · **Genesis:** 7c242080

## Abstract

Ants don't communicate directly. They modify the environment — leaving
pheromone trails that influence the behavior of ants that follow. Stronger
trails attract more ants, reinforcing successful paths. Weaker trails
evaporate, abandoning failed routes. This is **stigmergy**: indirect
coordination through environmental markers.

The Vaked Swarm's `/reflect` endpoint IS the pheromone trail. Every network
event, latency measurement, and topology shift is logged — creating a
historical memory that agents can "smell" to choose optimal compute-paths
without querying the network directly.

## Mapping

| Ant Colony | Swarm Equivalent |
|------------|-----------------|
| Pheromone trail | /reflect NetworkEvents |
| Trail strength | Historical latency (weighted by recency) |
| Evaporation | Exponential decay of old log entries |
| Foraging ant | Sub-agent seeking compute path |
| Nest → Food path | Optimal route between nodes |
| Pheromone reinforcement | Successful path → stronger log weight |

## Implementation

1. Every network event logged to `/reflect` includes latency, path, and timestamp.
2. Agents query the local `/reflect` arena (memory-mapped) before routing.
3. Paths with low historical latency get higher "pheromone weight."
4. Old entries decay exponentially (half-life: configurable, default 24h).
5. Agents choose the path with highest weight — no network query needed.

## ASCII Summary

```
┌──────────────────────────────────────────────────────────┐
│              STIGMERGIC ROUTING IN SWARM                 │
│                                                          │
│   ANT 1                    ANT 2                    ANT 3│
│   ┌───┐                    ┌───┐                   ┌───┐ │
│   │ 🐜│──┐                 │ 🐜│──┐                │ 🐜│ │
│   └───┘  │                 └───┘  │                └───┘ │
│          ▼                        ▼                       │
│   ═══════════════════════════════════════════              │
│   ║  PHEROMONE TRAIL = /reflect LOGS         ║           │
│   ║  ████████░░░░  Paris→Helsinki  126ms     ║           │
│   ║  ██████░░░░░░  US-West→Helsinki 720ms    ║           │
│   ║  ██░░░░░░░░░░  Singapore→Helsinki 813ms  ║           │
│   ═══════════════════════════════════════════              │
│                    │                                       │
│   ┌────────────────┴────────────────┐                     │
│   ▼                                 ▼                     │
│   STRONG TRAIL                      WEAK TRAIL            │
│   (many successes)                  (evaporating)         │
│   → preferred path                  → avoided path        │
│                                                          │
│   NO DIRECT QUERY. AGENTS SMELL THE TRAIL.               │
└──────────────────────────────────────────────────────────┘
```

## Algorithm

```
function choose_path(destinations):
    max_weight = 0
    best_path = nil
    for each path in /reflect.NetworkEvents:
        age = now - path.timestamp
        weight = path.success_count × exp(-age / half_life)
        if weight > max_weight:
            max_weight = weight
            best_path = path
    return best_path
```

## References

- Grassé, P.P. (1959). La reconstruction du nid et les coordinations interindividuelles.
- Theraulaz, G. & Bonabeau, E. (1999). A brief history of stigmergy.
- Vaked /reflect endpoint: constellation.vaked.dev/reflect
- Genesis Seal: 7c242080
