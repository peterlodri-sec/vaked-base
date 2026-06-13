# Contributing to Vaked

Thank you for your interest in Vaked! This document outlines how to contribute code, design, and feedback.

## Core Principle: Grammar-First Design

**Vaked follows a grammar-first discipline:** new language features are designed in the EBNF grammar and language spec before implementation.

### Design Process

1. **Open a GitHub issue** describing the feature or change you want to propose
2. **Write an RFC** (Request for Comments) in `protocol/rfcs/` or a language design doc in `docs/language/`
   - For **protocol changes:** use `hcp-rfc-author` skill (if available) and follow the RFC template
   - For **language changes:** use `vaked-language-author` skill and document in EBNF + examples
3. **Request design review** (mention @peterlodri-sec or open a discussion)
4. **Update the EBNF** in `vaked/grammar/vaked-v0-plus.ebnf` once the design is approved
5. **Implement** the change in vakedc (parser, type checker, lowerer as needed)
6. **Add tests** and examples
7. **Submit a pull request** with the full commit history

### Why Grammar-First?

- Vaked's grammar is **the specification** (it appears in `docs/language/0011` and `0012`)
- Changing the grammar without updating the spec creates spec-drift (bad)
- Examples in the grammar clarify intent and catch ambiguities early
- The EBNF is checked into the repo and tested against (differential oracle in `tests/spec/`)

## Examples as Specifications

Examples are **executable specifications**. When an example doesn't compile:

```
vaked/examples/my-example.vaked ─→ [vakedc check] ─→ error
```

The error is a **language bug**, not an application bug. Fix the language (grammar, type system, constraints).

**Adding an example:**

1. Create `vaked/examples/<name>.vaked` (or in a subdirectory like `primitives/`)
2. Ensure it parses and type-checks: `python3 -m vakedc check vaked/examples/<name>.vaked`
3. Ensure it lowers without error: `python3 -m vakedc lower vaked/examples/<name>.vaked`
4. Add a comment at the top explaining what the example demonstrates
5. Run tests: `pytest tests/spec/test_vakedc.py -v`

## Branches and Versioning

### Development Branch

- **Main branch:** `main` (stable, released versions only)
- **Development branch:** check the Claude Code instructions for the assigned feature branch
  - All work happens here first
  - PR required before merge to main
  - CI runs on every commit (linter, type checker, spec tests)

### Versioning

Vaked uses **semantic versioning**: `MAJOR.MINOR.PATCH`

- **v0.x** — Research/prototype phase (breaking changes without notice until v1.0)
- **v1.0** — Stable API and grammar (breaking changes documented in CHANGELOG, changelog entry required)

**Changelog policy:**

Every commit that changes user-visible behavior (grammar, type system, emitter output) must have a corresponding entry in `CHANGELOG.md`:

```markdown
## [v0.2] — 2026-10-15

### Added
- New `fiber` field `policy { … }` for eBPF policy declaration

### Changed
- `runtime` now requires explicit `name` field (was optional)

### Removed
- Deprecated `engine.version` field (use `engine.pin` instead)

### Fixed
- Type checker now correctly handles cycles in mesh topology
```

## Code Organization

```
vaked-base/
├── docs/language/        # Specification (grammar, type system, lowering)
├── vakedc/               # Compiler implementation (Python, stdlib-only)
├── vaked/
│   ├── grammar/          # EBNF + examples
│   ├── schema/           # Built-in type catalog
│   └── examples/         # Case studies + primitives
├── protocol/             # HCP / Litany RFCs + data structures
├── daemons/              # Zig daemon specs (not yet implemented)
├── tests/spec/           # Specification tests (golden, differential oracle, determinism)
└── flake.nix            # Dev environment (Zig, BEAM, Rust, tooling)
```

## Testing

### Running Tests

```bash
pytest tests/spec/
```

### Test Categories

1. **Differential Oracle** — vakedc's parse/check output matches EBNF recognizer (grammar compliance)
2. **Golden Snapshot** — LPG and lowering output match hand-verified fixtures
3. **Determinism** — Repeated compilation produces byte-identical artifacts
4. **Spec Coverage** — All 0011/0012 rules are tested with positive and negative cases

### Adding Tests

- **New grammar rule?** Add positive (accept) and negative (reject) examples to `tests/spec/test_examples_parse.py`
- **New type-check rule?** Add a `.vaked` file to `vaked/examples/types/` with comments explaining the check
- **New lowering emitter?** Add a fixture to `vaked/examples/lowering/` (hand-authored expected output)
- **Determinism regression?** Create a minimal repro in `vaked/examples/` and add it to the determinism oracle

## Code Style

### Python (vakedc)

- **No external dependencies** — stdlib only (vakedc is portable)
- **Type hints** — Use them (Python 3.9+ supports `|` union syntax)
- **Docstrings** — Module and function docstrings for public APIs; internal helpers get comments only if non-obvious
- **Line length** — 100 columns (readability over strict length)
- **Imports** — Alphabetical order, stdlib first, no circular imports

Example:

```python
def check_conformance(block: dict[str, Any], schema: Schema) -> list[Diagnostic]:
    """Check that block conforms to schema (§1.1 of 0011).
    
    Returns a list of diagnostics (empty = conform).
    """
    diagnostics = []
    # Check required fields...
    return diagnostics
```

### Documentation

- **Spec language** — Use the notation from 0011/0012 (`⊨`, `⊑`, `≤`, `<`, etc.)
- **Worked examples** — Include code snippets showing the feature in action
- **Normative vs. informative** — Mark normative rules with `Normative.` or `This note defines…`

## Pull Request Process

1. **Create a feature branch** from the development branch
   - Naming: `feat/short-desc` or `fix/short-desc` or `docs/short-desc`
2. **Commit with clear messages:**
   ```
   type(scope): concise message
   
   Longer explanation if needed. Reference GitHub issues: fixes #123.
   ```
   - `type`: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`
   - `scope`: `grammar`, `type-system`, `lowering`, `vakedc`, `examples`, `protocol`, etc.
3. **Push and open a PR** with a title and description
4. **Link related issues** (e.g., `fixes #45`, `related to #67`)
5. **Wait for review** — at least one approval before merge
6. **Update CHANGELOG.md** if the change affects users

## Performance & Profiling

If you add features that might slow compilation:

```bash
# Profile a single example
python3 -m cProfile -s cumtime -m vakedc lower vaked/examples/operator-field.vaked 2>&1 | head -30

# Benchmark against baseline
python3 examples/evaluation/bench.py --example "operator-field.vaked" --iterations 20 --json after.json
# Compare against before.json
```

**Expectation:** Parse < 100ms, check < 100ms, lower < 200ms for typical 1500-line declarations.

## Documentation

- **Spec** lives in `docs/language/` (0001–0016 design series)
- **Reference** lives in README.md and inline EBNF comments
- **Tutorials** are in `docs/` (if added)
- **Decision logs** are in `docs/decisions/` (generated by ralph loop, see CLAUDE.md)

## Community

- **Issues:** Use GitHub Issues for bugs, design proposals, and questions
- **Discussions:** Use GitHub Discussions for brainstorming and RFCs
- **Email:** For security issues, email `cabotage@protonmail.com`
- **Acknowledgments:** Contributors are listed in CHANGELOG.md and (eventually) a CONTRIBUTORS file

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (to be determined; currently unlicensed).

---

**Thank you for contributing to Vaked!** 🎉
