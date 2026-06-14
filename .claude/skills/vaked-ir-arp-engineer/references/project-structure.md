# Directory Structure

```
docs/
  language/
    references/
      parallel-reference-pack.md (94 lines)
      session-2026-06-08-sparks.md (22 lines)
    0001-language-manifesto.md (16 lines)
    0003-reference-map.md (24 lines)
    0008-parallel-fibers-indexes-surfaces.md (215 lines)
    0009-kickoff-context-for-dedicated-session.md (60 lines)
    0010-mirageos-unikernel-surface.md (48 lines)
    0011-type-system.md (646 lines)
    0012-lowering.md (830 lines)
    README.md (91 lines)
vaked/
  examples/
    engines/
      zig.vaked (8 lines)
    lowering/
      gen/
        catalog/
          zigCorpus.jsonl (3 lines)
        zig/
          mediaCompress.json (20 lines)
        RUNTIME.md (59 lines)
      flake.nix (103 lines)
      provenance.json (132 lines)
      README.md (75 lines)
    primitives/
      catalog.vaked (8 lines)
      device.vaked (10 lines)
      fiber.vaked (15 lines)
      index.vaked (28 lines)
      mediaPipeline.vaked (20 lines)
      mesh.vaked (19 lines)
      parallel.vaked (15 lines)
      stream.vaked (15 lines)
      surface.vaked (20 lines)
    types/
      capability-attenuation.vaked (44 lines)
      conformant.vaked (35 lines)
      README.md (54 lines)
      rejected.vaked (44 lines)
      schema-constraints.vaked (38 lines)
    operator-field.vaked (63 lines)
  grammar/
    README.md (231 lines)
    vaked-v0-plus.ebnf (260 lines)
  schema/
    builtins.vaked (179 lines)
    parallel-types.md (508 lines)
vakedc/
  __init__.py (47 lines)
  __main__.py (269 lines)
  check.py (1277 lines)
  emit.py (160 lines)
  graph.py (159 lines)
  lexer.py (388 lines)
  lower.py (1400 lines)
  parser.py (844 lines)
  README.md (124 lines)
  resolve.py (345 lines)
```