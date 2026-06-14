//! Output parsing.

use tracing::warn;

use crate::output::TaggerOutput;

fn strip_fences(s: &str) -> &str {
    let s = s.trim();
    if let Some(rest) = s.strip_prefix("```json").or_else(|| s.strip_prefix("```")) {
        return rest.trim_end_matches("```").trim();
    }
    s
}

pub(crate) fn parse_output(raw: &str) -> TaggerOutput {
    let clean = strip_fences(raw);
    match serde_json::from_str::<TaggerOutput>(clean) {
        Ok(mut out) => {
            // Safety: cap labels to a reasonable number.
            out.labels.truncate(10);
            out
        }
        Err(e) => {
            warn!(error = %e, "failed to parse agent JSON output — using noop");
            TaggerOutput::default()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_output_handles_valid_json() {
        let json = r#"{"labels":["area/language","type/feature"],"comment":"test","milestone":"Phase 0 — Language foundation","changelog_entry":null,"new_tag":null}"#;
        let out = parse_output(json);
        assert_eq!(out.labels.len(), 2);
        assert_eq!(out.labels[0], "area/language");
    }

    #[test]
    fn parse_output_handles_invalid_json() {
        let out = parse_output("not json at all");
        assert!(out.labels.is_empty());
        assert!(out.comment.is_none());
    }

    #[test]
    fn parse_output_strips_fences() {
        let json = "```json\n{\"labels\":[],\"comment\":null,\"milestone\":null,\"changelog_entry\":null,\"new_tag\":null}\n```";
        let out = parse_output(json);
        assert!(out.labels.is_empty());
    }
}
