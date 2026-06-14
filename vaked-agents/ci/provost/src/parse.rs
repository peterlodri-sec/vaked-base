//! Output parsing + the no-API-key deterministic fallback plan.

use tracing::warn;

use crate::output::{ProvostOutput, RfcIndexOp};
use crate::scan::RfcMeta;

fn strip_fences(s: &str) -> &str {
    let s = s.trim();
    if let Some(rest) = s.strip_prefix("```json").or_else(|| s.strip_prefix("```")) {
        return rest.trim_end_matches("```").trim();
    }
    s
}

pub(crate) fn parse_output(raw: &str) -> ProvostOutput {
    let clean = strip_fences(raw);
    match serde_json::from_str::<ProvostOutput>(clean) {
        Ok(mut out) => {
            // Safety caps so a runaway plan can't spam the repo.
            out.label_ops.truncate(50);
            out.link_ops.truncate(50);
            out.milestone_ops.truncate(50);
            out.rfc_index_ops.truncate(50);
            out.proposed_epics.truncate(20);
            out.proposed_issues.truncate(30);
            out.proposed_rfcs.truncate(10);
            out.missing_milestones.truncate(20);
            out
        }
        Err(e) => {
            warn!(error = %e, "failed to parse agent JSON output — using noop");
            ProvostOutput::default()
        }
    }
}

/// Deterministic plan when no API key is available: surface the RFC index rows
/// (computed from front-matter) and nothing judgment-heavy.
pub(crate) fn deterministic_plan(rfcs: &[RfcMeta]) -> ProvostOutput {
    let rfc_index_ops: Vec<RfcIndexOp> = rfcs
        .iter()
        .map(|r| RfcIndexOp {
            rfc_file: r.file.clone(),
            title: r.title.clone(),
            status: r.status.clone(),
        })
        .collect();
    let mut summary = String::from(
        "<!-- provost: deterministic -->\n\n\
         **Provost ran without an API key** — only the deterministic RFC index \
         reconciliation is shown below. Judgment-heavy proposals (epics, new \
         issues, links) are skipped until `OPENROUTER_API_KEY` is set.\n\n\
         ## Proposed RFC index\n\n| RFC | Title | Status |\n|-----|-------|--------|\n",
    );
    for r in rfcs {
        summary.push_str(&format!("| `{}` | {} | {} |\n", r.file, r.title, r.status));
    }
    ProvostOutput { rfc_index_ops, summary, ..Default::default() }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_output_handles_valid_json() {
        let json = r#"{"label_ops":[{"issue":18,"add":["type/epic"],"remove":[]}],"link_ops":[{"parent_issue":17,"child_issue":18}],"milestone_ops":[],"rfc_index_ops":[],"proposed_epics":[],"proposed_issues":[],"proposed_rfcs":[],"missing_milestones":[],"summary":"ok"}"#;
        let out = parse_output(json);
        assert_eq!(out.label_ops.len(), 1);
        assert_eq!(out.label_ops[0].issue, 18);
        assert_eq!(out.link_ops[0].parent_issue, 17);
        assert_eq!(out.summary, "ok");
    }

    #[test]
    fn parse_output_handles_invalid_json() {
        let out = parse_output("not json at all");
        assert!(out.label_ops.is_empty());
        assert!(out.summary.is_empty());
    }

    #[test]
    fn parse_output_strips_fences() {
        let json = "```json\n{\"label_ops\":[],\"link_ops\":[],\"milestone_ops\":[],\"rfc_index_ops\":[],\"proposed_epics\":[],\"proposed_issues\":[],\"proposed_rfcs\":[],\"missing_milestones\":[],\"summary\":\"x\"}\n```";
        let out = parse_output(json);
        assert_eq!(out.summary, "x");
    }

    #[test]
    fn deterministic_plan_lists_rfcs() {
        let rfcs = vec![RfcMeta {
            file: "protocol/rfcs/0001-hcp.md".into(),
            title: "HCP".into(),
            status: "Draft".into(),
            track: "Protocol".into(),
        }];
        let plan = deterministic_plan(&rfcs);
        assert_eq!(plan.rfc_index_ops.len(), 1);
        assert!(plan.summary.contains("0001-hcp.md"));
        assert!(plan.proposed_epics.is_empty());
    }
}
