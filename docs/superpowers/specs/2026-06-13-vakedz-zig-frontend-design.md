# Design — vakedz, the Zig front-end for Vaked

**Date:** 2026-06-13 · **Status:** design (v0.1 shipped: parse + cache) ·
**Research:** [`../research/2026-06-13-vakedz-fanout-research.md`](../research/2026-06-13-vakedz-fanout-research.md) ·
**Plan:** [`../plans/2026-06-13-vakedz-zig-frontend.md`](../plans/2026-06-13-vakedz-zig-frontend.md)

## Problem

The Vaked compiler exists as a Python reference (`vakedc/`: `parse → check →
lower`). The runtime mantra is *"Zig enforces"* — the daemons are Zig, and the
front-end that feeds them should ultimately be Zig too: fast, single-binary,
embeddable, no Python runtime at the enforcement boundary. We need a **faithful**
Zig front-end that produces **byte-identical** artifacts to `vakedc`, so the two
can be cross-checked forever and the Python stays the executable spec.

Two owner decisions framed this design:
1. **Cache layer = both.** Build a content-addressed compiler cache now (tooling,
   no grammar change) **and** file a tracking issue for a future language-level
   `cache` construct.
2. **Scope = full `parse → check → lower`** as the eventual target; v0.1 ships the
   front-end (parse) + the cache, with check/lower scaffolded and the rest
   tracked as the dogfooding backlog.

## Non-goals

- Not a rewrite of the *language*. The grammar, type system, and lowering
  contract are owned by `vaked/grammar/`, `docs/language/0011`, `0012`. `vakedz`
  ports the **implementation**, it does not evolve the language. Any versioned-
  language change still needs a GitHub issue first (convention 2).
- Not a divergent dialect. "Faithful" is enforced mechanically (below), not by
  intention.

## Architecture

A top-level `vakedz/` package mirroring `vakedc/`, one module per stage:

```
main.zig → { parse | check | lower | all | cache }
  json.zig    canonical JSON (the byte-parity contract)
  lexer.zig   v0.3 tokenizer            (← vakedc/lexer.py)
  parser.zig  recursive-descent AST      (← vakedc/parser.py)
  graph.zig   AST → LPG → canonical emit (← resolve.py + graph.py + emit.py)
  cache.zig   the ralphloop-cache primitive
  check.zig   0011 checker (scaffold)
  lower.zig   0012 lowering (scaffold)
```

Memory: an arena per CLI invocation (the compiler is a batch process; freeing
individually buys nothing). Errors carry `file:line:col` and a message.

### The byte-parity contract (the heart of the port)

`vakedc` does **not** blanket-sort keys. The structural wrappers are fixed
order; only the **props subtree** is recursively key-sorted. `json.zig`
therefore emits objects in **insertion order** and exposes `sortRecursive`,
which `graph.zig` applies **only** to each node's `props` value. Nodes sort by
`id`; edges by `(from, label, to, props)`. Strings escape like CPython's `json`
(no `/` escaping, UTF-8 passthrough); output ends in a newline. This single
contract is what makes `vakedz parse` == `vakedc parse` byte-for-byte; it is
verified, not assumed (see Verification).

### The ralphloop-cache (the native primitive)

`cache.zig` is a direct application of ralph's research bet
(`tools/ralph/PURPOSE.md`): *compile history into an immutable, content-addressed
increment, and the loop runs at near-flat cost while staying coherent and
rewindable.* As a compiler primitive that means:

- **Key** (deterministic): `{event=phase, file, source_sha256, grammar_version}`.
- **Value**: `output_sha256`, with output bytes stored content-addressed at
  `.vakedz-cache/cas/<sha256>`.
- **Ledger**: `.vakedz-cache/ledger.jsonl` — the **frozen** ralph/eventd chain
  `{seq, prev, payload, hash}`, `hash = sha256(prev_hex ++ canonical(payload))`,
  GENESIS `"0"*64`. Byte-compatible with `ralphcore.py`/`eventd/core.py`, so all
  three cross-verify.
- **Hit** = hash the source, find the latest matching ledger entry, replay the
  CAS blob. **Miss** = compute, write CAS, append one entry. The payload is
  **clock-free**, so identical source ⇒ identical entry: the loop is
  content-addressed, replayable (`cache verify` → longest-valid-prefix), and
  tamper-evident.

This closes the loop **literally**: CI builds `vakedz`, runs it against the
goldens, and the cache replays its own history; the thing that builds the
language is built on the language's core idea.

### Why "both" for the cache, not a grammar construct now

A language-level `cache` kind (e.g. `cache foo { key=…, ttl=… }`) is a real
future capability — declarable, lowerable to a daemon-backed CAS — but it is a
**versioned-language change** (grammar + schema + lowering + an issue). The
compiler cache needs none of that and unblocks the loop today. So: tooling
primitive now; language construct tracked (issue) for when a `.vaked` program
wants to *declare* a cache, not just benefit from one.

## Scope — v0.1

Shipped: `parse` (lexer→parser→LPG→canonical JSON, byte-identical to `vakedc`)
and the `ralphloop-cache`. `check`/`lower` are wired scaffolds that refuse to
assert success and point at the backlog. Front-end coverage targets the
constructs exercised by the committed goldens (`runtime, engine, index, stream,
fiber, surface, parallel`, imports, signatures, records, inherit, refs, calls,
lists, durations); other constructs parse but are validated only by adding their
goldens (the natural way to grow coverage).

## Verification (the closed loop)

- `zig build test` — in-source unit tests per module (canonical JSON ordering &
  escaping, lexer disambiguation, parser shape, graph emit, cache hashing).
- `vakedz/test/crossverify.sh` — the gate: `vakedz parse <src>` must equal the
  committed golden **and** the golden must still equal `vakedc parse <src>` (drift
  guard). Run by `task vakedz-verify` and `.github/workflows/vakedz-ci.yml`.
- Goldens are generated from the Python reference and committed under
  `vakedz/test/golden/`. New examples → new goldens → wider coverage.

## Risks / open questions

- **Zig version drift.** The devshell's Zig is unpinned (nixpkgs unstable);
  `vakedz` targets the `build.zig.zon` floor (0.16) and CI pins it. If the
  devshell moves ahead and the std API shifts, the build breaks loudly — bump
  the floor and adapt (tracked). Pinning Zig in the flake is a recommended
  follow-up.
- **NFC gate** not yet ported (ASCII sources unaffected) — tracked.
- **check/lower fidelity** is the large remaining surface; the research doc's
  diagnostic table (Strand B) and emitter slice (Strand C) are the spec.
