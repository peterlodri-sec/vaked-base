//! Per-task subprocess pipeline, mirroring `.github/workflows/swe-af.yml`:
//! clone -> swe-af plan -> swe-af code -> apply files -> commit/push -> broker PR.
//!
//! The `vaked-swe-af` binary is reused unchanged; it holds no GH write token and
//! prints one JSON object to stdout. The orchestrator is the only GitHub-write
//! actor (the broker step), and only opens a *draft* PR (never auto-merge).

use anyhow::{Context, Result, anyhow};
use serde_json::Value;
use std::collections::HashMap;
use std::path::Path;
use tokio::process::Command;

use crate::config::Config;
use crate::task::Task;

/// Reject paths that escape the checkout or are absolute.
fn safe_rel(path: &str) -> bool {
    !path.is_empty() && !path.contains("..") && !path.starts_with('/')
}

/// Build the environment for one `vaked-swe-af` invocation (`mode` = plan|code).
pub fn swe_af_env(
    cfg: &Config,
    task: &Task,
    mode: &str,
    plan_file: Option<&str>,
) -> HashMap<String, String> {
    let mut e = HashMap::new();
    e.insert("MODE".into(), mode.into());
    e.insert("ISSUE_NUMBER".into(), task.issue_number.to_string());
    e.insert("GITHUB_REPOSITORY".into(), task.repo.clone());
    e.insert("OPENROUTER_BASE_URL".into(), cfg.base_url.clone());
    e.insert("SWE_AF_API_KEY".into(), cfg.api_key.clone());
    e.insert(
        "SWE_AF_MODEL".into(),
        task.plan_model
            .clone()
            .unwrap_or_else(|| cfg.plan_model.clone()),
    );
    if mode == "code" {
        e.insert(
            "SWE_AF_CODE_MODEL".into(),
            task.code_model
                .clone()
                .unwrap_or_else(|| cfg.code_model.clone()),
        );
        if let Some(p) = plan_file {
            e.insert("PLAN_FILE".into(), p.into());
        }
        if let Some(n) = task.max_files {
            e.insert("SWE_AF_MAX_FILES".into(), n.to_string());
        }
    }
    // Read-only token for `gh issue view` inside swe-af (POLA: no write scope here).
    if let Some(t) = &cfg.gh_read_token {
        e.insert("GH_TOKEN".into(), t.clone());
    }
    e
}

/// Write each `{path,content}` verbatim under `root`; return the written paths.
/// Unsafe paths are dropped (defense-in-depth; swe-af already clamps them).
pub fn apply_files(root: &Path, code: &Value) -> Result<Vec<String>> {
    let mut written = Vec::new();
    let files = code
        .get("files")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    for f in files {
        let path = f.get("path").and_then(Value::as_str).unwrap_or_default();
        let content = f.get("content").and_then(Value::as_str).unwrap_or_default();
        if !safe_rel(path) {
            continue;
        }
        let full = root.join(path);
        if let Some(parent) = full.parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(&full, content).with_context(|| format!("write {path}"))?;
        written.push(path.to_string());
    }
    Ok(written)
}

/// Run `vaked-swe-af` in `cwd` with `env`; parse the last stdout JSON object.
async fn run_swe_af(cfg: &Config, cwd: &Path, env: &HashMap<String, String>) -> Result<Value> {
    let mut cmd = Command::new(&cfg.swe_af_bin);
    cmd.current_dir(cwd);
    for (k, v) in env {
        cmd.env(k, v);
    }
    let out = cmd
        .output()
        .await
        .map_err(|e| anyhow!("spawn swe-af: {e}"))?;
    let stdout = String::from_utf8_lossy(&out.stdout);
    let last = stdout
        .lines()
        .rev()
        .find(|l| l.trim_start().starts_with('{'))
        .ok_or_else(|| {
            anyhow!(
                "swe-af produced no JSON (stderr: {})",
                String::from_utf8_lossy(&out.stderr).trim()
            )
        })?;
    serde_json::from_str(last).map_err(|e| anyhow!("swe-af json: {e}"))
}

pub struct Outcome {
    pub pr_url: Option<String>,
    pub note: String,
}

