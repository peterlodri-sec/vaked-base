//! Unified-diff parsing/filtering helpers.

use std::collections::HashMap;

fn is_noise(path: &str) -> bool {
    let p = path.to_ascii_lowercase();
    const SUFFIXES: &[&str] = &[
        ".lock", ".snap", ".min.js", ".min.css", ".pb.go", ".png", ".jpg", ".jpeg", ".gif", ".svg",
        ".ico", ".pdf", ".woff", ".woff2", ".ttf", ".lockb",
    ];
    const NAMES: &[&str] = &[
        "cargo.lock",
        "flake.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "go.sum",
    ];
    const DIRS: &[&str] = &[
        "vendor/",
        "node_modules/",
        "dist/",
        "build/",
        "target/",
        ".crabcc/",
    ];
    let base = p.rsplit('/').next().unwrap_or(&p);
    NAMES.contains(&base)
        || SUFFIXES.iter().any(|s| p.ends_with(s))
        || DIRS.iter().any(|d| p.contains(d))
}

pub(crate) fn split_per_file(unified: &str) -> Vec<(String, String)> {
    let mut out: Vec<(String, String)> = Vec::new();
    let mut path = String::new();
    let mut buf = String::new();
    for line in unified.lines() {
        if let Some(rest) = line.strip_prefix("diff --git ") {
            if !buf.is_empty() {
                out.push((std::mem::take(&mut path), std::mem::take(&mut buf)));
            }
            path = rest
                .split(" b/")
                .nth(1)
                .map(String::from)
                .unwrap_or_else(|| rest.to_string());
        }
        buf.push_str(line);
        buf.push('\n');
    }
    if !buf.is_empty() {
        out.push((path, buf));
    }
    out
}

pub(crate) fn filter_unified(unified: &str) -> String {
    if !unified.contains("diff --git ") {
        return unified.to_string();
    }
    split_per_file(unified)
        .into_iter()
        .filter(|(path, _)| !is_noise(path))
        .map(|(_, section)| section)
        .collect::<Vec<_>>()
        .join("")
}

pub(crate) fn count_changed_lines(unified: &str) -> usize {
    unified
        .lines()
        .filter(|l| {
            (l.starts_with('+') && !l.starts_with("+++"))
                || (l.starts_with('-') && !l.starts_with("---"))
        })
        .count()
}

/// Map each file path -> set of RIGHT-side (new-file) line numbers present in the
/// unified diff (added `+` and context lines). GitHub inline review comments can
/// only attach to these lines; a finding citing a line not in this set is stale or
/// hallucinated, so it is dropped (also avoids a 422 that fails the whole review).
pub(crate) fn diff_right_lines(unified: &str) -> HashMap<String, std::collections::HashSet<u32>> {
    let mut map: HashMap<String, std::collections::HashSet<u32>> = HashMap::new();
    let mut path = String::new();
    let mut new_line = 0u32;
    let mut in_hunk = false;
    for line in unified.lines() {
        if let Some(rest) = line.strip_prefix("+++ b/") {
            path = rest.trim().to_string();
            in_hunk = false;
        } else if line.starts_with("diff --git") {
            // Provisional path until the `+++ b/` header refines it (handles renames).
            path = line.split(" b/").nth(1).map(|s| s.trim().to_string()).unwrap_or_default();
            in_hunk = false;
        } else if line.starts_with("--- ") {
            continue;
        } else if let Some(h) = line.strip_prefix("@@") {
            // @@ -a,b +c,d @@ — start counting the new file at c.
            new_line = h
                .split('+')
                .nth(1)
                .map(|p| p.chars().take_while(|c| c.is_ascii_digit()).collect::<String>())
                .and_then(|n| n.parse().ok())
                .unwrap_or(0);
            in_hunk = new_line > 0;
        } else if in_hunk && !path.is_empty() {
            match line.as_bytes().first() {
                Some(b'+') => {
                    map.entry(path.clone()).or_default().insert(new_line);
                    new_line += 1;
                }
                Some(b'-') => {} // deletion: left side only, don't advance the new-file counter
                Some(b'\\') => {} // "\ No newline at end of file"
                _ => {
                    // context (space-prefixed) or blank line — addressable, advances
                    map.entry(path.clone()).or_default().insert(new_line);
                    new_line += 1;
                }
            }
        }
    }
    map
}
