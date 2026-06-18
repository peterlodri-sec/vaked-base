# Stigmergy: The Memory of the Mesh

*How Ant Pheromones Inspired Swarm Routing*

Ants don't have meetings. They don't send packets. They don't run BGP.

When an ant finds food, it walks back to the nest leaving a chemical
trail. Other ants encounter the trail, follow it, find the food, and
reinforce the trail on their return. Over time, the shortest path
accumulates the strongest pheromone concentration — not because any ant
"planned" it, but because ants taking shorter trips deposit pheromone
more frequently. The trail IS the memory of the colony.

This is **stigmergy**: coordination through environmental modification.
The environment holds the intelligence. The agents just follow it.

### The Swarm's Pheromone Trail

The Vaked Swarm's `/reflect` endpoint IS the pheromone trail. Every time
the Sentinel logs a `NetworkEvent` — latency between Paris and Helsinki,
a topology shift when Hillsboro goes quiet, a successful packet route
through Nuremberg — it's depositing a digital pheromone.

Agents don't query the network to find the best path. They don't need to.
They read the local `/reflect` memory-mapped arena. The trail tells them:
"Paris→Helsinki: 126ms, 10,000 successes, reinforced heavily. US-West→
Helsinki: 720ms, still working but weaker trail. Singapore: 813ms,
trail evaporating — avoid unless necessary."

### Evaporation

Pheromones evaporate. Old trails fade. This is a feature, not a bug. If
a path that was fast yesterday becomes slow today (congestion, node
failure, DDoS), the old pheromone decays and the trail weakens. New,
faster paths emerge naturally as agents explore alternatives. The system
self-tunes without a central planner.

### No Query Cost

The beauty of stigmergy is that it costs nothing to "ask." The ant
doesn't query the colony — it smells the ground. The agent doesn't query
the network — it reads a memory address. The `/reflect` arena is mapped
into every node's address space. Reading it is a local operation. Zero
network round-trips. Zero latency. Just the weight of history guiding
the next step.

The mesh remembers. The mesh learns. The mesh routes itself.

---
*Genesis: 7c242080 · Pheromone half-life: 24h · Trails: 6 active*
