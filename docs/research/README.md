# docs/research — deep-research batch (PR-pipeline dogfood)

Date: 2026-06-14 · Branch: `claude/vaked-pr-pipeline-dogfood-pdl4sk`

A deep-research batch (run via the `deep-research` harness: fan-out → fetch →
adversarial verify → synthesize) plus a layer-by-layer explainer and an
end-to-end demonstration of Vaked across swarms. Together they answer: *does the
PR-multimodel-pipeline dogfood reflect the state of the art, and does the
language/compiler/runtime actually work end-to-end?*

| Document | What it covers |
|----------|----------------|
| [`2026-06-14-capability-attenuation-multi-agent-llm.md`](2026-06-14-capability-attenuation-multi-agent-llm.md) | **Report A** — least-privilege capability attenuation for heterogeneous multi-agent LLM systems (ocap/POLA, MCP authz, sole-publisher broker, static verification, failure modes). Validates the **mesh / authority** graph. |
| [`2026-06-14-multimodel-author-reviewer-loops.md`](2026-06-14-multimodel-author-reviewer-loops.md) | **Report B** — do strong-author + cheaper-reviewer multi-model coding loops improve correctness, and how to model fix-loops. Validates the **workflow / ordering** graph. |
| [`2026-06-14-how-vaked-works-layer-by-layer.md`](2026-06-14-how-vaked-works-layer-by-layer.md) | Explainer: Vaked under the compiler, six compiler layers + the runtime stack, 7 graph-topology illustrations, and 14 flashcards. |
| [`2026-06-14-vaked-e2e-swarm-demonstration.md`](2026-06-14-vaked-e2e-swarm-demonstration.md) | End-to-end run of `vakedc parse → check → lower` across nine swarm declarations, with the artifact trees each produces. |

## Headline findings

- **Authority graph (mesh):** attenuation-only delegation, a single side-effect
  broker, and gating the egress leg are the three load-bearing recommendations
  across the strongest 2025–2026 sources — exactly what the dogfood's `mesh` +
  `E-CAP-ATTENUATION` + sole `mcp.github_write` broker encode. Vaked is, on the
  static-verification axis, slightly ahead of the literature.
- **Ordering graph (workflow):** cross-model review beats self-review by large,
  statistically-significant margins; an advisory read-only reviewer sidesteps the
  cheap-judge rubber-stamping failure mode; fix-loops belong as bounded retries,
  not back-edges — and compile-time cycle/depth checks are ahead of the
  runtime-only bounds in every shipping agent framework surveyed.
- **End-to-end:** nine structurally different swarms type-check and lower to
  deterministic artifact trees (Nix / OTP / Zig / eBPF / CrabCC) with no grammar
  changes, demonstrating language + compiler + runtime as one pipeline.

## Caveats

Several of the sharpest 2026 results are single-author preprints with author-built
benchmarks, not independently reproduced; confidence tags (HIGH/MED/LOW) and
flagged disagreements are preserved in each report. Capability graphs confine the
*consequences* of prompt injection, not a model's *compliance* — defense-in-depth
(e.g. `agent_guardd`'s egress membrane, a non-LLM test/SAST evidence layer)
remains necessary.