/// Full per-task pipeline. `work` is the (already-created) task scratch dir.
pub async fn run_task(cfg: &Config, task: &Task, work: &Path) -> Result<Outcome> {
    let checkout = work.join("repo");
    let log = work.join("eventd/log.jsonl");
    std::fs::create_dir_all(log.parent().unwrap())?;
    let log_s = log.to_string_lossy().to_string();
    let co_s = checkout.to_string_lossy().to_string();

    // 1. clone (shallow, blobless)
    git_clone(cfg, &task.repo, &checkout).await?;

    // 2. plan
    let plan = run_swe_af(cfg, &checkout, &swe_af_env(cfg, task, "plan", None)).await?;
    let plan_md = plan.get("plan").and_then(Value::as_str).unwrap_or_default();
    let summary = plan
        .get("summary")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let plan_path = work.join("plan.md");
    std::fs::write(&plan_path, plan_md)?;
    crate::eventd::append(
        &co_s,
        &log_s,
        &format!(
            r#"{{"kind":"swe_af.plan","producer":"swe_af","issue":{}}}"#,
            task.issue_number
        ),
    )
    .await
    .ok();

    // 3. code
    let plan_path_s = plan_path.to_string_lossy().to_string();
    let code = run_swe_af(
        cfg,
        &checkout,
        &swe_af_env(cfg, task, "code", Some(plan_path_s.as_str())),
    )
    .await?;
    let written = apply_files(&checkout, &code)?;
    crate::eventd::append(
        &co_s,
        &log_s,
        &format!(
            r#"{{"kind":"swe_af.code","producer":"swe_af","issue":{},"files":{}}}"#,
            task.issue_number,
            written.len()
        ),
    )
    .await
    .ok();
    if written.is_empty() {
        return Ok(Outcome {
            pr_url: None,
            note: "no files produced".into(),
        });
    }

    // 4. commit + push branch
    let branch = task.branch();
    let commit_msg = code
        .get("commit_message")
        .and_then(Value::as_str)
        .filter(|s| !s.trim().is_empty())
        .unwrap_or("chore(swe_af): apply agent-generated change");
    git_commit_push(&checkout, &branch, commit_msg, &written).await?;

    // 5. broker: open a DRAFT PR (the only GitHub write; never auto-merge)
    let title = if summary.trim().is_empty() {
        format!("swe_af: resolve #{}", task.issue_number)
    } else {
        format!("swe_af: {summary}")
    };
    let pr_url = gh_pr_create(cfg, &checkout, &task.repo, &branch, &title, &plan_path).await?;
    crate::eventd::append(
        &co_s,
        &log_s,
        &format!(
            r#"{{"kind":"swe_af.publish_draft","producer":"swe_af","issue":{}}}"#,
            task.issue_number
        ),
    )
    .await
    .ok();

    // 6. verify the audit chain (non-fatal)
    if let Err(e) = crate::eventd::verify(&co_s, &log_s).await {
        tracing::warn!(%e, "eventd verify");
    }

    Ok(Outcome {
        pr_url: Some(pr_url),
        note: code
            .get("notes")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
    })
}

async fn git_clone(cfg: &Config, repo: &str, dest: &Path) -> Result<()> {
    let token = cfg
        .gh_write_token
        .as_deref()
        .or(cfg.gh_read_token.as_deref());
    let url = match token {
        Some(t) => format!("https://x-access-token:{t}@github.com/{repo}.git"),
        None => format!("https://github.com/{repo}.git"),
    };
    let dest_s = dest.to_string_lossy().to_string();
    run(
        "git",
        &[
            "clone",
            "--filter=blob:none",
            "--no-tags",
            url.as_str(),
            dest_s.as_str(),
        ],
        None,
    )
    .await
}

async fn git_commit_push(checkout: &Path, branch: &str, msg: &str, files: &[String]) -> Result<()> {
    let c = checkout.to_string_lossy().to_string();
    run(
        "git",
        &["-C", c.as_str(), "config", "user.name", "vaked-swe-af[bot]"],
        None,
    )
    .await?;
    run(
        "git",
        &[
            "-C",
            c.as_str(),
            "config",
            "user.email",
            "swe-af@users.noreply.github.com",
        ],
        None,
    )
    .await?;
    run("git", &["-C", c.as_str(), "checkout", "-b", branch], None).await?;
    for f in files {
        run("git", &["-C", c.as_str(), "add", "--", f.as_str()], None).await?;
    }
    run("git", &["-C", c.as_str(), "commit", "-m", msg], None).await?;
    run(
        "git",
        &[
            "-C",
            c.as_str(),
            "push",
            "-u",
            "origin",
            branch,
            "--force-with-lease",
        ],
        None,
    )
    .await
}

