//! Thin wrappers over `python3 -m eventd` (append/verify). The audit chain is
//! best-effort during a node and gated by `verify` at the end (exit 0 = ok,
//! 4 = tampered; see `eventd/__main__.py`).

use anyhow::{Result, anyhow};
use tokio::process::Command;

pub fn append_argv(log: &str, payload: &str) -> Vec<String> {
    vec![
        "-m".into(),
        "eventd".into(),
        "append".into(),
        log.into(),
        payload.into(),
    ]
}

pub fn verify_argv(log: &str) -> Vec<String> {
    vec!["-m".into(), "eventd".into(), "verify".into(), log.into()]
}

/// Append one entry. Best-effort: callers may `.ok()` this during a run.
pub async fn append(cwd: &str, log: &str, payload: &str) -> Result<()> {
    let st = Command::new("python3")
        .current_dir(cwd)
        .args(append_argv(log, payload))
        .status()
        .await
        .map_err(|e| anyhow!("eventd append spawn: {e}"))?;
    if !st.success() {
        return Err(anyhow!("eventd append exit {:?}", st.code()));
    }
    Ok(())
}

/// Verify the chain. Exit 0 = ok; anything else = broken/tampered.
pub async fn verify(cwd: &str, log: &str) -> Result<()> {
    let st = Command::new("python3")
        .current_dir(cwd)
        .args(verify_argv(log))
        .status()
        .await
        .map_err(|e| anyhow!("eventd verify spawn: {e}"))?;
    match st.code() {
        Some(0) => Ok(()),
        Some(c) => Err(anyhow!("eventd verify failed exit {c}")),
        None => Err(anyhow!("eventd verify killed by signal")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn append_argv_shape() {
        assert_eq!(
            append_argv("log.jsonl", r#"{"kind":"x"}"#),
            vec!["-m", "eventd", "append", "log.jsonl", r#"{"kind":"x"}"#]
        );
    }

    #[test]
    fn verify_argv_shape() {
        assert_eq!(
            verify_argv("log.jsonl"),
            vec!["-m", "eventd", "verify", "log.jsonl"]
        );
    }
}
