# vaked-provost — product-owner / coordination agent

`vaked-provost` is the Vaked fleet's **product owner**: a doc-grounded, advisory
agent that keeps the *project graph* coherent — epics, the RFC process, issues,
milestones, and the links between them. It is a peer of
[`label-tagger`](../label-tagger/) (same adk-rust + OpenRouter stack, same
JSON-to-stdout / shell-applies-mutations split) but operates one level up: where
label-tagger triages an individual PR or issue, provost **reconciles the whole
repository's structure** on a schedule.

It never blocks CI: any failure logs and exits 0 after printing a safe no-op.

## What it does

On each run it reads the **live** docs and current GitHub state, then proposes a
coordination plan:

- **Epics** — derives epics from `GOALS.md` phases + major design specs, and
  links child issues to their epic via GitHub **native sub-issues**. (The "1.0
  epic" is issue #17; specs say e.g. *"Track B of the 1.0 epic (#17), issue #18"*
  — provost links #18 under #17.)
- **RFC process** — keeps the RFC index (in `docs/protocol/README.md`) honest:
  one row per `protocol/rfcs/NNNN-*.md` with its front-matter Status; flags any
  protocol design spec that has no RFC; proposes new RFC stubs when warranted.
- **Issues & milestones** — backfills missing `area/*` / `phase/*` / `type/epic`
  labels, and assigns an **existing** milestone to the right epic/issue. It does
  **not** create milestones (that is label-tagger's `milestone-sync`) — it notes
  missing ones for you instead.
- **Cross-links** — surfaces the single coordination view tying issues ↔ epics ↔
  RFCs ↔ specs ↔ milestones together.

## The safety boundary

Provost is **advisory + safe-sync**. The binary is read-only; the workflow shell
applies mutations, split into two buckets:

| Channel | What | How |
|---------|------|-----|
| **Auto-applied** (reversible GitHub *metadata*) | label add/remove, sub-issue parent↔child links, assigning an existing milestone | workflow shell + `gh`, gated on `dry_run=false` |
| **Coordination issue** `[provost] Coordination backlog` (marker `<!-- vaked-provost-coordination -->`, edited in place each run) | proposed new epics/issues + the proposed RFC index + missing-milestone notes | `gh issue create`/`edit --body-file` |
| **Coordination PR** (branch `provost/coordination`, marker-tracked) | new RFC **stub files** for a spec that lacks an RFC | `gh pr create`, only when `proposed_rfcs` is non-empty |

It never closes or deletes anything — it only adds and links.

## Modes

Set by `MODE` (workflow input or env):

| Mode | Focus |
|------|-------|
| `all` (default) | Full reconciliation: epics + RFC process + cross-links. |
| `rfc` | RFC index/status + tracking-issue reconciliation. |
| `epic` | Epic proposals + child→epic links. |
| `link` | Only the safe-sync subset (labels/links/milestones); no proposals. |

## Triggers

- **`schedule`** — daily `0 6 * * *`, `mode=all`, `dry_run=false` (applies
  safe-sync, refreshes the coordination issue).
- **`workflow_dispatch`** — choose `mode` and `dry_run` (defaults to `true` so a
  manual run shows the plan in the job summary without mutating).

## Doc-grounding

Before deciding, the agent calls its `read_file` tool on `GOALS.md`,
`docs/context/TIMELINE.md`, `.github/labels.yml`, and `docs/protocol/README.md`,
and is fed a pre-scanned catalog of the RFC series (front-matter Status/Track),
the design specs/plans (with their `#NNN` issue references), and current GitHub
state (open issues, milestones, epics). Nothing is hard-coded — evolve the docs
and the behavior follows.

## Output contract

The binary prints one JSON object (`ProvostOutput`) to stdout:

```jsonc
{
  "label_ops":     [{ "issue": 18, "add": ["type/epic"], "remove": [] }],
  "link_ops":      [{ "parent_issue": 17, "child_issue": 18 }],
  "milestone_ops": [{ "issue": 17, "milestone_title": "Phase 2 — Runtime: stubs → real" }],
  "rfc_index_ops": [{ "rfc_file": "protocol/rfcs/0001-hcp.md", "title": "…", "status": "Draft" }],
  "proposed_epics":  [{ "title": "…", "body": "…", "labels": [], "milestone": null, "children": [] }],
  "proposed_issues": [{ "title": "…", "body": "…", "labels": [], "epic": 17 }],
  "proposed_rfcs":   [{ "number": "0008", "slug": "…", "title": "…", "track": "Protocol", "rationale": "…" }],
  "missing_milestones": [],
  "summary": "…full markdown body for the coordination issue…"
}
```

## Environment

| Var | Purpose |
|-----|---------|
| `OPENROUTER_API_KEY` / `PROVOST_API_KEY` | LLM access. **Absent ⇒ graceful degradation**: emits only the deterministic RFC-index plan; skips judgment-heavy proposals. |
| `PROVOST_MODEL` | Model id (default `deepseek/deepseek-v4-flash`). |
| `OPENROUTER_BASE_URL` | API base (default `https://openrouter.ai/api/v1`). |
| `MODE` | `all` \| `rfc` \| `epic` \| `link`. |
| `GITHUB_REPOSITORY` | `owner/repo`. |
| `GH_TOKEN` | Used by the binary for read-only `gh` state queries and by the shell for mutations. |
| `LANGFUSE_URL`, `LANGFUSE_API_KEY` | Optional OTLP tracing; degrades gracefully. |

## Build & prebuilt binary

[`provost-build.yml`](../../../.github/workflows/provost-build.yml) bakes
`vaked-provost-linux-x86_64` into the rolling `provost-bin` release; the run
workflow downloads it (fast path) and only compiles from source if the download
fails.

```bash
cargo test  --manifest-path vaked-agents/ci/provost/Cargo.toml
cargo build --release --manifest-path vaked-agents/ci/provost/Cargo.toml
```

## Deferred (follow-ups)

- **GitHub Projects v2** sync (`projects` mode) — needs a PAT with `project`
  scope as `PROJECTS_TOKEN`; the default Actions token can't manage Projects.
- **`--apply-proposals`** — a gated active path where provost creates the
  approved epics/issues directly instead of only proposing them.
- Wire the coordination summary into the `ralph` decision ledger.