async fn gh_pr_create(
    cfg: &Config,
    checkout: &Path,
    repo: &str,
    branch: &str,
    title: &str,
    body_file: &Path,
) -> Result<String> {
    let body_s = body_file.to_string_lossy().to_string();
    let mut cmd = Command::new("gh");
    cmd.current_dir(checkout).args([
        "pr",
        "create",
        "--repo",
        repo,
        "--draft",
        "--head",
        branch,
        "--title",
        title,
        "--body-file",
        body_s.as_str(),
    ]);
    if let Some(t) = &cfg.gh_write_token {
        cmd.env("GH_TOKEN", t);
    }
    let out = cmd
        .output()
        .await
        .map_err(|e| anyhow!("gh pr create spawn: {e}"))?;
    if !out.status.success() {
        return Err(anyhow!(
            "gh pr create: {}",
            String::from_utf8_lossy(&out.stderr).trim()
        ));
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

async fn run(bin: &str, args: &[&str], env: Option<(&str, &str)>) -> Result<()> {
    let mut cmd = Command::new(bin);
    cmd.args(args);
    if let Some((k, v)) = env {
        cmd.env(k, v);
    }
    let out = cmd
        .output()
        .await
        .map_err(|e| anyhow!("spawn {bin}: {e}"))?;
    if !out.status.success() {
        return Err(anyhow!(
            "{bin} {:?} failed: {}",
            args,
            String::from_utf8_lossy(&out.stderr).trim()
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;
    use crate::task::Task;
    use std::collections::HashMap;

    fn cfg() -> Config {
        let mut m = HashMap::new();
        m.insert("NATS_URL".into(), "nats://x:4222".into());
        Config::from_map(&m).unwrap()
    }
    fn task() -> Task {
        Task {
            task_id: "t1".into(),
            repo: "a/b".into(),
            issue_number: 7,
            plan_model: None,
            code_model: Some("zzz/coder".into()),
            max_files: Some(5),
        }
    }

    #[test]
    fn plan_env_routes_to_aperture() {
        let c = cfg();
        let env = swe_af_env(&c, &task(), "plan", None);
        assert_eq!(env.get("MODE").unwrap(), "plan");
        assert_eq!(env.get("ISSUE_NUMBER").unwrap(), "7");
        assert_eq!(env.get("GITHUB_REPOSITORY").unwrap(), "a/b");
        assert_eq!(env.get("OPENROUTER_BASE_URL").unwrap(), &c.base_url);
        assert_eq!(
            env.get("SWE_AF_MODEL").unwrap(),
            "deepseek/deepseek-v4-flash"
        );
        assert!(!env.contains_key("SWE_AF_CODE_MODEL"));
    }

    #[test]
    fn code_env_uses_task_code_model_and_plan_file() {
        let env = swe_af_env(&cfg(), &task(), "code", Some("/w/plan.md"));
        assert_eq!(env.get("MODE").unwrap(), "code");
        assert_eq!(env.get("SWE_AF_CODE_MODEL").unwrap(), "zzz/coder");
        assert_eq!(env.get("PLAN_FILE").unwrap(), "/w/plan.md");
        assert_eq!(env.get("SWE_AF_MAX_FILES").unwrap(), "5");
    }

    #[test]
    fn apply_writes_full_files_rejects_unsafe() {
        let d = tempfile::tempdir().unwrap();
        let code = serde_json::json!({
            "files":[
                {"path":"src/x.rs","content":"fn x(){}"},
                {"path":"../escape","content":"no"},
                {"path":"/abs","content":"no"}
            ],
            "commit_message":"feat: x","notes":""
        });
        let written = apply_files(d.path(), &code).unwrap();
        assert_eq!(written, vec!["src/x.rs".to_string()]);
        assert_eq!(
            std::fs::read_to_string(d.path().join("src/x.rs")).unwrap(),
            "fn x(){}"
        );
    }
}
