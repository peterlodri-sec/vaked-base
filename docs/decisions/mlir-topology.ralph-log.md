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

## 2026-06-13 — Decision #2: Decision / question: Should memoryd (from 0014) and the Track‑D control plane (#
- **Track:** mlir-topology · **Models:** stage1 mimo-v2.5 · stage2 deepseek-v4-pro
- **Context snapshot:** HEAD 74e3092, 8 open issues

**Decision / question:** Should `memoryd` (from 0014) and the Track‑D control plane (#20) formally block on the `eventd` arena snapshot API (#16, #18)?  
**Options:**  
1. **Block.** Require `eventd`’s arena snapshot API (content‑addressed, refcount‑GC snapshots from `zig/substrate/arena.zig` – #16) to be implemented and validated before `memoryd` and the control plane begin runtime‑level work.  
2. **Proceed with a provisional backing store.** Implement `memoryd` against a temporary, non‑arena store (e.g., a plain append‑only file) and later swap in the arena.

**Recommendation:** **Block.** Both designs are fundamentally anchored in the arena‑snapshot contract.  
- `docs/language/0014-memory-primitive.md` states: “Memory entries are events on the per‑runtime hash‑chained `eventd` log … memory state is the fold over those events, resolving content **against the arena (#16)**.” A provisional store breaks the fold‑verifiability and rewind‑to‑byte‑exact‑state guarantees.  
- Issue #20 (control plane replay/rewind/jump/step) explicitly lists the eventd log + arena snapshots as its substrate; without arena‑anchored snapshots the “rewind preserves concurrent siblings (#16 structural sharing)” property cannot hold.  
- The `eventd` hardening backlog (#35) identifies snapshot/compaction as critical for boot‑time chain verification; delivering it now unblocks both dependents and removes a known design risk.

**Risks:**  
- Delays `memoryd` and the control plane until the arena snapshot API is complete. The 0014 grammar and emitter are already landed (see 0014 §Lowering), so the agent‑side declaration surface is defined and the implementation gap is purely runtime.  
- Unforeseen complexity in `eventd`’s snapshot representation (checkpoint entry format, interaction with GC floor) may push the timeline. This is mitigated by explicit design guidance in #16 and #35, and the fact that `eventd`’s core append‑only log is implemented.

**Next actions:**  
1. Open a focused tracking issue: “Implement arena snapshot/checkpoint API for eventd (→ unblocks 0014 memoryd and #20 control plane).” Scope the representation (checkpoint‑entry folding a prefix, arena content‑hash, GC‑floor integration) per the snapshot/compaction item in #35, and tie it to the eventd design’s open question “rotation without breaking the chain” noted there.  
2. Update epic #17 to reflect that 0014 (*runtime* phase) and #20 are gated on eventd arena snapshots.  
3. After the snapshot API lands, proceed with `memoryd` as described in 0014’s runtime contract (mining daemon, recall server, `mem` capability enforcement), folding events directly against the arena.

**Confidence:** high

