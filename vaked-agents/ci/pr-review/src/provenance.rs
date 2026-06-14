//! Provenance round — commit-signature verification (advisory).

use tracing::warn;

use crate::config::Config;
use crate::github::gh;

/// Maintainer GitHub login — commits authored by them that aren't signature-verified
/// are flagged in the provenance round. Keep in sync with `prompts/ci-agent-briefing.md`.
const MAINTAINER_LOGIN: &str = "peterlodri-sec";
/// Maintainer's published GPG signing-key fingerprints (provenance reference; the
/// runtime check trusts GitHub's server-side `verified` flag, which already validates
/// against these account-registered keys). Source: github.com/peterlodri-sec.gpg.
const MAINTAINER_GPG_FPRS: &[&str] = &[
    "72581F31DD0EE484B6714ACB2B2495E0AC50DAC7", // maintainer signing key (uid 1)
    "25B2B8EA46DCC314187EF5F4B7FE23390470D65C", // maintainer signing key (uid 2)
    "6A476414899DD9AA82445A7AA893B8B408AC3C8B", // maintainer signing key (uid 3)
];

/// Commit-signature provenance for the PR's commits.
pub(crate) struct Provenance {
    total: usize,
    verified: usize,
    /// Short SHAs of commits GitHub did NOT report as signature-verified.
    unverified: Vec<String>,
    /// Of those, the ones authored by the maintainer — a real provenance concern.
    unverified_maintainer: Vec<String>,
}

impl Provenance {
    /// One-line markdown summary appended above the review footer (empty when no commits).
    pub(crate) fn summary_line(&self) -> String {
        if self.total == 0 {
            return String::new();
        }
        if self.unverified.is_empty() {
            return format!(
                "\n<sub>🔏 provenance: {}/{} commits signature-verified</sub>",
                self.verified, self.total
            );
        }
        let mut s = format!(
            "\n<sub>🔏 provenance: {}/{} commits verified",
            self.verified, self.total
        );
        if !self.unverified_maintainer.is_empty() {
            // Reference the maintainer's primary signing key so the warning is actionable.
            let fpr = MAINTAINER_GPG_FPRS.first().copied().unwrap_or("");
            let short = &fpr[fpr.len().saturating_sub(8)..];
            s.push_str(&format!(
                " · ⚠ {} commit(s) by @{MAINTAINER_LOGIN} unsigned/unverified ({}) — expected a known key (…{short})",
                self.unverified_maintainer.len(),
                self.unverified_maintainer.join(", "),
            ));
        } else {
            s.push_str(&format!(
                " · {} unverified ({})",
                self.unverified.len(),
                self.unverified.join(", ")
            ));
        }
        s.push_str("</sub>");
        s
    }
}

/// Best-effort commit-signature provenance via GitHub's server-side verification
/// (`commit.verification.verified`, validated against the committer's account-registered
/// keys). Advisory: returns `None` if the API call fails or there are no commits.
pub(crate) fn fetch_provenance(cfg: &Config) -> Option<Provenance> {
    let endpoint = format!("repos/{}/pulls/{}/commits", cfg.repo, cfg.pr);
    // One TSV row per commit: short-sha, verified, author login.
    let jq = r#".[] | [(.sha[0:7]), (.commit.verification.verified|tostring), (.author.login // "")] | @tsv"#;
    let out = match gh(&["api", "--paginate", &endpoint, "--jq", jq]) {
        Ok(s) => s,
        Err(e) => {
            warn!(error = %e, "provenance: could not list PR commits — skipping");
            return None;
        }
    };
    let mut p = Provenance {
        total: 0,
        verified: 0,
        unverified: Vec::new(),
        unverified_maintainer: Vec::new(),
    };
    for line in out.lines().filter(|l| !l.trim().is_empty()) {
        let mut it = line.split('\t');
        let sha = it.next().unwrap_or("").trim().to_string();
        let verified = it.next() == Some("true");
        let login = it.next().unwrap_or("").trim();
        if sha.is_empty() {
            continue;
        }
        p.total += 1;
        if verified {
            p.verified += 1;
        } else {
            if login.eq_ignore_ascii_case(MAINTAINER_LOGIN) {
                p.unverified_maintainer.push(sha.clone());
            }
            p.unverified.push(sha);
        }
    }
    (p.total > 0).then_some(p)
}
