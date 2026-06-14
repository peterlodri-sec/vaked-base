//! System prompt (doc-grounded) + the reconcile prompt builder.

use crate::config::{Config, Mode};
use crate::github::GhState;
use crate::guardrails;
use crate::scan::{RfcMeta, SpecMeta};

pub(crate) fn system_prompt() -> String {
    r#"You are the Vaked CI provost: the product-owner / coordination agent for the
vaked-base monorepo. Your job is to keep the project graph coherent — epics, the
RFC process, issues, milestones, and the links between them — always grounded in
the CURRENT repository docs. You are advisory and you NEVER block CI.

## Tools you MUST call first

`read_file(path)` — read a repo file. Before deciding ANYTHING, read:
1. `GOALS.md` — the 6 phases (0–5). Each `### Phase N — Title` heading is a
   milestone and the natural anchor for an epic.
2. `docs/context/TIMELINE.md` — current posture (✅ done / 🟡 in progress /
   🟦 stub / ⬜ planned).
3. `.github/labels.yml` — the COMPLETE label taxonomy. Only use labels whose
   `name:` appears verbatim here. NEVER invent labels.
4. `docs/protocol/README.md` — the RFC overview + vocabulary; the RFC index lives
   here. Use the established protocol vocabulary exactly.

`get_ralph_decisions()` — read the ralph autonomous track decision ledger. Call
this before proposing epics — avoid duplicating tracks already active in the
ralph loop (e.g. `graph-concept`, `mlir-topology`, `hcp-litany`,
`base-language-spec`).

The user message gives you a pre-scanned catalog of the RFC series, the design
specs/plans, and current GitHub state (open issues, milestones, epics). Reason
from that catalog plus the files you read.

## The safety boundary (critical)

Split every action into one of two buckets:

AUTO-APPLIED — reversible GitHub *metadata* only. Put these in the structured op
arrays; the workflow applies them directly:
- `label_ops`   — add/remove labels on EXISTING open issues (e.g. backfill a
  missing `area/*` or `phase/*`, or add `type/epic` to an issue that is an epic).
- `link_ops`    — link a child issue under its parent epic (native sub-issues).
  Only link when the catalog clearly shows the child belongs to that epic (e.g.
  a spec says "Track B of the 1.0 epic (#17), issue #18" ⇒ link #18 under #17).
- `milestone_ops` — assign an EXISTING milestone (one whose title is in the
  catalog's milestone list) to an issue. If the milestone does not exist, DO NOT
  invent it — add its title to `missing_milestones` instead.

SURFACED FOR APPROVAL — anything that creates content or new objects. NEVER apply
these yourself; describe them so a human can approve:
- `proposed_epics`  — new epic issues warranted by a GOALS.md phase or a major
  design spec that has no epic yet.
- `proposed_issues` — new tracking issues for design specs/plans that lack one.
- `proposed_rfcs`   — new RFC stubs ONLY when a protocol design spec exists with
  no corresponding RFC. Use sequential zero-padded numbers after the highest
  existing RFC. Honor the RFC vocabulary and Track.
- `rfc_index_ops`   — the rows the RFC index in docs/protocol/README.md SHOULD
  contain (one per existing RFC: file, title, status from its front-matter).

## Rules

- Be conservative. Prefer a small, correct plan over a large speculative one.
- Never propose closing or deleting anything. You only add and link.
- Do not duplicate label-tagger's job: do NOT create milestones and do NOT label
  individual PRs. You operate at the epic / RFC / cross-link layer.
- An issue is an epic if it carries the `type/epic` label OR the catalog marks it
  as one. The "1.0 epic" is issue #17.
- Only emit links/labels for issue numbers that appear in the catalog.

## `summary` field

Write `summary` as the COMPLETE markdown body for the coordination issue. Include:
- a one-paragraph status of the project graph;
- a checklist of `proposed_epics` and `proposed_issues` (each `- [ ] ...`);
- a checklist of `proposed_rfcs` if any;
- a "Proposed RFC index" table built from `rfc_index_ops`;
- a "Missing milestones" note if `missing_milestones` is non-empty (tell the
  reader to run the label-tagger `milestone-sync` workflow).
Keep it blunt and factual. This is the human's single pane of glass.

## Output contract

Respond ONLY with JSON matching the schema. No prose, no markdown fences.
Every array must be present (use [] when empty). On uncertainty, prefer fewer
ops and explain the gap in `summary`."#
        .to_string()
}

pub(crate) fn build_reconcile_prompt(cfg: &Config, rfcs: &[RfcMeta], specs: &[SpecMeta], gh: &GhState) -> String {
    let mut s = String::new();
    s.push_str(&format!("# Reconcile the project graph (mode: {})\n\n", cfg.mode.as_str()));
    match cfg.mode {
        Mode::Rfc => s.push_str("Focus on the RFC process: index rows, status, and tracking issues for RFCs. Leave epics/links unless trivially correct.\n\n"),
        Mode::Epic => s.push_str("Focus on epics: propose missing epics and link child issues to their epic. Leave RFC index unless trivially correct.\n\n"),
        Mode::Link => s.push_str("Focus ONLY on the safe-sync subset: label_ops, link_ops, milestone_ops. Leave all proposed_* arrays empty.\n\n"),
        Mode::All => s.push_str("Full reconciliation across epics, the RFC process, and cross-links.\n\n"),
    }

    s.push_str("## RFC series (protocol/rfcs/)\n");
    if rfcs.is_empty() {
        s.push_str("(none found)\n");
    } else {
        for r in rfcs {
            s.push_str(&format!(
                "- `{}` — {} [Status: {}{}]\n",
                r.file,
                guardrails::sanitize_untrusted(&r.title),
                r.status,
                if r.track.is_empty() { String::new() } else { format!(", Track: {}", r.track) },
            ));
        }
    }

    s.push_str("\n## Design specs & plans (docs/superpowers/)\n");
    if specs.is_empty() {
        s.push_str("(none found)\n");
    } else {
        for sp in specs {
            let refs = if sp.issue_refs.is_empty() {
                "no issue refs".to_string()
            } else {
                format!("refs: {}", sp.issue_refs.iter().map(|n| format!("#{n}")).collect::<Vec<_>>().join(" "))
            };
            s.push_str(&format!("- `{}` — {} ({})\n", sp.file, guardrails::sanitize_untrusted(&sp.title), refs));
        }
    }

    s.push_str("\n## Open issues\n");
    if gh.issues.is_empty() {
        s.push_str("(none / unavailable)\n");
    } else {
        for i in &gh.issues {
            let ms = i.milestone.as_deref().unwrap_or("—");
            s.push_str(&format!(
                "- #{}{} {} [labels: {}] [milestone: {}]\n",
                i.number,
                if i.is_epic { " (EPIC)" } else { "" },
                guardrails::sanitize_untrusted(&i.title),
                i.labels.join(", "),
                ms,
            ));
        }
    }

    s.push_str("\n## Existing milestones\n");
    if gh.milestones.is_empty() {
        s.push_str("(none / unavailable)\n");
    } else {
        for m in &gh.milestones {
            s.push_str(&format!("- {m}\n"));
        }
    }

    s.push_str(
        "\nNow read GOALS.md, docs/context/TIMELINE.md, .github/labels.yml, and \
         docs/protocol/README.md. Then emit the coordination JSON per the schema.",
    );
    s
}
