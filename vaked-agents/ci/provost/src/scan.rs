//! Pre-scan: RFC series + design specs/plans on disk.

use crate::consts::{PLAN_DIR, RFC_DIR, SPEC_DIR};

#[derive(Debug, Clone)]
pub(crate) struct RfcMeta {
    pub(crate) file: String,
    pub(crate) title: String,
    pub(crate) status: String,
    pub(crate) track: String,
}

/// Strip markdown list/bold markers and split a "Key: Value" line.
fn md_kv(line: &str) -> Option<(String, String)> {
    let t = line.trim().trim_start_matches('-').trim();
    let t = t.replace("**", "");
    let (k, v) = t.split_once(':')?;
    Some((k.trim().to_ascii_lowercase(), v.trim().to_string()))
}

fn parse_rfc_front(text: &str, file: &str) -> RfcMeta {
    let mut title = String::new();
    let mut status = String::new();
    let mut track = String::new();
    for line in text.lines().take(40) {
        let t = line.trim();
        if title.is_empty() {
            if let Some(h) = t.strip_prefix("# ") {
                title = h.trim().to_string();
            }
        }
        if let Some((k, v)) = md_kv(t) {
            match k.as_str() {
                "status" if status.is_empty() => status = v,
                "track" if track.is_empty() => track = v,
                _ => {}
            }
        }
    }
    RfcMeta {
        file: file.to_string(),
        title: if title.is_empty() { file.to_string() } else { title },
        status: if status.is_empty() { "Unknown".to_string() } else { status },
        track,
    }
}

pub(crate) fn scan_rfcs() -> Vec<RfcMeta> {
    let mut rfcs = Vec::new();
    let Ok(entries) = std::fs::read_dir(RFC_DIR) else {
        return rfcs;
    };
    let mut paths: Vec<String> = entries
        .filter_map(|e| e.ok())
        .map(|e| e.path().to_string_lossy().into_owned())
        .filter(|p| p.ends_with(".md") && !p.ends_with("README.md"))
        .collect();
    paths.sort();
    for p in paths {
        if let Ok(text) = std::fs::read_to_string(&p) {
            rfcs.push(parse_rfc_front(&text, &p));
        }
    }
    rfcs
}

#[derive(Debug, Clone)]
pub(crate) struct SpecMeta {
    pub(crate) file: String,
    pub(crate) title: String,
    pub(crate) issue_refs: Vec<u64>,
}

/// Pull `#NNN` issue references out of text.
fn extract_issue_refs(text: &str) -> Vec<u64> {
    let bytes = text.as_bytes();
    let mut refs = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'#' {
            let mut j = i + 1;
            let mut n: u64 = 0;
            let mut any = false;
            while j < bytes.len() && bytes[j].is_ascii_digit() {
                n = n.saturating_mul(10).saturating_add((bytes[j] - b'0') as u64);
                j += 1;
                any = true;
            }
            if any {
                refs.push(n);
            }
            i = j;
        } else {
            i += 1;
        }
    }
    refs.sort_unstable();
    refs.dedup();
    refs
}

fn scan_specs_in(dir: &str) -> Vec<SpecMeta> {
    let mut specs = Vec::new();
    let Ok(entries) = std::fs::read_dir(dir) else {
        return specs;
    };
    let mut paths: Vec<String> = entries
        .filter_map(|e| e.ok())
        .map(|e| e.path().to_string_lossy().into_owned())
        .filter(|p| p.ends_with(".md") && !p.ends_with("README.md"))
        .collect();
    paths.sort();
    for p in paths {
        if let Ok(text) = std::fs::read_to_string(&p) {
            let title = text
                .lines()
                .find_map(|l| l.trim().strip_prefix("# ").map(|h| h.trim().to_string()))
                .unwrap_or_else(|| p.clone());
            // Issue refs from the top of the file (the status block).
            let head: String = text.lines().take(15).collect::<Vec<_>>().join("\n");
            specs.push(SpecMeta {
                file: p.clone(),
                title,
                issue_refs: extract_issue_refs(&head),
            });
        }
    }
    specs
}

pub(crate) fn scan_specs() -> Vec<SpecMeta> {
    let mut all = scan_specs_in(SPEC_DIR);
    all.extend(scan_specs_in(PLAN_DIR));
    all
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn md_kv_parses_bold_and_plain() {
        assert_eq!(md_kv("- **Status:** Draft"), Some(("status".into(), "Draft".into())));
        assert_eq!(md_kv("Track: Protocol"), Some(("track".into(), "Protocol".into())));
        assert_eq!(md_kv("no colon here"), None);
    }

    #[test]
    fn parse_rfc_front_extracts_fields() {
        let text = "# 0007 — Post-Quantum Litany\n\n- **Status:** Draft\n- **Created:** 2026-06-13\n- **Track:** Protocol\n\n## Abstract\n";
        let m = parse_rfc_front(text, "protocol/rfcs/0007-pq.md");
        assert_eq!(m.title, "0007 — Post-Quantum Litany");
        assert_eq!(m.status, "Draft");
        assert_eq!(m.track, "Protocol");
    }

    #[test]
    fn parse_rfc_front_defaults_when_missing() {
        let m = parse_rfc_front("no heading, no front matter", "protocol/rfcs/x.md");
        assert_eq!(m.status, "Unknown");
        assert_eq!(m.title, "protocol/rfcs/x.md");
    }

    #[test]
    fn extract_issue_refs_finds_numbers() {
        let refs = extract_issue_refs("Track B of the 1.0 epic (#17), issue #18. See #18 again.");
        assert_eq!(refs, vec![17, 18]);
    }

    #[test]
    fn extract_issue_refs_empty() {
        assert!(extract_issue_refs("no refs here").is_empty());
    }
}
