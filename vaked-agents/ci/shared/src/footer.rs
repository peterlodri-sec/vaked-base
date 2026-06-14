//! Shared advisory-comment footer, reused across the CI agent fleet.
//!
//! Every agent that posts an advisory comment (pr-review, label-tagger, …)
//! stamps the same `<sub>…</sub>` footer line so the format stays identical and
//! lives in one place. Agents fill only the fields they track; anything left
//! empty is omitted. The link and signature helpers read the standard `GITHUB_*`
//! environment so each agent builds the same commit/run links without
//! duplicating the logic.

use std::fmt::Write as _;

/// `GITHUB_SERVER_URL` (for GitHub Enterprise) or the public default, with any
/// trailing slash trimmed.
pub fn server_url() -> String {
    std::env::var("GITHUB_SERVER_URL")
        .ok()
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "https://github.com".into())
        .trim_end_matches('/')
        .to_string()
}

/// `" · [commit abc1234](url)"` for the given repo and commit SHA, or an empty
/// string when no SHA is available. The leading ` · ` lets callers concatenate
/// links directly.
pub fn commit_link(repo: &str, sha: Option<&str>) -> String {
    match sha {
        Some(s) if !s.is_empty() => {
            let short = &s[..s.len().min(7)];
            format!(" · [commit {short}]({}/{repo}/commit/{s})", server_url())
        }
        _ => String::new(),
    }
}

/// `" · [run](url)"` for the active GitHub Actions run, or an empty string when
/// not running in CI (no `GITHUB_RUN_ID`).
pub fn run_link(repo: &str) -> String {
    match std::env::var("GITHUB_RUN_ID").ok().filter(|s| !s.is_empty()) {
        Some(id) => format!(" · [run]({}/{repo}/actions/runs/{id})", server_url()),
        None => String::new(),
    }
}

/// Compact build stamp `v{version}+{git_sha}` (no PII). Pass each crate's own
/// `CARGO_PKG_VERSION` and build-time `GIT_SHA`.
pub fn signature(version: &str, git_sha: &str) -> String {
    format!("v{version}+{git_sha}")
}

/// One advisory footer line. Metrics render in the given order as `key=value`
/// tokens; links are pre-built tokens (each already prefixed with ` · `).
pub struct Footer<'a> {
    /// Agent name, e.g. `"vaked-ci-reviewer"`.
    pub agent: &'a str,
    /// Ordered `key=value` metric tokens, e.g. `("model", "claude-haiku-4-5")`.
    pub metrics: &'a [(&'a str, String)],
    /// Total runtime in seconds, if measured.
    pub runtime_s: Option<f64>,
    /// Slowest timed stages, e.g. `"review 12.0s, meta 0.8s"`, if tracked.
    pub slowest: Option<&'a str>,
    /// Pre-built link tokens (commit/run/trace), each already prefixed with ` · `.
    pub links: &'a str,
    /// Build signature from [`signature`].
    pub signature: &'a str,
}

impl Footer<'_> {
    /// Render the `<sub>…</sub>` footer line. Always marked advisory.
    pub fn render(&self) -> String {
        let mut s = format!("<sub>{} · advisory", self.agent);
        for (k, v) in self.metrics {
            let _ = write!(s, " · {k}={v}");
        }
        if let Some(rt) = self.runtime_s {
            let _ = write!(s, " · runtime={rt:.1}s");
            if let Some(slow) = self.slowest {
                let _ = write!(s, " (slowest: {slow})");
            }
        }
        s.push_str(self.links);
        let _ = write!(s, " · {}</sub>", self.signature);
        s
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn renders_reviewer_shape() {
        let metrics = [
            ("model", "claude-haiku-4-5".to_string()),
            ("findings", "3".to_string()),
        ];
        let f = Footer {
            agent: "vaked-ci-reviewer",
            metrics: &metrics,
            runtime_s: Some(12.34),
            slowest: Some("review 12.0s"),
            links: " · [run](https://example/run)",
            signature: "v0.4.0+abc1234",
        };
        assert_eq!(
            f.render(),
            "<sub>vaked-ci-reviewer · advisory · model=claude-haiku-4-5 · findings=3 \
             · runtime=12.3s (slowest: review 12.0s) · [run](https://example/run) \
             · v0.4.0+abc1234</sub>"
        );
    }

    #[test]
    fn omits_absent_fields() {
        let metrics = [("model", "x".to_string())];
        let f = Footer {
            agent: "vaked-label-tagger",
            metrics: &metrics,
            runtime_s: None,
            slowest: None,
            links: "",
            signature: "v0.1.0+deadbee",
        };
        assert_eq!(
            f.render(),
            "<sub>vaked-label-tagger · advisory · model=x · v0.1.0+deadbee</sub>"
        );
    }
}
