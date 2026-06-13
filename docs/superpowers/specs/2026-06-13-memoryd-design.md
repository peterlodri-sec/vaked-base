# memoryd — runtime memory plane + CDN-backed recall (design)

## Status

Design (2026-06-13). Track of the 1.0 epic ([#17](https://github.com/peterlodri-sec/vaked-base/issues/17)),
issue [#24](https://github.com/peterlodri-sec/vaked-base/issues/24). The runtime
home for the `memory` kind ([0014](../../language/0014-memory-primitive.md), grammar
+ lowering landed). Convention: daemon = design → plan → impl; this is the design.
Builds directly on **eventd** ([design](./2026-06-12-eventd-design.md), #18) — memory
entries are eventd events; memory state is the fold. The proving ground is
**MemPalace** (the async transcript miner used on this repo daily; CLAUDE.md
patch-doctor), generalized from external tooling to a runtime daemon.

## Purpose

One memory plane per runtime that turns the four-quadrant `memory` primitive into a
running daemon:

1. **mine** `source` streams into typed entries (the write path),
2. **append** entries to `eventd` and keep the recall view as the **fold** over the
   log (durable, replayable, rewind-for-free),
3. **serve recall** — capability-bound queries over the folded state (the read path),
4. **publish** the recall view to the edge CDN so recall is global and cheap.

## The one read plane (memory ⊥ index)

`memory`, `index`, and `catalog` are three corners of one space, and they **share a
read substrate** — a CrabCC-built catalog (sqlite + embedding shard):

| | pinned / reproducible | mined / runtime |
|---|---|---|
| **build-time write** | `index` (sources + `trust.sha256`, CrabCC-chunked) | — |
| **runtime write** | `catalog` (materialized view of an index) | **`memory`** (eventd-folded, mined) |

`index.emit` and `memory.emit` both produce `[catalog.jsonl, catalog.sqlite]`
([0008](../../language/0008-parallel-fibers-indexes-surfaces.md),
[0014](../../language/0014-memory-primitive.md)). They differ only in the **write
path**: `index` is build-time + pinned (a Nix derivation), `memory` is
runtime-appended via eventd. **Therefore there is no separate `indexd`.** memoryd is
the *serving* plane for any catalog; `index`/`catalog` are read-only inputs to it,
materialized at build time. memoryd `memory` adds the `(mine, append, eventd)` write
path on top of the same read substrate. CrabCC is the engine on both ends.

## Pipeline: CrabCC build → CDN put → memoryd serves by hash

```
            build-time (CI / Nix)                 runtime (vakedos)              edge (cdn.crabcc.app)
index ──▶ CrabCC chunk/embed ──▶ catalog ──put──▶                         ──▶  by sha256 (immutable)
                                  (sqlite +                                      D1 / R2 / KV
                                   embed shard)                                   ▲
memory: source stream ──▶ memoryd.mine ──▶ eventd append ──▶ fold ──▶ catalog ──publish──┘  (latest + history)
                                                                       └──▶ local recall (host)
recall ◀── cf-second-brain Worker (edge) ── or ── memoryd (host, by hash)
```

- **`index` / static `catalog`** publish **content-addressed by `sha256`** — the hash
  in `index.trust { sha256 }` *is* the CDN key. Immutable, reproducible, fetch-by-hash.
- **`memory`** is mined and non-reproducible, so memoryd publishes **periodic folded
  snapshots**: a mutable `latest` pointer + content-addressed history. The eventd log
  stays the source of truth; the CDN carries the materialized fold.
- "memoryd serves by hash" locally; globally the **edge** serves by hash.

### Distribution tiers (CDN → GitHub fallback → local)

Distribution degrades gracefully, mirroring the fleet's prebuilt-release-then-build
convention ([`docs/agents/ci.md`](../../agents/ci.md)):

1. **Edge CDN** (`cdn.crabcc.app`) — primary: global, cheap, by hash.
2. **GitHub fallback** — when the CDN is unconfigured/unreachable, publish + fetch
   catalogs from GitHub: **GHCR** (an OCI registry — blobs are addressed by `sha256`
   **digest**, so content-addressing carries over with *zero glue* and matches
   `index.trust.sha256` exactly), or **Release assets / repository artifacts** named by
   hash. GHCR is the preferred fallback precisely because OCI digests already are the
   addressing model.
3. **Local** — build from source (CrabCC) / fold from the local eventd log. Always
   available; the floor of the chain.

The `cdn(...)` emit target therefore lowers to an ordered target list (CDN, then a
GitHub target), resolved at fetch time — the daemon tries each tier in order.

## Edge read plane — reuse + extend `cf-second-brain`

A "second brain" already runs on Cloudflare: the **`cf-second-brain` Worker** +
**`second-brain` KV** + **`second-brain-db` D1**. memoryd does **not** invent an edge
recall plane — it **feeds and extends** that one (`cdn.crabcc.app`, the `__cdn`
Nix-defined edge infra):

- **D1 (edge SQLite)** *is* the edge `catalog.sqlite` — small/hot catalogs and the
  structured recall side land here directly.
- **KV** carries `hash → shard` (and the `latest` pointer for mutable memory snapshots).
- **R2** carries large corpus blobs by `sha256` (catalogs too big for D1).
- The **`cf-second-brain` Worker is the edge recall API** — extended to serve the
  Vaked catalog/recall query surface and resolve by hash.

memoryd picks the publish target by **catalog size at lower-time**: small → D1, large
→ R2-by-hash + a D1/KV index. (Exact backend + addressing of `__cdn` is **Open Q1**.)

## Semantics (from 0014, made operational)

- **Mine (write path).** memoryd subscribes to the `source` stream(s) and applies the
  `mine` normalizer to distil raw events into entries of the `schema` type `T`. Lean:
  mining is **model-driven and brokered** — the distiller is a budgeted call through
  `mcp-brokerd` (not a deterministic transform), mirroring MemPalace. Mined entries
  are therefore **non-reproducible** and carry provenance (miner id, model, budget,
  source event ids). Batched/debounced like the proven async-hook miner.
- **State = fold.** Each mined entry is an eventd event
  ([format](./2026-06-12-eventd-design.md#entry-format-frozen--matches-ralphcore-today));
  recall state is the fold, partitioned by `scope` (`session`/`agent`/`runtime`).
  Rewind (Track D, #20) rewinds memory for free. The catalog is a **materialized cache
  of the fold**, updated incrementally on append and rebuildable from eventd on demand.
- **Recall (read path).** Mediated by the `mem` capability domain (POLA, 0011 §4):
  `none < recall < append < admin`. Recall is **hybrid** — sqlite for structured
  filters (`scope`, schema fields, time), embeddings for semantic recall; both are
  catalog emits. Lean (0014 open): **runtime API only**, no `recall` language form.
- **Retention.** `retention` (e.g. `90d`) via **tombstone events on append** (not
  fold-time filtering), so the cache stays cheap and rewind stays exact — decided with
  the eventd compaction question.

## Capability enforcement

memoryd is the enforcement point for `mem`:

- A mesh node holding `mem.recall` may query but not write.
- Mining fibers hold `mem.append`; only the control plane holds `mem.admin`.
- **Edge caveat:** a public CDN read makes `mem.recall` advisory off-host; a
  token-gated bucket/Worker route makes it enforceable. memoryd publishes per-`scope`
  partitions so a recall token maps to a partition. (Tied to Open Q1.)

## Lowering inputs (already landed)

`vakedc lower` already emits what memoryd consumes (0012 §3.4 `memory.store`):

- `gen/memory/<name>.json` — `source`, `mine`, `scope`, `retention`, recall `emit`
  targets, the per-runtime eventd log path.
- `gen/eventd.json` — the log contract (presence-gated on memory/workflow decls).

memoryd reads these as its config. **New lowering work:** a `cdn(...)` `ArtifactTarget`
(publish step + addressing) added to the 0012 emitter registry beside `catalog.sqlite`
/ `nix.derivation` — gated on Open Q1.

## Daemon shape (runtime)

- **Language:** Zig (roster: [`docs/runtime/README.md`](../../runtime/README.md):17),
  with a **Python reference/oracle first** — the established daemon pattern (#15;
  eventd ships its oracle at `/eventd`). memoryd's oracle would live at `/memoryd`:
  `mine` (stub/brokered distiller) → `eventd` append → fold → catalog emit → CDN put,
  plus a recall CLI, cross-checked in `tests/spec/test_memoryd.py`.
- **Writer discipline:** appends go through eventd's single-writer
  (`agent-supervisord` owns it); memoryd is an eventd writer for `mem.append`.
- **Reader:** folds the log read-only; serves recall; publishes snapshots.

## Phases

1. **Python reference/oracle** (`/memoryd`): config from `gen/memory/*.json`; mine
   (deterministic stub + a brokered-distiller seam); append to the eventd reference;
   fold → catalog (sqlite + jsonl); local recall (structured + a pluggable embedder).
   `tests/spec/test_memoryd.py` cross-verifies entries are valid eventd events and
   recall = fold.
2. **CDN publish + edge recall**: `cdn(...)` emit target; publish catalogs (by sha256)
   and memory snapshots (latest + history) to the edge; extend `cf-second-brain` to
   serve the recall API + resolve by hash. (Blocked on Open Q1.)
3. **Brokered mining**: real model-driven distiller via `mcp-brokerd` with budgets +
   provenance; MemPalace becomes *a* `memory` declaration rather than a special case.
4. **Zig daemon port** (Python as oracle), `mem` enforcement, rewind integration
   (Track D).

## Verification

- Oracle: mined entries verify as eventd chain entries (reuse `test_eventd`);
  recall determinism (same log → byte-identical folded catalog); retention tombstone
  drops an entry from recall but not from the chain; rewind to N reproduces the
  catalog at N.
- Edge: a published catalog fetched by `sha256` byte-matches the local emit; a
  `mem.recall` token reads only its `scope` partition.

## Open questions

1. **`__cdn` backend + addressing (blocking phase 2).** Is `cdn.crabcc.app` R2 / D1 /
   KV / Pages, and **content-addressed or path-mutable**? Content-addressed unifies
   `index.trust.sha256` with the CDN key at zero glue; path-based needs a hash→path
   manifest. Needs `__cdn` read into scope to pin. (No `cdn` R2 bucket observed in the
   account; `cf-second-brain` D1/KV present.)
2. **Mining determinism (final call).** Model-driven+brokered (this design's lean,
   non-reproducible + provenance) vs a deterministic normalizer (reproducible, weaker
   distillation). Decides whether memoryd needs `mcp-brokerd` + budgets.
3. **Recall query surface.** Runtime API only (0014's lean) vs a `recall` expression
   form entering the language.
4. **Cross-runtime / mesh-shared palaces** (0014 open) — published snapshots are the
   carrier; interacts with the SHM arena graft (#16).
