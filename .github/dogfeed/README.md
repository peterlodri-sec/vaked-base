# dogfeed staging — outside-model prompt audit

`outside-model.jsonl` is the staging file for the **dogfeed** CI auto-post
(`.github/workflows/dogfeed.yml`). It carries the panel sink's per-run JSONL records
(model · prompt_sha · first_line · completion_tokens · cost — **no full prompt/response, no
key**) for the oracle's non-hosted (OpenRouter) calls. On push, the workflow posts a summary
comment to the rolling **"oracle: outside-model prompt dogfeed"** issue via the built-in
`GITHUB_TOKEN` — the gh token never leaves the Actions runner (nothing on dev-cx53).

## Protocol (matches social-post)
1. On dev-cx53, run a team with the sink pointed at this file (truncate per run):
   ```
   : > .github/dogfeed/outside-model.jsonl
   ORACLE_DOGFEED_LOG=.github/dogfeed/outside-model.jsonl task -d tools/oracle team
   ```
2. `git add .github/dogfeed/outside-model.jsonl && git commit && git push` → the workflow fires
   and appends one comment to the rolling issue.
3. After CI confirms, **clear the file** in a follow-up commit (`: > …jsonl`) so a later push
   does not re-post. An empty file is a no-op.

Direct posting (no CI) still works from anywhere `gh` is authed:
`task -d tools/oracle dogfeed` (or `DRY=1 … dogfeed` to preview).
