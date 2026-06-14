//! Status events published to `swe.af.status.<task>.<node>` for the live console.

use serde::Serialize;

/// The DAG node a status event refers to.
#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Node {
    Run,
    Plan,
    Code,
    Apply,
    Publish,
    Review,
    Done,
    Error,
}

impl Node {
    fn as_str(self) -> &'static str {
        match self {
            Node::Run => "run",
            Node::Plan => "plan",
            Node::Code => "code",
            Node::Apply => "apply",
            Node::Publish => "publish",
            Node::Review => "review",
            Node::Done => "done",
            Node::Error => "error",
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct StatusEvent {
    pub task_id: String,
    pub node: Node,
    pub state: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
}

impl StatusEvent {
    pub fn new(task_id: &str, node: Node, state: &str) -> Self {
        Self {
            task_id: task_id.to_string(),
            node,
            state: state.to_string(),
            detail: None,
        }
    }

    pub fn with_detail(mut self, d: &str) -> Self {
        self.detail = Some(d.to_string());
        self
    }

    /// `<prefix>.<task_id>.<node>`
    pub fn subject(&self, prefix: &str) -> String {
        format!("{prefix}.{}.{}", self.task_id, self.node.as_str())
    }

    pub fn encode(&self) -> Vec<u8> {
        serde_json::to_vec(self).unwrap_or_default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn subject_includes_task_and_node() {
        let e = StatusEvent::new("t1", Node::Plan, "started");
        assert_eq!(e.subject("swe.af.status"), "swe.af.status.t1.plan");
    }

    #[test]
    fn encodes_json_with_fields() {
        let e = StatusEvent::new("t1", Node::Code, "ok").with_detail("3 files");
        let v: serde_json::Value = serde_json::from_slice(&e.encode()).unwrap();
        assert_eq!(v["task_id"], "t1");
        assert_eq!(v["node"], "code");
        assert_eq!(v["state"], "ok");
        assert_eq!(v["detail"], "3 files");
    }

    #[test]
    fn detail_omitted_when_none() {
        let e = StatusEvent::new("t1", Node::Run, "started");
        let v: serde_json::Value = serde_json::from_slice(&e.encode()).unwrap();
        assert!(v.get("detail").is_none());
    }
}
