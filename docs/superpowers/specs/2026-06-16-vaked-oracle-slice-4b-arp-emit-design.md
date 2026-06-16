# vaked-oracle slice 4b · thread 3 — ARP-emission (design)

**Date:** 2026-06-16
**Status:** approved (brainstorm) — ready for plan
**Base:** `origin/main` @ `a7a6207`

## One-liner

The oracle emits its findings as typed **`arp_event`** Vaked declarations — its RE execution
recorded in the ARP representation layer, **verifiable via `vakedc check`** (`tools/arp/
verify_log.py`). Closes the dogfood loop (oracle evidence → Vaked/ARP) one-way.

## Lane safety (critical)

There are **two** ARP things in this repo. Thread 3 uses **only** the first:
1. **`arp_event`** — a stable Vaked builtin schema (`vaked/schema/builtins.vaked`) + auto-hook
   (`.claude/hooks/arp_log.py`) + verifier (`tools/arp/verify_log.py`), all on `origin/main`.
   We **consume this schema read-only** (emit conforming blocks). ✅ in-lane.
2. **execution ARP IR** — the other dev's *unpushed* lanes (`exec-semantics`, `gocc`,
   `feat+arp-dogfeed-hook`). **NOT TOUCHED** by this thread.

The oracle is a one-way *producer* of `arp_event` declarations; it never reads, writes, or
depends on the execution ARP IR.

## The `arp_event` schema (read-only target)

```
schema arp_event {
  field ts      : String { required }
  field command : String { required nonempty }
  field inputs  : List<String> { optional }
  field outputs : List<String> { optional }
  field status  : String { required }
  field notes   : String { optional }
}
```
Block form (verified during brainstorm to pass `vakedc check`): a fenced ```vaked block,
instance name an **IDENT slug** (not a string), omit `inputs`/`outputs` when empty.

## Decisions (locked in brainstorm)

- **Granularity: per-function** — one `arp_event` per reverse-engineered function.
- **Dedicated output** `docs/oracle/arp-trace.md` (NOT the shared `docs/arp-log.md` — no
  collision with the auto-hook).
- **Standalone CLI** `oracle arp-emit` (deliberate, decoupled from the run — like `dogfeed`).
- Pure stdlib; tests in the module-level `test_*` convention; a `vakedc check` dogfood test.

## Mapping: finding → per-function `arp_event`

For each entry in `finding["functions"]` (shape: `{name, addr, pseudo_c_sha, refined_c,
fidelity:{score,method}, dynamic}`), with `tgt = finding["target"]["path"]`:
- **slug** (IDENT): `oracle_<sanitized name>_<sha12(refined_c)>` where sanitized = `re.sub(r"\W","_",name)` (handles Zig `cache.sha256Hex` → `cache_sha256Hex`); `sha12` = first 12 hex of `sha256(refined_c or "")`. The `oracle_` prefix guarantees a letter-leading IDENT.
- **command**: `"oracle RE <name>"`.
- **inputs**: `[tgt, name]`.
- **outputs**: `["refined_sha:<sha12|none>", "fidelity:<score|none>"]`.
- **status**: `_status(score)` — `score is None` → `"no-ground-truth"`; `score < 0.4` →
  `"low-fidelity"`; else `"ok"`.
- **ts**: injected (CLI `--ts`, default current time) — `arp_event.ts` is required; the finding
  carries no timestamp, so it is supplied at emit time (kept injectable for deterministic tests).

## Components / files

### `tools/oracle/arp_emit.py` (NEW · pure stdlib)
- `_slug(name, refined_c)`, `_status(score)`, `_vstr(s)`/`_vlist(xs)` (Vaked string/list literals,
  backslash+quote escaped).
- `finding_to_events(finding)` → `list[dict]` (one per function; the mapping above).
- `render_arp_block(ev, *, ts)` → the fenced ```vaked `arp_event <slug> {...}` block
  (ts/command always; inputs/outputs omitted when empty; status always; slug **unquoted**).
- `emit(finding, *, path, ts)` → append a `## <ts> — <command>` heading + the block per event;
  write a one-time markdown header (title + the `verify_log.py` reproduce line) when the file is new.
  Returns the event count.

### `tools/oracle/oracle.py` (MODIFY)
`arp-emit` subparser: `--finding <finding.json>` (required), `--out <md>` (default
`docs/oracle/arp-trace.md`), `--ts <str>` (default a current-time stamp). `cmd_arp_emit`:
`finding = json.load(open(ns.finding))`; `n = arp_emit.emit(finding, path=ns.out, ts=ns.ts or <now>)`;
print `arp-emit: wrote <n> arp_event(s) to <out>`. Dispatch in `main`.

### `tools/oracle/test_oracle.py` (MODIFY — module-level `test_*`, plain assert)
- `finding_to_events`: a 2-function finding (one with fidelity 0.58 → `ok`; one with score
  `None` → `no-ground-truth`) maps to 2 events with the right command/inputs/outputs/status.
- `_slug`: IDENT-safe — `cache.sha256Hex` → `oracle_cache_sha256Hex_<sha12>` (no `.`; matches
  `^[A-Za-z_]\w*$`).
- `render_arp_block`: starts with ```` ```vaked ````, `arp_event <slug> {` (slug unquoted),
  contains `ts`/`command`/`status`; omits `inputs`/`outputs` lines when those are empty.
- `_status` thresholds (None / <0.4 / >=0.4).
- `emit`: appends blocks + writes the header once (second emit to the same file → no duplicate
  header).
- **`vakedc check` dogfood test:** `emit` a finding to a temp `.md`; extract the ```vaked blocks
  (reuse `tools/arp/verify_log.extract`); `subprocess.run([sys.executable,"-m","vakedc","check",tmp], cwd=<repo root>)` → returncode 0. (Mirrors `verify_log.py`; vakedc is in-repo, M3-safe.)

### `tools/oracle/Taskfile.yml` (MODIFY)
`arp:emit` (run `oracle arp-emit` on a finding JSON) + `arp:verify` (`python3 tools/arp/
verify_log.py docs/oracle/arp-trace.md`) targets.

### Docs
`docs/oracle/v0.md` — an "ARP-emission (slice 4b · thread 3)" section (the dogfood-loop close +
the lane boundary). `.DEV.TODO` — thread 3 done; slice-4b complete.

## Error handling
- Missing/empty `refined_c` → `refined_sha:none`, slug uses `sha12("")` (stable). Missing fidelity
  → `no-ground-truth`. `emit` creates the file + header if absent. The CLI surfaces a bad finding
  JSON as a non-zero exit (deliberate command).
- Slugs are sanitized to valid IDENTs; the `vakedc check` test is the backstop that every emitted
  block is well-formed.

## Out of scope (own cycles)
- Auto-emit from `oracle run`/`team` (kept a deliberate standalone command).
- Any interaction with the **execution ARP IR** (other dev's lane).
- A richer per-step (decompile/refine/fidelity) trace — per-function is the chosen granularity.

## Constraints
Pure stdlib; M3-safe (`vakedc check` is pure Python, no compile); read-only against the
`arp_event` builtin schema; **never touch the execution ARP IR / `exec-semantics`/`gocc` lanes**;
emit to a dedicated `docs/oracle/arp-trace.md`; Snyk OFF.
