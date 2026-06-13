# yardmaster — merge-train conductor

> The rail-yard role that sequences cars into a train and dispatches them.

The Vaked repo is built by a **fan-out fleet** of agents (multiple Claude
sessions + CI/cron agents), each opening its own branch/PR — sometimes
**stacked** (PR B based on PR A's branch, e.g. #112 on #103). There's a runtime
supervisor (`agent-supervisord`) and a *decision* loop (`ralph`), but nothing
sequenced the **integration** of those PRs. yardmaster is that missing piece.

Each tick it:

1. **Observes** the open PRs (mergeable state + CI) via the GitHub REST API.
2. **Builds the dependency DAG** — an edge to every open PR whose head branch is
   this PR's base (stacked dependency) — and **topologically orders** the train.
3. **Acts on the first actionable car** by `mergeable_state`:

   | state | action |
   |-------|--------|
   | `clean` + CI green + opt-in | **merge** (squash) |
   | `behind` | **update-branch** (base moved) |
   | `unstable`/`blocked` + CI pending | **wait** |
   | `dirty` | **flag `train:needs-human`** — never auto-resolve |
   | stacked on an unmerged base | **hold** until the base merges |

4. **Records** the action on the `eventd` hash-chained ledger (`state/log.jsonl`).
5. **Notifies** (Telegram) on merge / blocked-conflict / failure.

## Stance (advisory-first)

- **Dry-run by default.** `plan` prints the train; `tick` plans + ledgers but
  **merges nothing** unless `--enable` / `YARDMASTER_ENABLE_MERGE=1`.
- **Opt-in only.** Auto-merges a PR only with the `train:auto` label or a
  fleet-author allowlist — never an arbitrary human PR.
- **Conflicts are a human's call.** A content merge needs judgment (see the
  research-integrity union that resolved #112's paper conflict); the train
  *surfaces* `dirty` PRs immediately, it does not resolve them.
- **One action per tick** — single-writer, auditable, rate-limit-friendly.
- **Control.** `state/control.json` (the `ralphcore` shape): `{"paused": true}`
  halts the train, `{"step": true}` runs one action while paused.

## Run

```bash
# dry-run: print the planned merge train for the current open PRs
GITHUB_TOKEN=… python3 tools/yardmaster/yardmaster.py plan --repo peterlodri-sec/vaked-base

# one action (dry-run unless --enable / YARDMASTER_ENABLE_MERGE=1)
python3 tools/yardmaster/yardmaster.py tick --repo peterlodri-sec/vaked-base

# verify the ledger chain
python3 tools/yardmaster/yardmaster.py verify
```

In CI it runs from `.github/workflows/merge-train.yml` (schedule + dispatch +
`pull_request`), `environment: ci`, guarded on `GITHUB_TOKEN`, Telegram on
failure.

## Reuse (no new machinery)

- **Ledger:** `eventd.EventLog` (`eventd/`) — single-writer, fsync, boot-verify.
- **Control + ratify-rate:** `tools/ralph/ralphcore.py` (`Control`, `parse_control`, `ratify_rate`).
- **Agent shape + workflow conventions:** `tools/ralph/`, `.github/workflows/ralph-tracks.yml`.

Tests: [`tests/spec/test_yardmaster.py`](../../tests/spec/test_yardmaster.py)
(topo-sort, decision-table totality, stacked-hold planning, ledger tamper) —
registered in `tests/spec/run_all.py`.
