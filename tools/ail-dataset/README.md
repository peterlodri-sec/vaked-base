# ail-dataset — ARP fine-tuning dataset

A seed dataset for fine-tuning a model to emit **ARP** (Agent Register
Protocol) graphs: a *validated* AI-lish V1 execution-graph core with the four
ARP behavioral primitives interleaved.

- **ARP** is specified in [`protocol/rfcs/0009-arp.md`](../../protocol/rfcs/0009-arp.md).
- The grammar it rides on, **AI-lish V1**, is specified in
  [`docs/ailish/2026-06-14-ailish-v1-rfc.md`](../../docs/ailish/2026-06-14-ailish-v1-rfc.md)
  and implemented in the [`ailish`](../ailish/) crate (parser + guardrail +
  formatter, plus the `ailishcheck` binary).

ARP is **purely additive** (RFC 0009 §1): AI-lish V1 owns the grammar, the
eight registers and their monad rules, typed atoms, dataflow/justification
edges, gates, and the `gate(*:fail)` → `R:commit` freeze invariant. ARP adds
only the four behavioral signals below. They are **advisory** — they carry no
authority, do not gate or mutate state, and are **not** part of the V1 grammar.

## The four behavioral primitives (RFC 0009 §2)

| Primitive | Spelling | Meaning |
|-----------|----------|---------|
| **Stride** | `[STRIDE: a → b → c]` | A declared progress arc, emitted *before* acting — a retry/checkpoint anchor. |
| **Tension** | `[T:N]`, `N ∈ 0..100` | Goal-distance: high early, low as the task converges. Drives compression; gives a harness an escalation threshold. |
| **Valence** | `[+]` / `[-]` / `[!]` | A polarity signal emitted *after* a tool result: good / bad / attention. |
| **Branch** | `[BRANCH: a \| b; condition: X]` | An explicit fork: alternative paths and the condition that selects between them. |

Because the primitives are advisory annotations interleaved among V1 frames,
they can always be **stripped** to recover the underlying V1 graph — that is the
core integrity invariant this dataset is built on (see *Validation* below).

## Record schema

`arp-examples.jsonl` is one JSON object per line. Keys:

| Key | Meaning |
|-----|---------|
| `id` | Stable record id (e.g. `arp-001-squash-merge-divergence`). |
| `title` | One-line human title. |
| `difficulty` | One of `exciting`, `special`, `complex`. |
| `tags` | Topic tags. |
| `problem` | What went wrong. |
| `state` | The situation at the decision point. |
| `solution` | How it was resolved. |
| `ail_v1` | The AI-lish **V1 core only** — MUST pass `ailishcheck`. |
| `arp` | The dense ARP graph: the same V1 core with STRIDE / T / valence / BRANCH primitives interleaved. |
| `read` | A one-paragraph natural-language gloss (problem → state → solution). |

**Invariant:** stripping the ARP primitives from `arp` reduces to exactly
`ail_v1` (modulo blank lines / trailing whitespace). So the validated V1 core is
provably the same graph the ARP record is built around.

## Validation

Run:

```bash
python3 generate.py validate            # uses ./arp-examples.jsonl
python3 generate.py validate --jsonl other.jsonl
```

For every row this performs two checks and prints a `strip | ailishcheck`
PASS/FAIL table (exit nonzero if any row fails):

1. **ARP-strip round-trip.** `arp` has its primitives removed — lines that are
   solely `[STRIDE: …]`, `[T:N]`, or `[BRANCH: …]` are dropped, and a trailing
   `[+]`/`[-]`/`[!]` valence token is stripped from any remaining line — and the
   result is asserted equal to `ail_v1`. This proves the ARP graph's core *is*
   the validated V1.
2. **`ailishcheck` on the V1 core.** `ail_v1` is written to a temp file and the
   `ailishcheck` binary parses it and runs the §3 register-monad guardrail
   (exit 0 = valid). Every V1 core in the dataset is proven by this binary.

The harness locates `ailishcheck` at `../ailish/target/debug/ailishcheck`
relative to this directory (it also probes ancestor checkouts that share the
`tools/ailish/` tree, and honours an `AILISHCHECK_BIN` override). If the binary
is genuinely absent it builds it with `cargo build --bin ailishcheck --locked`.
Note the project rule against building on the developer machine — prefer a
prebuilt binary or set `AILISHCHECK_BIN` to one.

### The AI-lish V1 guardrail rules each `ail_v1` core respects

A V1 core only validates if every frame obeys its register monad (RFC §3):

- `R:think` / `R:review` — evaluations (`combine`/`join`/`intersect`/`depend`)
  and relations only; no side-effecting verbs.
- `R:plan` — only `→ target(...)` schedule and/or `depend(...)`; no direct
  side-effecting verb; no gates.
- `R:tool` — actions (any verb), each bound to `%N`.
- `R:risk` — MUST emit a `gate(*:fail)` **or** a `block(...)` mitigation. To
  model "risk handled, then proceeded", these records use `block(...)` so no
  live fail-gate is left to freeze the later commit.
- `R:artifact` — MUST contain `gate(no_cjk:pass)` or `gate(english:pass)`.
- `R:commit` — verbs `merge`/`commit`/`open` only; MUST be preceded (document
  order) by `gate(ci:pass)`; MUST NOT sit behind a live `gate(*:fail)`.
- `R:bench` — `test`/`build` actions with metrics in a `; key=value`
  annotation, plus a gate.

## Keep generating

`generate.py gen` is a template-based emitter. It turns a
`(problem, state, solution, frames-spec)` Python dict into a record: it renders
`ail_v1` from the frames, derives `arp` by inserting STRIDE/T/BRANCH lines and
appending valence tokens, builds the `read` gloss, **validates the V1 core via
`ailishcheck`**, and appends to the JSONL only if valid (and only if the id is
not already present — so it is idempotent).

```bash
python3 generate.py gen
```

To add more rows, append spec dicts to the `SPECS` list in `generate.py` (the
documented extension point) and re-run `gen`. A spec describes the V1 core as a
list of frame dicts plus the ARP annotations (`stride`, `tensions`, `branches`,
and per-line `valence`); the emitter guarantees `strip_arp(arp) == ail_v1`
before it even calls `ailishcheck`, so a malformed spec fails loudly rather than
writing a bad row.

## Normalize-then-validate (V0-era inputs)

AI-lish V0 was an *expressive log sketch* and used tokens V1 rejects: the math
operator `⊕`, fuzzy `≈`, empty-set `∅`, and brace set literals `{…}`. Before
such a sample can become a dataset row it must be **normalized into V1 first**,
then validated:

- `⊕` → `combine(...)` (named pure func; V1 removed math symbols because LLMs
  hallucinate math context around `⊕`).
- set literals `{a, b}` → backtick symbols and `intersect(...)` / `join(...)`.
- drop `≈` / `∅` and other V0-only tokens.

Only after normalization does `ailishcheck` accept the graph. Record
`arp-008-normalize-then-validate` captures exactly this discipline.
