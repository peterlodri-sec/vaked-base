//! Output schema + no-op fallback.

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Debug, Serialize, Deserialize, Default)]
pub(crate) struct TaggerOutput {
    /// Labels to apply (area/*, type/*, phase/* from .github/labels.yml only).
    pub(crate) labels: Vec<String>,
    /// Optional short markdown comment to post on the PR/issue.
    pub(crate) comment: Option<String>,
    /// Exact GOALS.md phase title to assign as milestone, or null.
    pub(crate) milestone: Option<String>,
    /// Keep-a-Changelog formatted entry string, or null.
    pub(crate) changelog_entry: Option<String>,
    /// Git tag to create (e.g. "v0.3.0"), or null. Only set in changelog mode.
    pub(crate) new_tag: Option<String>,
    /// Milestones to upsert (milestone-sync mode only).
    #[serde(skip_serializing_if = "Vec::is_empty", default)]
    pub(crate) milestones_to_upsert: Vec<MilestoneSpec>,
}

#[derive(Debug, Serialize, Deserialize)]
pub(crate) struct MilestoneSpec {
    pub(crate) title: String,
    pub(crate) description: String,
}

/// JSON schema for the LLM structured output (label/changelog modes).
pub(crate) fn output_schema() -> Value {
    json!({
        "type": "object",
        "additionalProperties": false,
        "required": ["labels", "comment", "milestone", "changelog_entry", "new_tag"],
        "properties": {
            "labels": {
                "type": "array",
                "items": { "type": "string" },
                "description": "Labels to apply from the labels.yml taxonomy"
            },
            "comment": {
                "type": ["string", "null"],
                "description": "Short markdown comment to post, or null"
            },
            "milestone": {
                "type": ["string", "null"],
                "description": "Exact phase title from GOALS.md to assign, or null"
            },
            "changelog_entry": {
                "type": ["string", "null"],
                "description": "Keep-a-Changelog formatted entry, or null"
            },
            "new_tag": {
                "type": ["string", "null"],
                "description": "Git tag to create (changelog mode only), or null"
            }
        }
    })
}

/// The empty fallback emitted when anything goes wrong (advisory — never block CI).
pub(crate) fn noop_json() -> String {
    serde_json::to_string(&TaggerOutput::default()).unwrap()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn noop_json_is_valid() {
        let s = noop_json();
        let v: Value = serde_json::from_str(&s).expect("noop JSON must be valid");
        assert!(v["labels"].is_array());
    }
}
