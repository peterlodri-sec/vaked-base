//! Task schema: one unit of work = run swe_af against one GitHub issue.

use anyhow::{Result, anyhow};
use serde::{Deserialize, Serialize};

/// A unit of work the orchestrator leases from the NATS work-queue.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub task_id: String,
    /// "owner/name"
    pub repo: String,
    pub issue_number: u64,
    #[serde(default)]
    pub plan_model: Option<String>,
    #[serde(default)]
    pub code_model: Option<String>,
    #[serde(default)]
    pub max_files: Option<usize>,
}

/// A repo must be exactly `owner/name`, each segment safe (no traversal).
fn valid_repo(repo: &str) -> bool {
    let mut parts = repo.split('/');
    let (Some(owner), Some(name), None) = (parts.next(), parts.next(), parts.next()) else {
        return false;
    };
    let ok = |s: &str| {
        !s.is_empty()
            && !s.contains("..")
            && s.chars()
                .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'))
    };
    ok(owner) && ok(name)
}

impl Task {
    /// Parse + validate a task from JSON bytes (the NATS message payload).
    pub fn from_json(bytes: &[u8]) -> Result<Self> {
        let t: Task = serde_json::from_slice(bytes).map_err(|e| anyhow!("task json: {e}"))?;
        if t.task_id.is_empty() {
            return Err(anyhow!("task_id required"));
        }
        if !valid_repo(&t.repo) {
            return Err(anyhow!("invalid repo: {}", t.repo));
        }
        if t.issue_number == 0 {
            return Err(anyhow!("issue_number must be > 0"));
        }
        Ok(t)
    }

    /// Deterministic branch name for this task's PR.
    pub fn branch(&self) -> String {
        format!("swe-af/issue-{}", self.issue_number)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_minimal_task() {
        let j = r#"{"task_id":"t1","repo":"peterlodri-sec/vaked-base","issue_number":42}"#;
        let t = Task::from_json(j.as_bytes()).unwrap();
        assert_eq!(t.task_id, "t1");
        assert_eq!(t.repo, "peterlodri-sec/vaked-base");
        assert_eq!(t.issue_number, 42);
        assert_eq!(t.plan_model, None);
    }

    #[test]
    fn rejects_bad_repo() {
        for bad in [
            r#"{"task_id":"t1","repo":"../evil","issue_number":1}"#,
            r#"{"task_id":"t1","repo":"justone","issue_number":1}"#,
            r#"{"task_id":"t1","repo":"a/b/c","issue_number":1}"#,
            r#"{"task_id":"t1","repo":"a/..","issue_number":1}"#,
        ] {
            assert!(
                Task::from_json(bad.as_bytes()).is_err(),
                "should reject: {bad}"
            );
        }
    }

    #[test]
    fn rejects_empty_id_and_zero_issue() {
        assert!(Task::from_json(br#"{"task_id":"","repo":"a/b","issue_number":1}"#).is_err());
        assert!(Task::from_json(br#"{"task_id":"t","repo":"a/b","issue_number":0}"#).is_err());
    }

    #[test]
    fn branch_name_is_deterministic() {
        let t = Task {
            task_id: "t1".into(),
            repo: "a/b".into(),
            issue_number: 42,
            plan_model: None,
            code_model: None,
            max_files: None,
        };
        assert_eq!(t.branch(), "swe-af/issue-42");
    }
}
