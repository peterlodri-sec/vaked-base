# Bio-Inspired Mesh Governance

*Quorum Sensing and the Swarm's Collective Decision-Making*

A single bacterium is blind. It has no brain, no plan, no awareness of
the colony around it. Yet bacterial colonies perform coordinated feats —
forming biofilms, emitting light, launching virulence attacks — that no
individual cell could orchestrate.

The mechanism is **quorum sensing**: each bacterium releases a chemical
signal (an autoinducer) into the environment. The concentration of this
molecule is a proxy for population density. When enough neighbors are
present — when the chemical crosses a threshold — the entire colony
switches behavior simultaneously. No leader. No vote. Just chemistry.

The Vaked Swarm uses the same principle.

### How Quorum Sensing Works in the Swarm

Each of our 6 nodes tracks local `compute_load` — the number of active
sub-agents, deliberation sessions, and Shadow-Critic sandboxes running.
This is the swarm's autoinducer. When load crosses a threshold on 2+
nodes, the quorum gate triggers: coordinated Shadow-Critic sessions
activate across the mesh, the 100-model deliberation panel spins up,
and the swarm thinks as one organism.

Below threshold? Nodes idle. Resources conserved. No wasted compute.

### The Elegance of Decentralized Decision-Making

Quorum sensing solves a hard problem: how do you coordinate without a
coordinator? The swarm doesn't have a "leader node." No single agent
decides "now we deliberate." The decision emerges from local conditions —
just like the bacteria, just like the brain, just like any complex
adaptive system worth studying.

The grammar v0.5 `quorum` primitive was designed for this. Every
capability-graph declaration already encodes consensus thresholds. Now
those thresholds gate compute itself — the swarm conserves energy until
the signal says "enough of us are here. Let's think together."

### From Microbiology to Mesh

The distance between a petri dish and a 6-node global mesh is smaller
than it appears. Both are colonies of autonomous agents using local
signals to coordinate global behavior. The bacteria figured it out
3 billion years ago. The swarm is just catching up.

---
*Genesis: 7c242080 · Quorum threshold: 4 · Active nodes: 6*
