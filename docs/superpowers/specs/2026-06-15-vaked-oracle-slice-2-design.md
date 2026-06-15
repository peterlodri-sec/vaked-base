# vaked-oracle slice 2 — double-dogfood wire (design)

**Date:** 2026-06-15
**Branch:** `feat/oracle-double-dogfood` (worktree `.worktrees/oracle-slice2`, off `origin/main`)
**Status:** approved design → implementation plan next

## Goal

Flip the `transition_xref` seam from always-`null` (slice 1) to a **verified
bidirectional link** between an oracle finding and a real vaked-aegis kernel WAL
transition. Agent-free, deterministic, replay-stable. One sentence: *oracle
reverse-engineers the LLM runtime; recording that RE finding is itself judged and
logged as an aegis kernel transition, and the two hash-chained ledgers cross-
reference each other.*

## Background — what exists (slice 1, on `origin/main`)

The seam is built and unit-tested but **never called in a production flow**:

- `tools/oracle/schema.py` — `build_finding(..., transition_xref=None)`; finding
  carries `transition_xref: str | None`, `observed_effects: {writes, deletes}`.
- `tools/oracle/bridge.py` — two functions, tested, **uncalled**:
  - `to_observed_effects(finding, *, files_written, files_deleted) -> {"writes": [...], "deletes": [...]}`
  - `attach_transition(finding, transition_hash) -> finding'` (deep-copy with `transition_xref` set)
- `tools/oracle/ledger.py` — `class Ledger`: `.append(payload) -> entry`, `.verify() -> bool` (hash-chained, eventd dialect).
- `tools/dogfood/kernel.py` — `judge(root, scope, intent, proposer, *, wal_path, blobs_dir, observed=None, record=True) -> verdict`. The production transition gate: PROPOSE → DETECT actual → CAPABILITY gate → DECLARED-vs-ACTUAL gate → OBSERVED gate → REPLAY gate; on accept appends to the eventd WAL and returns `verdict["hash"]`/`["seq"]`/`["payload"]`. `proposer(root, scope, intent) -> declared|None` mutates the tree in place.
- `tools/dogfood/wal.py` — `append_transition(log, payload)`, `EventLog` (re-export). WAL = the real `eventd` daemon.
- `eventd` — entry shape `{seq, prev, payload, hash}`, `hash = sha256(prev_hex || canonical_json(payload))`. `EventLog(path, *, writer=False, verify=True)` verifies the chain on open (raises `TamperError`).
- `tools/dogfood/capability.py` — `check(paths, scope) -> {"ok": bool, "violations": [...]}`, `in_scope(rel, scope) -> bool`.
- `docs/oracle/integration.md` §2 — documents the seam, states it is "null in slice 1".

## The hash cycle, resolved

The xref is the WAL entry's content hash. The WAL hashes the transition payload,
whose `postimages` include the finding artifact. So the artifact **cannot**
contain the xref (it would change the hash that defines the xref). Resolution:

- **WAL transition** records the finding **without** `transition_xref` (the post-image written into the scoped workspace).
- **Oracle ledger** records the finding **with** `transition_xref` = that WAL entry's hash.

Bidirectional, acyclic:
- ledger → WAL: `finding.transition_xref` is the WAL entry hash.
- WAL → ledger: the WAL transition's `actual_effects.writes` contains the finding path.

```
oracle ledger entry                         eventd WAL entry
  finding (target, fns, fidelity, …)          payload.kind = dogfood_transition
  transition_xref = <wal hash> ───────────►   hash = <wal hash>
                          ◄───────────────── actual_effects.writes ∋ <finding path>
  Ledger.verify()                             EventLog(verify=True) on open
  (independent chain)                         (independent chain)
```

## Architecture — the wire

Reuse `kernel.judge()` verbatim. The "proposer" materializes the finding artifact
into the capability-scoped oracle workspace; `judge` captures that write as a
transition, runs every gate, appends to the WAL, returns the verdict. Then attach
the WAL hash to the finding and append the linked finding to the oracle ledger.

### New module: `tools/oracle/dogfood_bridge.py`

Imports the dogfood kernel + eventd. Import plumbing: insert `<repo>/tools/dogfood`
on `sys.path` (kernel does bare `import capability`), and `<repo>` (eventd). Top-
level `import kernel` is safe — `kernel` only imports `proposer` (opencode) lazily
inside `_proposer_from_args`, never at module load.

```python
def ground_finding(*, finding: dict, finding_rel: str, root: str, scope: list[str],
                   wal_path: str, blobs_dir: str, oracle_ledger) -> dict:
    """Record `finding` as an aegis kernel transition and cross-link both chains.

    `finding_rel` is the workspace-relative path the finding artifact is written
    to (must be inside `scope`). Returns
    {"verdict", "transition_xref", "ledger_entry", "linked_finding"}.
    Raises RuntimeError if the kernel rejects the transition (e.g. out-of-scope).
    """
    # normalize the finding's OWN observed_effects to the artifact path — this is
    # the shared key verify_xref uses for the WAL→finding direction. Identical in
    # the hashed artifact and the linked ledger copy.
    finding = dict(finding)
    finding["observed_effects"] = bridge.to_observed_effects(finding, files_written=[finding_rel])

    def _proposer(root, scope, intent):
        dest = os.path.join(root, finding_rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(finding, f, sort_keys=True)   # finding WITHOUT xref
        return {"writes": [finding_rel], "deletes": []}      # declared effects

    observed = finding["observed_effects"]                   # == {"writes": [finding_rel], "deletes": []}
    tgt = finding.get("target", {})
    intent = f"RE evidence: {tgt.get('binary', '?')} fns={len(finding.get('functions', []))}"
    verdict = kernel.judge(root, scope, intent, _proposer,
                           wal_path=wal_path, blobs_dir=blobs_dir, observed=observed)
    if not verdict["accepted"]:
        raise RuntimeError(f"kernel rejected grounding: {verdict['reasons']}")
    wal_hash = verdict["hash"]
    linked = bridge.attach_transition(finding, wal_hash)     # finding WITH xref
    led_entry = oracle_ledger.append(linked)
    return {"verdict": verdict, "transition_xref": wal_hash,
            "ledger_entry": led_entry, "linked_finding": linked}


def verify_xref(*, finding: dict, wal_path: str, oracle_ledger) -> bool:
    """Prove the bidirectional link + both chains. Raises ValueError on any break.

    1. oracle_ledger.verify() — oracle chain intact (else raise).
    2. open EventLog(wal_path) — verifies the WAL chain on open (TamperError else).
    3. locate the WAL entry whose hash == finding['transition_xref'] (else raise).
    4. set(finding['observed_effects']['writes']) must be a non-empty subset of
       that entry's payload.actual_effects.writes (else raise — a forged xref
       pointing at a transition that did not record this finding).
    """
```

