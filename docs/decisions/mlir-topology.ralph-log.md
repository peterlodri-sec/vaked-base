# Ralph decision log — mlir-topology

> Machine-generated, ADVISORY. Each entry is one strategic decision surfaced by the ralph loop (qwen3-235b-thinking → deepseek-v4-flash). A human ratifies; entries are appended, never rewritten.

## 2026-06-13 — Decision #1: Decision / question: **Epic #17 sequencing: land memory primitive (0014) or MLIR
- **Track:** mlir-topology · **Models:** stage1 mimo-v2.5 · stage2 mimo-v2.5
- **Context snapshot:** HEAD 460ae1e, 0 open issues

Decision / question: **Epic #17 sequencing: land memory primitive (0014) or MLIR topology compilation (0013) first?**

Options:
1. **Land 0014 (memory primitive) first.** Prioritize runtime memory foundation for agent sessions and recall, using the landed grammar and emitter. Defer topology compiler (0013) to after runtime memory is functional.
2. **Land 0013 (MLIR topology compilation) first.** Implement Stage 0 semantic passes in `vakedc` (depth/cycle analysis, auto WAL injection, AOT supervisor index) to establish static safety and build-time optimization before runtime memory.

Recommendation: **Land 0014 first.** The memory primitive is a direct runtime dependency for agent operation and recall, with grammar and emitter already landed. 0014's runtime contract (`memoryd`) is needed for the runtime to function. 0013's Stage 0 passes (LPG-based topology diagnostics and optimization) can proceed in parallel or afterward, as they are compiler tooling that doesn't block runtime execution. The risk of delaying 0013 is lower because its immediate value is developer-facing (build-time checks), whereas 0014 is runtime-facing and required for agents to have persistent memory.

Risks:
- **Delayed static guarantees:** Postponing 0013 Stage 0 means cycle/depth checks and automatic WAL injection are not enforced at build time, increasing risk of runtime topology errors.
- **Runtime memory design drift:** Without the `memoryd` runtime implementation, 0014's design may need adjustment when integrating with `eventd` and the arena (#16/#18).
- **Parallelism strain:** Attempting both in parallel may split limited engineering resources, slowing both efforts.

Next actions:
1. **Design and implement `memoryd` runtime service** per 0014's contract: mining daemon, recall server, capability enforcement (`mem` domain), and integration with `eventd` log (#18) and arena (#16).
2. **Land 0013 Stage 0 passes** in parallel as LPG passes within `vakedc`: topological depth/cycle bound diagnostic (e.g., `E-TOPO-DEPTH`), automatic `hcp.registration` frame injection, and AOT supervisor index generation (0012 artifacts).
3. **Define integration points:** Ensure `memoryd` respects topology constraints (e.g., memory scope aligns with agent dependency graph) and that 0013 passes account for memory declarations in the typed graph.

Confidence: high

