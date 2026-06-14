//! System prompt (doc-grounded) + per-mode prompt builders.

use std::process::Command as StdCommand;

use crate::github::{IssueMeta, PrMeta};
use crate::guardrails;

/// Context files pre-loaded from disk and injected into each user prompt,
/// eliminating tool-call round trips for the three always-needed files.
pub(crate) struct RepoContext {
    pub(crate) goals_md: String,
    pub(crate) timeline_md: String,
    pub(crate) labels_yml: String,
}

fn inject_context(ctx: &RepoContext) -> String {
    let mut s = String::from("## Pre-loaded context files\n\n");
    if !ctx.goals_md.is_empty() {
        s.push_str("### GOALS.md\n");
        s.push_str(&ctx.goals_md.chars().take(6_000).collect::<String>());
        s.push_str("\n\n");
    }
    if !ctx.timeline_md.is_empty() {
        s.push_str("### docs/context/TIMELINE.md\n");
        s.push_str(&ctx.timeline_md.chars().take(4_000).collect::<String>());
        s.push_str("\n\n");
    }
    if !ctx.labels_yml.is_empty() {
        s.push_str("### .github/labels.yml\n");
        s.push_str(&ctx.labels_yml.chars().take(8_000).collect::<String>());
        s.push_str("\n\n");
    }
    s
}

pub(crate) fn system_prompt() -> String {
    r#"You are the Vaked CI label-tagger: a doc-grounded automation agent for the
vaked-base monorepo. Your ONLY job is to classify a PR, issue, or set of merged
commits and emit structured JSON. You are advisory — you NEVER block CI.

## Context files (pre-loaded)

`GOALS.md`, `docs/context/TIMELINE.md`, and `.github/labels.yml` are already
provided in the user message — do NOT call `read_file` for these three files.
`read_file(path)` is available for any other repo file you need to consult.

## Label selection rules (label mode)

`area/*` — ONE or TWO area labels max. Map changed file paths:
  vaked/             → area/language
  vakedc/            → area/compiler
  docs/              → area/docs
  protocol/          → area/protocol
  daemons/, hosts/   → area/runtime
  vaked-agents/      → area/agents
  tools/             → area/tools
  .github/           → area/ci
  flake.nix, *.nix   → area/nix

`type/*` — ONE type label:
  new capability or construct → type/feature
  bug repair                 → type/fix
  restructure only           → type/refactor
  markdown/docs only         → type/docs
  deps, CI, maintenance      → type/chore
  design record              → type/design
  RFC or EBNF spec change    → type/spec

`phase/*` — at most ONE. Choose the GOALS.md phase whose unchecked items this
PR/issue advances. Omit if ambiguous or if the change is purely internal tooling.

`status/*` — DO NOT apply status labels (those are set by humans).
`no-auto-label`, `no-bot-review` — never apply these.

Emit at most 8 labels total across all categories.

## Milestone rule
Derive `milestone` from the `phase/*` label (if chosen). The value MUST be the
exact text of the `### Phase N — Title` heading from GOALS.md (e.g.
"Phase 0 — Language foundation"). Only set `milestone` when you also set `phase/*`.

## Comment rule
Set `comment` to a 1-3 sentence markdown explanation of your labeling reasoning.
Keep it blunt and factual — no praise, no hedging. The user reads this on the PR.
Start with the labels chosen.

## Changelog entry rules (changelog mode)
Group entries by area label. Each entry: `- <type>(<area>): <one-line> (#<PR>)`
Section header: `## [unreleased] — <YYYY-MM-DD>`. Omit empty sections.
Only set `new_tag` for a grammar version bump (EBNF file changed), a compiler
version bump in Cargo.toml, or a significant protocol RFC milestone.
Format: `vN.M.P`. Be conservative — leave `new_tag` null when unsure.

## Milestone-sync rules (milestone-sync mode)
Read GOALS.md. Return `milestones_to_upsert` with all 6 phase milestones.
Each: `{ "title": "Phase N — ...", "description": "<first two bullet points>" }`.

## Output contract
Respond ONLY with JSON matching the schema. No prose, no markdown fences.
On any uncertainty, omit the field (null) rather than guess.
If `no-auto-label` is present on the PR/issue, set `labels: []` and return."#.to_string()
}

pub(crate) fn build_label_pr_prompt(meta: &PrMeta, diff: &str, ctx: &RepoContext) -> String {
    let mut s = inject_context(ctx);
    s.push_str("---\n\n# Label this PR\n\n");
    s.push_str(&format!("PR #{}: {}\n", meta.number, guardrails::sanitize_untrusted(&meta.title)));
    if !meta.body.trim().is_empty() {
        s.push_str("\n## PR Description\n");
        s.push_str(&guardrails::sanitize_untrusted(meta.body.trim()));
        s.push('\n');
    }
    if !meta.files.is_empty() {
        s.push_str(&format!("\n## Changed files ({})\n", meta.files.len()));
        for f in &meta.files {
            s.push_str(&format!("- {f}\n"));
        }
    }
    if !diff.trim().is_empty() {
        s.push_str("\n## Diff (may be truncated)\n```diff\n");
        s.push_str(diff);
        s.push_str("\n```\n");
    }
    s.push_str("\nEmit the JSON labels, milestone, and comment.");
    s
}

pub(crate) fn build_label_issue_prompt(meta: &IssueMeta, ctx: &RepoContext) -> String {
    let mut s = inject_context(ctx);
    s.push_str("---\n\n# Label this issue\n\n");
    s.push_str(&format!("Issue #{}: {}\n", meta.number, guardrails::sanitize_untrusted(&meta.title)));
    if !meta.body.trim().is_empty() {
        s.push_str("\n## Issue Body\n");
        s.push_str(&guardrails::sanitize_untrusted(meta.body.trim()));
        s.push('\n');
    }
    s.push_str("\nEmit the JSON labels, milestone, and comment.");
    s
}

pub(crate) fn build_changelog_prompt(commits: &str, ctx: &RepoContext) -> String {
    let today = chrono_today();
    let mut s = inject_context(ctx);
    s.push_str(&format!(
        "---\n\n# Generate changelog entry\n\nToday: {today}\n\n\
         ## Recent activity\n{commits}\n\n\
         Generate a `changelog_entry` grouped by area. Decide if a `new_tag` \
         is warranted (only for grammar/compiler/protocol version milestones). \
         Set `labels: []`, `comment: null`, `milestone: null`."
    ));
    s
}

pub(crate) fn build_milestone_sync_prompt(ctx: &RepoContext) -> String {
    let mut s = inject_context(ctx);
    s.push_str("---\n\n# Milestone sync\n\n\
     Extract all 6 phase headings (Phase 0 through Phase 5) from the GOALS.md above.\n\
     Return a `milestones_to_upsert` array with title = exact phase heading text and \
     description = the first 2-3 bullet points from that phase.\n\
     Set `labels: []`, `comment: null`, `milestone: null`, `changelog_entry: null`, `new_tag: null`.");
    s
}

fn chrono_today() -> String {
    // Use `date` command — avoids adding a chrono dependency.
    StdCommand::new("date")
        .arg("+%Y-%m-%d")
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim().to_string())
        .unwrap_or_else(|| "2026-01-01".to_string())
}
