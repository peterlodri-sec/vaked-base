# Spec — Tightened vaked→ARP dogfeeding hook

**Date:** 2026-06-15
**Status:** approved (brainstorm), pending implementation plan

## Context

Vaked dogfeeds its own dev sessions by recording substantial shell operations as
typed `arp_event` Vaked declarations in `docs/arp-log.md`. The current mechanism is
an **advisory hookify nag rule** (`.claude/hookify.vaked-arp-log.local.md`,
PostToolUse `bash`) that asks the model to *manually* write each entry. It is
model-dependent and unreliable: the log has been empty since it was created
(`ad60b26`, 2026-06-14). Three further gaps: `arp_event` is not a validatable
Vaked construct, captured fields would be mechanical guesses, and the
"substantial" filter is prose only.

This change makes capture **deterministic, validatable (real Vaked), accurate, and
low-noise**, and ships a portable bootstrap block so other skills/workflows can
install the same hook.

### Key enabling fact

The vakedc **parser accepts any identifier as a `kind`** — the `KINDS` tuple
(`vakedc/parser.py:34-42`) is reference-only, not enforced at parse time. The
checker binds an instance to a schema purely by kind-name
(`vakedc/check.py:1172`, `registry.schemas.get(kind)`); a kind with no matching
schema simply passes. Therefore defining `schema arp_event {…}` in
`builtins.vaked` makes `arp_event "x" {…}` instances **both parse and
check-validate with zero grammar/parser change**.

## Components

### 1. `arp_event` schema — `vaked/schema/builtins.vaked`

Append:

```vaked
schema arp_event {
  field command : String { required nonempty }
  field inputs  : List<String> { optional }
  field outputs : List<String> { optional }
  field status  : String { required }
  field notes   : String { optional }
}
```

`status` is `String` ("ok" or "err: <msg>"). Field types (`String`, `List<String>`)
match existing builtins usage.

### 2. Deterministic capture hook — `.claude/hooks/arp_log.py`

PostToolUse, matcher `Bash`. Replaces the advisory rule. Reads stdin JSON.

- **Input fields:** `tool_input.command`; status derived best-effort from
  `tool_response` (exact field nailed during impl).
- **Noise filter:** skip trivial reads (`ls cat echo which pwd head tail`,
  `git status/log/diff`) and mirror existing `not_contains` excludes (`.vaked`,
  `vakedc`, `run_all.py`). Substantial = file-mutating / pipeline / build / test.
- **outputs (fidelity):** reuse the `_git_status_map` pattern
  (`tools/dogfood/kernel.py:63`). Hook runs *after* the command, so it persists a
  `$TMPDIR/arp-gitmap.json` stamp; delta of current map vs stamp = files this
  command touched → `outputs`. Rewrite stamp each run.
- **inputs:** file-path-looking tokens extracted from the command string.
- **emit:** `## YYYY-MM-DD HH:MM — <label>` header + a ` ```vaked ` fenced
  `arp_event` block; append to `docs/arp-log.md`. Label derived from command.
- **self-validate:** validate the generated block (extract → temp `.vaked` →
  `vakedc check`) before append; reject malformed.

### 3. Register + retire — `.claude/settings.json`

Add PostToolUse `Bash` hook: `python3 $CLAUDE_PROJECT_DIR/.claude/hooks/arp_log.py`.
Delete `.claude/hookify.vaked-arp-log.local.md` (superseded; gitignored per-machine,
so no commit needed).

### 4. Dogfood verifier — `tools/arp/verify_log.py`

vakedc reads `.vaked` only, not `.md` fences. Extract all ` ```vaked ` blocks from
`docs/arp-log.md` → temp `.vaked` → `python3 -m vakedc check` (exit 0 = log is
provably valid Vaked). This is the dogfooding: Vaked checks its own session log.

### 5. Tests — `tools/arp/test_arp_log.py`

- substantial cmd → appends `arp_event` with correct fields.
- trivial cmd → no append (noise control).
- generated block → `vakedc check` exit 0 (validity).
- pure-python, tiny fixtures, no build (dev-machine constraint).

### 6. Portable bootstrap — `docs/arp-log.meta-hook.md`

Self-contained copy-pasteable `[<>]` directive block another skill/workflow can read
to **create the schema + hook + register + verify** from scratch. Concise; embeds
the schema, the hook contract (stdin fields, filter, emit format), the settings.json
entry, and the verify command. Goal: any agent reading it can reproduce the whole
pipeline without this spec.

## Verification

1. `python3 -m vakedc check` on `vaked/schema/builtins.vaked` — exit 0 (schema valid).
2. Run `python3 tools/arp/test_arp_log.py` (or pytest) — all green.
3. Feed a sample substantial-command stdin JSON to `.claude/hooks/arp_log.py`;
   confirm `docs/arp-log.md` gets a valid fenced `arp_event` entry; feed `ls`,
   confirm no append.
4. `python3 tools/arp/verify_log.py` on a populated log — exit 0.
5. Hand `docs/arp-log.meta-hook.md` to a fresh agent (or re-read it) and confirm the
   steps reproduce the pipeline standalone.

## Out of scope

- Adding `arp_event` to the grammar `kind` enum (unnecessary — parser is open).
- Making vakedc natively parse markdown fences (verifier extracts instead).
- Retroactively logging past sessions.
