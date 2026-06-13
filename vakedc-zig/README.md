# vakedc-zig — Zig-based Vaked Compiler

A native Zig implementation of the Vaked language compiler, bootstrapped for embedding in Zig enforcement daemons.

## Status

**Phase 1 (in progress)**: Lexer + Parser + LPG → JSON

- ✅ Design specification ([`docs/superpowers/specs/2026-06-13-vakedc-zig-compiler-bootstrap.md`](../docs/superpowers/specs/2026-06-13-vakedc-zig-compiler-bootstrap.md))
- ✅ Phase 1 implementation plan ([`docs/superpowers/plans/2026-06-13-vakedc-zig-phase-1.md`](../docs/superpowers/plans/2026-06-13-vakedc-zig-phase-1.md))
- 🚧 Lexer (stub → implementation)
- 🚧 Parser (stub → implementation)
- ⏳ Graph builder + resolver
- ⏳ Canonical JSON emission
- ⏳ Phase 2: Type checker + lowering
- ⏳ Phase 3: LSP server + dogfeeding

## Building

```bash
cd vakedc-zig
zig build
```

Produces `zig-cache/bin/vakedc-zig`.

## Usage

### Parse a .vaked file into JSON

```bash
./vakedc-zig parse ../vaked/examples/primitives/fiber.vaked --print
```

Writes canonical JSON to stdout (matching Python `vakedc` byte-for-byte).

### Emit token stream (debug)

```bash
./vakedc-zig lex ../vaked/examples/primitives/fiber.vaked
```

### Emit AST (debug)

```bash
./vakedc-zig parse-ast ../vaked/examples/primitives/fiber.vaked
```

## Testing

```bash
zig build test
```

Runs unit tests. Integration tests compare against Python `vakedc` reference:

```bash
# In repo root:
./vakedc-zig/zig-cache/bin/vakedc-zig parse vaked/examples/primitives/fiber.vaked --print > /tmp/zig.json
python3 -m vakedc parse vaked/examples/primitives/fiber.vaked --print > /tmp/py.json
diff /tmp/zig.json /tmp/py.json  # should be empty
```

## Architecture

| Module | Responsibility |
|--------|-----------------|
| `lexer.zig` | UTF-8 → tokens with exact spans; NFC validation; newline group-tracking |
| `parser.zig` | Tokens → AST (recursive descent, PEG-ordered, soft-keyword dispatch) |
| `graph.zig` | AST → Labeled Property Graph (nodes + edges with stable IDs) |
| `resolver.zig` | Symbol table + ref resolution + external stub creation |
| `emit.zig` | LPG → canonical JSON (stable key order, deterministic) |
| `main.zig` | CLI: `parse`, `lex`, `parse-ast` subcommands |

**Data flow**:

```
Source file → Lexer (tokens) → Parser (AST)
  → Graph builder (LPG nodes) → Resolver (edges + refs)
  → Emitter (canonical JSON)
```

## Notes

- **Stdlib only**: No external dependencies (matching Zig philosophy of self-contained binaries).
- **Determinism**: Identical source → identical JSON bytes across runs (even with different Zig/host versions).
- **Span fidelity**: Exact byte offsets from lexer → graph provenance (enables error messages with source attribution).
- **Parity target**: `vakedc-zig parse` output must match Python `vakedc parse --print` byte-for-byte (test oracle).

## Dogfeeding Plan

Once lowering is complete:

1. Write `hosts/vakedos/vakedos.vaked` (complete NixOS host declaration)
2. Compile: `vakedc-zig lower vakedos.vaked --out /tmp/vakedos`
3. Deploy: `nixos-rebuild switch --flake /tmp/vakedos`
4. Observe: eBPF policy + OTel traces from running system
5. Feed back: decisions → `tools/ralph/state/events.jsonl` → `memory ralphDecisions`

## References

- **Grammar**: [`vaked/grammar/vaked-v0-plus.ebnf`](../vaked/grammar/vaked-v0-plus.ebnf)
- **Type system**: [`docs/language/0011-type-system.md`](../docs/language/0011-type-system.md)
- **Lowering**: [`docs/language/0012-lowering.md`](../docs/language/0012-lowering.md)
- **Reference (Python)**: [`vakedc/README.md`](../vakedc/README.md)
- **Examples**: [`vaked/examples/`](../vaked/examples/)

## License

Same as vaked-base (see LICENSE).