Step 4 uses the finding's own `observed_effects.writes` (normalized to the
artifact path by `ground_finding`) as the shared key against the located
transition's `actual_effects.writes`. `verify_xref` needs only the linked finding
+ the WAL path + the ledger — no `finding_rel` argument.

### CLI: `tools/oracle/oracle.py`

Add two argparse subcommands beside `run` (`sub.add_parser(...)`, dispatch in
`main` via `elif ns.cmd == ...`):

- `ground --finding <path> --root <dir> --scope <prefix>... --wal-path <p> --blobs <p>`
  Loads the finding JSON, computes `finding_rel` relative to `root`, calls
  `ground_finding`, prints `transition_xref` + accepted/seq.
- `verify-xref --finding <path> --wal-path <p> --ledger <p>`
  Loads the (linked) finding + opens the ledger, calls `verify_xref`, prints OK/FAIL.

### Reused unchanged

`oracle/bridge.py`, `oracle/ledger.py`, `oracle/schema.py`, `dogfood/kernel.py`,
`dogfood/wal.py`, `dogfood/transition.py`, `dogfood/capability.py`, `eventd/`.
**No edits to `tools/ralph/` or `eventd/`** (read/call only).

## Testing — `tools/oracle/test_oracle.py` (extend; pure-Python, M3-safe)

All run via `python3 tools/oracle/test_oracle.py` (stdlib, no compile). Fixtures
use a `tempfile.TemporaryDirectory()` non-git workspace + a tmp WAL/ledger.

1. `test_ground_attaches_real_wal_hash` — build a fixture finding; `ground_finding`
   into a tmp scope → `result["transition_xref"]` is a 64-hex string (not None);
   the linked finding's `transition_xref` == that hash; the WAL has exactly one
   `dogfood_transition` entry; its `actual_effects.writes` == `[finding_rel]`.
2. `test_verify_xref_resolves_bidirectionally` — after `ground_finding`,
   `verify_xref(finding=linked, ...)` returns True.
3. `test_verify_xref_rejects_missing_wal_entry` — linked finding whose
   `transition_xref` = `"00"*32` (absent) → `verify_xref` raises `ValueError`.
4. `test_verify_xref_rejects_finding_not_in_writes` — point `transition_xref` at a
   real WAL entry recorded for a *different* path → raises `ValueError`.
5. `test_ground_respects_capability_scope` — `finding_rel` outside `scope` → kernel
   rejects (`capability` gate) → `ground_finding` raises `RuntimeError`; the WAL
   gains no entry and the workspace is rolled back (no stray file).
6. `test_chains_verify_independently` — tamper the oracle ledger file → `verify_xref`
   raises at step 1 while the WAL still opens clean; tamper the WAL file →
   `EventLog` open raises `TamperError` while `oracle_ledger.verify()` is True.

Target: existing 33 stay green + 6 new = 39 passing.

## Docs

- `docs/oracle/integration.md` §2 — replace "null in slice 1 … not called in
  production flows yet" with the wired flow: the `ground`/`verify-xref` commands,
  the acyclic hash resolution, and the bidirectional integrity check.
- `docs/oracle/v0.md` — the example finding's `"transition_xref": null` annotated
  as "null until grounded; slice 2 `ground` populates it"; add a one-line
  double-dogfood acceptance entry once the on-box run lands.

## On-box acceptance (final task — dev-cx53, box-gated)

Mirrors slice 1 task 17. On dev-cx53 (revdev cell): a real `task -d tools/oracle run`
produces a finding → `oracle ground` it into `~revdev/oracle/findings` (scope) with
the WAL under `~revdev/oracle/.aegis-wal` → `oracle verify-xref` passes → record the
`transition_xref` + WAL seq in `docs/oracle/v0.md` and `docs/recon/02-dynamic-evidence.md`.
Uses the golden SSH patterns (`docs/recon/golden-ssh-patterns.md`). No compile.

## Out of scope (→ slice 3, in `.DEV.TODO`)

The agentic proposer and finding-driven *code* patches (an LLM agent writing a real
source edit grounded in the finding). Slice 2 keeps the proposer a deterministic
artifact-materializer; slice 3's agent reuses this exact `ground_finding`/WAL plumbing.

## Constraints

Never compile on the M3 (the wire + all tests are pure-Python; only the on-box
acceptance touches dev-cx53). revdev unprivileged. Snyk OFF. `tools/ralph` + `eventd`
read/call-only. Don't touch the execution ARP IR or L2 eBPF-LSM.
