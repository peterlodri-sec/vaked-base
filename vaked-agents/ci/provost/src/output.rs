//! Output schema (the JSON contract the workflow shell consumes) + no-op fallback.

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Debug, Serialize, Deserialize, Default)]
pub(crate) struct ProvostOutput {
    /// Auto-applied: label add/remove on existing issues.
    #[serde(default)]
    pub(crate) label_ops: Vec<LabelOp>,
    /// Auto-applied: native sub-issue parent↔child links.
    #[serde(default)]
    pub(crate) link_ops: Vec<LinkOp>,
    /// Auto-applied: assign an EXISTING milestone to an issue.
    #[serde(default)]
    pub(crate) milestone_ops: Vec<MilestoneOp>,
    /// Surfaced: proposed RFC index entries (rendered into the coordination issue).
    #[serde(default)]
    pub(crate) rfc_index_ops: Vec<RfcIndexOp>,
    /// Surfaced: proposed new epics (checklist in the coordination issue).
    #[serde(default)]
    pub(crate) proposed_epics: Vec<ProposedEpic>,
    /// Surfaced: proposed new issues (checklist in the coordination issue).
    #[serde(default)]
    pub(crate) proposed_issues: Vec<ProposedIssue>,
    /// Surfaced: proposed new RFC stubs (written to the coordination PR).
    #[serde(default)]
    pub(crate) proposed_rfcs: Vec<ProposedRfc>,
    /// Note for a human: milestones referenced but absent (run label-tagger milestone-sync).
    #[serde(default)]
    pub(crate) missing_milestones: Vec<String>,
    /// Complete markdown body for the coordination issue (LLM-authored).
    #[serde(default)]
    pub(crate) summary: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub(crate) struct LabelOp {
    pub(crate) issue: u64,
    #[serde(default)]
    pub(crate) add: Vec<String>,
    #[serde(default)]
    pub(crate) remove: Vec<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub(crate) struct LinkOp {
    pub(crate) parent_issue: u64,
    pub(crate) child_issue: u64,
}

#[derive(Debug, Serialize, Deserialize)]
pub(crate) struct MilestoneOp {
    pub(crate) issue: u64,
    pub(crate) milestone_title: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub(crate) struct RfcIndexOp {
    pub(crate) rfc_file: String,
    pub(crate) title: String,
    pub(crate) status: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub(crate) struct ProposedEpic {
    pub(crate) title: String,
    #[serde(default)]
    pub(crate) body: String,
    #[serde(default)]
    pub(crate) labels: Vec<String>,
    #[serde(default)]
    pub(crate) milestone: Option<String>,
    #[serde(default)]
    pub(crate) children: Vec<u64>,
}

#[derive(Debug, Serialize, Deserialize)]
pub(crate) struct ProposedIssue {
    pub(crate) title: String,
    #[serde(default)]
    pub(crate) body: String,
    #[serde(default)]
    pub(crate) labels: Vec<String>,
    #[serde(default)]
    pub(crate) epic: Option<u64>,
}

#[derive(Debug, Serialize, Deserialize)]
pub(crate) struct ProposedRfc {
    pub(crate) number: String,
    pub(crate) slug: String,
    pub(crate) title: String,
    #[serde(default)]
    pub(crate) track: String,
    #[serde(default)]
    pub(crate) rationale: String,
}

/// JSON schema for the LLM structured output.
pub(crate) fn output_schema() -> Value {
    json!({
        "type": "object",
        "additionalProperties": false,
        "required": [
            "label_ops", "link_ops", "milestone_ops", "rfc_index_ops",
            "proposed_epics", "proposed_issues", "proposed_rfcs",
            "missing_milestones", "summary"
        ],
        "properties": {
            "label_ops": {
                "type": "array",
                "description": "Label add/remove on existing issues (safe-sync)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["issue", "add", "remove"],
                    "properties": {
                        "issue": { "type": "integer" },
                        "add": { "type": "array", "items": { "type": "string" } },
                        "remove": { "type": "array", "items": { "type": "string" } }
                    }
                }
            },
            "link_ops": {
                "type": "array",
                "description": "Native sub-issue parent↔child links (safe-sync)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["parent_issue", "child_issue"],
                    "properties": {
                        "parent_issue": { "type": "integer" },
                        "child_issue": { "type": "integer" }
                    }
                }
            },
            "milestone_ops": {
                "type": "array",
                "description": "Assign an EXISTING milestone to an issue (safe-sync)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["issue", "milestone_title"],
                    "properties": {
                        "issue": { "type": "integer" },
                        "milestone_title": { "type": "string" }
                    }
                }
            },
            "rfc_index_ops": {
                "type": "array",
                "description": "Proposed RFC index rows (surfaced in coordination issue)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["rfc_file", "title", "status"],
                    "properties": {
                        "rfc_file": { "type": "string" },
                        "title": { "type": "string" },
                        "status": { "type": "string" }
                    }
                }
            },
            "proposed_epics": {
                "type": "array",
                "description": "Proposed new epics (surfaced for human approval)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["title", "body", "labels", "children"],
                    "properties": {
                        "title": { "type": "string" },
                        "body": { "type": "string" },
                        "labels": { "type": "array", "items": { "type": "string" } },
                        "milestone": { "type": ["string", "null"] },
                        "children": { "type": "array", "items": { "type": "integer" } }
                    }
                }
            },
            "proposed_issues": {
                "type": "array",
                "description": "Proposed new issues (surfaced for human approval)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["title", "body", "labels"],
                    "properties": {
                        "title": { "type": "string" },
                        "body": { "type": "string" },
                        "labels": { "type": "array", "items": { "type": "string" } },
                        "epic": { "type": ["integer", "null"] }
                    }
                }
            },
            "proposed_rfcs": {
                "type": "array",
                "description": "Proposed new RFC stubs (surfaced via coordination PR)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["number", "slug", "title", "track", "rationale"],
                    "properties": {
                        "number": { "type": "string" },
                        "slug": { "type": "string" },
                        "title": { "type": "string" },
                        "track": { "type": "string" },
                        "rationale": { "type": "string" }
                    }
                }
            },
            "missing_milestones": {
                "type": "array",
                "items": { "type": "string" },
                "description": "Milestones referenced but absent in the repo"
            },
            "summary": {
                "type": "string",
                "description": "Complete markdown body for the coordination issue"
            }
        }
    })
}

/// The empty fallback emitted when anything goes wrong (advisory — never block CI).
pub(crate) fn noop_json() -> String {
    serde_json::to_string(&ProvostOutput::default()).unwrap()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn noop_json_is_valid() {
        let s = noop_json();
        let v: Value = serde_json::from_str(&s).expect("noop JSON must be valid");
        assert!(v["label_ops"].is_array());
        assert!(v["summary"].is_string());
    }

    #[test]
    fn output_schema_is_object() {
        let schema = output_schema();
        assert_eq!(schema["type"], "object");
        assert!(schema["properties"]["summary"].is_object());
    }
}
