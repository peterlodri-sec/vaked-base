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
5. **Broadcasts** the train every run (see below).

## Broadcast (always-on)

Every tick yardmaster announces as **`yardmaster:<repo>`** to **both** channels
([`report.py`](report.py)):

- **Mastodon** — a short emoji caption **plus an infographic picture**: a
  deterministic SVG of the train (a locomotive + one colour-coded car per PR on a
  track) rasterized to PNG, then **compressed** (pngquant, ~⅓ size),
  **metadata/EXIF-tagged** (exiftool: title, description, artist, copyright,
  software, datetime, source), and **Ed25519-signed**. The image is
  *data-accurate*, not LLM-drawn; any missing tool degrades that stage only.
- **Telegram** — the full emoji status report (one line per car + tally).

**Provenance + signature.** `finalize_image` builds a manifest
`{repo, commit, generated_at, image_sha256, sig, pubkey}`, signs it with
`YARDMASTER_SIGNING_KEY` (an Ed25519 PEM in the `ci` Environment) via openssl,
embeds it in the image (`UserComment` + a PNG `Comment` chunk), **and writes it to
the `eventd` ledger** (`signed_image` event) as the durable copy. Verify: strip
`UserComment`, `sha256` → `image_sha256`, then openssl-verify the signature over
the unsigned manifest with the embedded pubkey. Without a key it degrades to a
hash-only provenance manifest (still ledgered). Generate a key:
`openssl genpkey -algorithm ed25519` → store the PEM as `YARDMASTER_SIGNING_KEY`.

Best-effort + secret-guarded (a missing key is a clean no-op; a transport error
never fails the run). Credentials live in the `ci` Environment: `MASTODON_BASE_URL`
/ `MASTODON_ACCESS_TOKEN` / `MASTODON_VISIBILITY`, `TELEGRAM_TOKEN` / `TELEGRAM_TO`,
`YARDMASTER_SIGNING_KEY`. `YARDMASTER_ANNOUNCE=0` silences it.

## Stance (active, opt-in)

- **Graduated to act.** In CI the train runs `tick --enable` — it performs one
  real action per run (merge / update-branch / label). `plan` is the local
  dry-run; `YARDMASTER_ENABLE_MERGE=1` enables acting outside `--enable`.
- **Opt-in only.** Acts on a PR only with the `train:auto` label or a fleet-author
  allowlist (`FLEET_AUTHORS`) — never an arbitrary PR. Enrol a PR by labelling it
  `train:auto`.
- **Conflicts are a human's call.** A content merge needs judgment (see the
  research-integrity union that resolved #112's paper conflict); the train
  *surfaces* `dirty` PRs immediately, it does not resolve them.
- **Stacked-safe.** Holds a PR stacked on an unmerged base; refuses to merge an
  orphaned stacked PR into a stale (non-default) base.
- **One action per tick** — single-writer (workflow `concurrency`), auditable.
- **Control.** `state/control.json` (the `ralphcore` shape): `{"paused": true}`
  halts the train, `{"step": true}` runs one action while paused.

## Run

```bash
# dry-run: print the planned merge train for the current open PRs (no writes)
GITHUB_TOKEN=… python3 tools/yardmaster/yardmaster.py plan --repo peterlodri-sec/vaked-base

# one action + broadcast (acts on opt-in PRs; dry-run unless --enable)
python3 tools/yardmaster/yardmaster.py tick --enable --repo peterlodri-sec/vaked-base

# verify the ledger chain
python3 tools/yardmaster/yardmaster.py verify
```

In CI it runs from `.github/workflows/merge-train.yml` on **trusted events only**
(hourly `schedule` + `workflow_dispatch` — *not* `pull_request`, since the active
job holds write perms + secrets and must never execute PR-supplied code),
`environment: ci`, `concurrency: merge-train`, `contents`/`pull-requests: write` +
`checks: read`, installs `librsvg2-bin` / `pngquant` / `exiftool` for the
infographic, and runs `tick --enable`.

## Reuse (no new machinery)

- **Ledger:** `eventd.EventLog` (`eventd/`) — single-writer, fsync, boot-verify.
- **Control + ratify-rate:** `tools/ralph/ralphcore.py` (`Control`, `parse_control`, `ratify_rate`).
- **Agent shape + workflow conventions:** `tools/ralph/`, `.github/workflows/ralph-tracks.yml`.

Tests: [`tests/spec/test_yardmaster.py`](../../tests/spec/test_yardmaster.py)
(topo-sort, decision-table totality, stacked-hold planning, ledger tamper) —
registered in `tests/spec/run_all.py`.
