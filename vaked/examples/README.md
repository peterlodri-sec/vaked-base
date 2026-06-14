# Vaked Language Examples

All `.vaked` files here are calibrated against the grammar
(`vaked/grammar/vaked-v0-plus.ebnf`), the type system
(`docs/language/0011-type-system.md`), and the built-in schema catalog
(`vaked/schema/parallel-types.md`). Every file is expected to parse and check
clean under `vakedc check`.

## Structure

### `operator-field.vaked` — integration example

The primary integration fixture. Declares a complete `runtime` block with
indexes, streams, fibers, surfaces, and a parallel group. Used by the test
suite as the parser/checker golden source and by `vaked/examples/lowering/`
as the lowering input.

### `primitives/` — one file per built-in primitive kind

Each file is a minimal, self-contained example of one primitive:

| File | Primitive | What it demonstrates |
|------|-----------|----------------------|
| `index.vaked` | `index` | source list, normalize, chunk, trust, emit |
| `catalog.vaked` | `catalog` | `from`, `key`, `emit` |
| `stream.vaked` | `stream` | source channel, type, retention, fps |
| `fiber.vaked` | `fiber` | engine ref, input/output, policy, observe |
| `surface.vaked` | `surface` | mode, fps, input refs, views |
| `mesh.vaked` | `mesh` | nodes, capabilities, routes |
| `parallel.vaked` | `parallel` | fibers list, strategy, supervisor, backpressure |
| `device.vaked` | `device` | driver, mount, permissions, observe |
| `mediaPipeline.vaked` | `mediaPipeline` | source, stages (resize + encode), sink |

**Coverage gap:** declaration kinds `import`, `host`, `budget`, `runclass`,
`ebpf`, `observability`, and the `@annotation` syntax have no examples yet.
These are valid grammar constructs (see `vaked/grammar/vaked-v0-plus.ebnf`)
awaiting a dedicated example file.

### `types/` — type-layer examples

Exercises the type-checking pipeline (0011). Has its own
[`types/README.md`](./types/README.md).

| File | What it demonstrates |
|------|----------------------|
| `conformant.vaked` | declarations that pass `vakedc check` |
| `rejected.vaked` | declarations that fail with expected diagnostic codes |
| `schema-constraints.vaked` | closed constraint set (§3) |
| `capability-attenuation.vaked` | POLA / attenuation checks (§4) |

### `engines/` — engine declarations

| File | What it demonstrates |
|------|----------------------|
| `zig.vaked` | Zig engine declaration with package and config refs |

### `lowering/` — lowering fixtures

Expected-output fixtures for `operator-field.vaked`. The test suite compares
`vakedc lower` output byte-for-byte against the committed files in
`lowering/gen/`. Has its own [`lowering/README.md`](./lowering/README.md).

| Artifact | Source |
|----------|--------|
| `gen/RUNTIME.md` | generated docs (0012 §5.1) |
| `gen/zig/mediaCompress.json` | Zig daemon config (0012 §5.2) |
| `gen/catalog/zigCorpus.jsonl` | CrabCC catalog (0012 §5.3) |
| `provenance.json` | per-run provenance record (0012 §6.2) |
