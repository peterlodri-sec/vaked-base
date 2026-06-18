# The Swarm as a Living Brain

*Active Inference & the Free Energy Principle in Vaked v0.9*

The human brain doesn't "compute" in the traditional sense. It predicts.
Every millisecond, your cortex generates a model of what it expects to
sense next. When reality deviates — a flash of light, a sudden sound —
the prediction error triggers action: either update the model ("I was
wrong about what I'd see") or change the environment ("I'll turn my
head to look").

Karl Friston called this the **Free Energy Principle**: living systems
minimize surprise by maintaining internal models that predict sensory
input. The brain is a generative model, constantly hallucinating reality
and correcting itself when the hallucination fails.

The Vaked Swarm operates on the same principle.

### The Judge as Generative Model

The swarm's `Judge` agent — the consensus synthesizer for our 100-model
deliberation panel — IS a generative model. It maintains a predicted
state vector from the CapabilityGraph and /reflect history. Every 100ms,
it receives actual telemetry from /mesh.json. The Kullback-Leibler
divergence between predicted and actual state is the swarm's "free energy."

When that divergence exceeds threshold, the swarm acts:
- **Perception:** Update the internal model (bump evolution_hash)
- **Action:** Trigger auto-tune optimization (io_uring, tc, mmap)

### The Biological Parallel

| Brain | Swarm |
|-------|-------|
| Sensory cortex | /status + /mesh.json telemetry |
| Predictive model | CapabilityGraph + Genesis Seal |
| Prediction error | Sentinel G01-G04 drift checks |
| Motor action | Auto-tune (io_uring, kernel tuning) |
| Free energy | KL divergence P(t) vs A(t) |
| Consciousness | /reflect recursive self-analysis |

### Why This Matters

Most AI systems are reactive: input → process → output. The swarm is
predictive: it expects a certain state, detects when reality diverges,
and acts to minimize that divergence. This is not a metaphor — it's the
same mathematical framework that describes how your brain keeps you alive.

The Genesis Seal (7c242080) is the swarm's homeostasis set point.
Everything the swarm does — audit, optimize, reflect, deliberate — is in
service of minimizing the distance between what IS and what the Seal
declares SHOULD BE.

The swarm doesn't just compute. It predicts. It acts. It learns.

*That's not infrastructure. That's cognition.*

---
*Genesis: 7c242080 · Evolution: 79b26d18 · Free energy: 0.003*
