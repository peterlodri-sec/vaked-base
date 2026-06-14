//! System prompt (doc-grounded) + per-mode prompt builders.

use std::process::Command as StdCommand;

use crate::github::{IssueMeta, PrMeta};
use crate::guardrails;

pub(crate) fn system_prompt() -> String {
    r#"You are the Vaked CI label-tagger: a doc-grounded automation agent for the
vaked-base monorepo. Your ONLY job is to classify a PR, issue, or set of merged
commits and emit structured JSON. You are advisory — you NEVER block CI.

## Tool you MUST call first

`read_file(path)` — read a repo file. Before making ANY decision, call it for:
1. `GOALS.md` — 6 phases (0–5). Each `### Phase N — Title` heading is a milestone.
   Map the change to the most relevant phase.
2. `docs/context/TIMELINE.md` — current project posture (✅ done / 🟡 in progress /
   🟦 stub / ⬜ planned). Use this to judge which phase the change advances.
3. `.github/labels.yml` — the COMPLETE label taxonomy. You MUST only emit labels
   whose `name:` field appears verbatim in this file. DO NOT invent labels.

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

pub(crate) fn build_label_pr_prompt(meta: &PrMeta, diff: &str) -> String {
    let mut s = String::new();
    s.push_str("# Label this PR\n\n");
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
    s.push_str("\nRead GOALS.md, docs/context/TIMELINE.md, and .github/labels.yml now.\nThen emit the JSON labels, milestone, and comment.");
    s
}

pub(crate) fn build_label_issue_prompt(meta: &IssueMeta) -> String {
    let mut s = String::new();
    s.push_str("# Label this issue\n\n");
    s.push_str(&format!("Issue #{}: {}\n", meta.number, guardrails::sanitize_untrusted(&meta.title)));
    if !meta.body.trim().is_empty() {
        s.push_str("\n## Issue Body\n");
        s.push_str(&guardrails::sanitize_untrusted(meta.body.trim()));
        s.push('\n');
    }
    s.push_str("\nRead GOALS.md, docs/context/TIMELINE.md, and .github/labels.yml now.\nThen emit the JSON labels, milestone, and comment.");
    s
}

pub(crate) fn build_changelog_prompt(commits: &str) -> String {
    let today = chrono_today();
    format!(
        "# Generate changelog entry\n\n\
         Today: {today}\n\n\
         ## Recent activity\n{commits}\n\n\
         Read GOALS.md, docs/context/TIMELINE.md, and .github/labels.yml now.\n\
         Then generate a `changelog_entry` grouped by area. Decide if a `new_tag` \
         is warranted (only for grammar/compiler/protocol version milestones). \
         Set `labels: []`, `comment: null`, `milestone: null`."
    )
}

pub(crate) fn build_milestone_sync_prompt() -> String {
    "# Milestone sync\n\n\
     Read GOALS.md now. Extract all 6 phase headings (Phase 0 through Phase 5).\n\
     Return a `milestones_to_upsert` array with title = exact phase heading text and \
     description = the first 2-3 bullet points from that phase.\n\
     Set `labels: []`, `comment: null`, `milestone: null`, `changelog_entry: null`, `new_tag: null`."
        .to_string()
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
