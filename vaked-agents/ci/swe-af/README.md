# vaked-swe-af

The **plan** and **code** nodes of the lowered `workflow swe_af` declared in
[`vaked/examples/agentfield-swe.vaked`](../../../vaked/examples/agentfield-swe.vaked)
(`on = "github.issue.labeled:agent"`). An adk-rust + OpenRouter agent, sibling to
`pr-review` / `label-tagger` / `provost`.

## What it is

`swe_af` is a typed agent DAG — `plan → code → review → publish` — over a `mesh`
whose nodes hold attenuated (POLA) capabilities. This binary runs the two
authoring nodes; the rest of the DAG is wired in
[`.github/workflows/swe-af.yml`](../../../.github/workflows/swe-af.yml):

| swe_af node | mesh role · caps | here |
|---|---|---|
| `plan` | planner · `fs.repo_ro, mem.recall` | `MODE=plan` → JSON plan |
| `code` | coder · `fs.repo_rw, process.spawn_sandboxed` | `MODE=code` → full-file writes |
| `review` | reviewer · `fs.repo_ro` | reuses the **pr-review** agent on the opened PR |
| `publish` | broker · `mcp.github_write` | the workflow shell's `gh pr create` |

## POLA boundary

The binary holds **no `GH_TOKEN`** and makes **no GitHub writes**. It reads the
issue (`gh issue view`) and repo files (read-only `read_file` / `list_dir` tools)
and prints one JSON object to stdout. The workflow shell applies every side
effect — writing files, committing to `swe-af/issue-<n>`, and (only at the broker
step) `gh pr create`. That mirrors the mesh: only `broker` holds `mcp.github_write`.

## Modes

```bash
# plan: read the issue + repo, emit { plan, target_files, summary }
MODE=plan ISSUE_NUMBER=123 OPENROUTER_API_KEY=… ./vaked-swe-af

# code: given the plan, emit { files:[{path,content}], commit_message, notes }
MODE=code ISSUE_NUMBER=123 PLAN_FILE=plan.md OPENROUTER_API_KEY=… ./vaked-swe-af
```

`code` emits **full file contents** (never diffs) — far more robust to apply than
LLM-generated patches. The shell writes each file verbatim, so partial content
would corrupt files; the prompt forbids it and the parser clamps size/path.

## Env vars

| var | default | meaning |
|---|---|---|
| `OPENROUTER_API_KEY` \| `SWE_AF_API_KEY` | — | required; absent ⇒ graceful no-op |
| `SWE_AF_MODEL` | `deepseek/deepseek-v4-flash` | model for both modes |
| `SWE_AF_CODE_MODEL` | = `SWE_AF_MODEL` | stronger coder model (recommended) |
| `MODE` | `plan` | `plan` \| `code` |
| `ISSUE_NUMBER` | — | the target issue |
| `PLAN_FILE` | — | code mode: path to the plan markdown |
| `SWE_AF_MAX_FILES` | `20` | code mode cap |
| `LANGFUSE_URL`, `LANGFUSE_API_KEY` | — | optional tracing |
| `DRY_RUN` | `0` | print JSON without calling the model |

## Build / test

```bash
cargo test  --manifest-path vaked-agents/ci/swe-af/Cargo.toml
cargo build --release --manifest-path vaked-agents/ci/swe-af/Cargo.toml
```

The rolling prebuilt binary (`swe-af-bin` release) is produced by
[`.github/workflows/swe-af-build.yml`](../../../.github/workflows/swe-af-build.yml);
`swe-af.yml` downloads it (fast path) or compiles from source (fallback).

> Advisory + bounded. Never auto-merges. Output is a normal PR for human +
> pr-review review. See `docs/superpowers/specs/2026-06-13-swe-af-gha-runner-design.md`.
