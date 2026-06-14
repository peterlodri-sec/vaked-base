# swe-af fan-out batch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Rust daemon that drains a NATS JetStream work-queue and runs the existing `vaked-swe-af` agent (plan → code → publish) per task inside disk/cgroup-bounded scratch, routing model calls through the tailnet Aperture gateway, opening one draft PR per task with eventd audit and live `swe.af.status.*` events.

**Architecture:** A new workspace-excluded crate `vaked-agents/ci/swe-af-orchestrator/` with two binaries: `swe-af-orchestrator` (the pool daemon) and `swe-af-enqueue` (the producer CLI). The daemon is a tokio + `async-nats` JetStream **durable pull consumer** with a `Semaphore(K)` worker pool; each task is a subprocess pipeline mirroring `.github/workflows/swe-af.yml` (git clone → `vaked-swe-af MODE=plan` → `MODE=code` → apply/commit/push → `gh pr create --draft` broker → eventd verify). Isolation = a systemd slice (aggregate `MemoryMax`/`CPUQuota`) + per-task scratch dir under a disk cap + a free-space guard that pauses message intake. The `vaked-swe-af` binary is **reused unchanged**.

**Tech Stack:** Rust 2021, tokio, `async-nats` (JetStream), serde/serde_json, anyhow, tracing, uuid; subprocess: `git`, `gh`, `vaked-swe-af`, `bwrap`, `python3 -m eventd`. Deploy: systemd unit on bench-node (Ubuntu).

**Scope (v1):** issue-based tasks only (matches `vaked-swe-af`'s required `ISSUE_NUMBER`). Out: freeform `prompt` tasks, GCP/ccx33 workers, autoscaling — phase 2.

**Reference docs:** `docs/superpowers/specs/2026-06-14-swe-af-fanout-batch-design.md`; the DAG to mirror: `.github/workflows/swe-af.yml`; the agent it drives: `vaked-agents/ci/swe-af/src/main.rs` + `README.md`; eventd CLI: `eventd/__main__.py` (append/verify, exit codes 0 ok / 4 tampered).

**Environment contract (orchestrator reads from env / systemd EnvironmentFile):**
- `NATS_URL` (e.g. `nats://100.73.72.35:4222`), optional `NATS_CREDS`.
- `SWE_AF_STREAM` (default `SWE_AF_TASKS`), `SWE_AF_SUBJECT` (default `swe.af.tasks`), `SWE_AF_CONSUMER` (default `swe-af-workers`), `SWE_AF_STATUS_PREFIX` (default `swe.af.status`).
- `SWE_AF_POOL` (default `6`), `SWE_AF_SCRATCH` (default `/var/lib/swe-af/scratch`), `SWE_AF_MIN_FREE_GB` (default `10`), `SWE_AF_SCRATCH_CAP_GB` (default `20`).
- `SWE_AF_BIN` (default `/usr/local/bin/vaked-swe-af`), `SWE_AF_BWRAP` (`1` to wrap, default `0` in v1).
- `OPENROUTER_BASE_URL` (Aperture: `https://nixai-base.tail2870dc.ts.net/aperture/v1`), `SWE_AF_API_KEY` (placeholder `tailscale-identity`).
- `GH_TOKEN` (read scope, passed to `vaked-swe-af` for `gh issue view`), `SWE_AF_GH_WRITE_TOKEN` (write scope, used only for the broker step).
- `SWE_AF_PLAN_MODEL` (default `deepseek/deepseek-v4-flash`), `SWE_AF_CODE_MODEL` (default `openai/gpt-5.3-codex`).
- `EVENTD_LOG` (default `<scratch>/<task_id>/eventd/log.jsonl` per task).

---

## File structure

| File | Responsibility |
|---|---|
| `vaked-agents/ci/swe-af-orchestrator/Cargo.toml` | crate + 2 bins + deps |
| `vaked-agents/ci/swe-af-orchestrator/build.rs` | stamp `GIT_SHA` (mirror swe-af) |
| `src/lib.rs` | re-export modules for tests |
| `src/task.rs` | `Task` schema, parse + validate, branch-name derivation |
| `src/config.rs` | `Config::from_env`, all knobs above |
| `src/status.rs` | `StatusEvent` schema + subject builder + JSON encode |
| `src/disk.rs` | free-space probe + scratch dir-size accounting + guard decision |
| `src/eventd.rs` | `append`/`verify` wrappers over `python3 -m eventd` |
| `src/lifecycle.rs` | per-task subprocess pipeline (clone→plan→code→apply→push→broker) |
| `src/nats.rs` | JetStream connect, ensure stream/consumer, pull loop |
| `src/bin/orchestrator.rs` | wire pool: pull → semaphore → lifecycle → ack/term; signals |
| `src/bin/enqueue.rs` | producer CLI: publish a `Task` to the subject |
| `deploy/swe-af-orchestrator.service` | systemd unit + slice caps (bench-node) |
| `deploy/swe-af.slice` | systemd slice (MemoryMax/CPUQuota) |
| `deploy/README.md` | post-P1 runbook (tailnet, gh, binary, Aperture grant, disk reclaim) |

---

## Task 1: Crate skeleton + CI build target

**Files:**
- Create: `vaked-agents/ci/swe-af-orchestrator/Cargo.toml`
- Create: `vaked-agents/ci/swe-af-orchestrator/build.rs`
- Create: `vaked-agents/ci/swe-af-orchestrator/src/lib.rs`
- Create: `vaked-agents/ci/swe-af-orchestrator/src/bin/orchestrator.rs` (stub)
- Create: `vaked-agents/ci/swe-af-orchestrator/.gitignore`

- [ ] **Step 1: Write `Cargo.toml`**

```toml
[package]
name = "vaked-swe-af-orchestrator"
version = "0.1.0"
edition = "2021"
publish = false

[[bin]]
name = "swe-af-orchestrator"
path = "src/bin/orchestrator.rs"

[[bin]]
name = "swe-af-enqueue"
path = "src/bin/enqueue.rs"

[lib]
path = "src/lib.rs"

[dependencies]
tokio = { version = "1", features = ["rt-multi-thread", "macros", "process", "signal", "fs", "sync", "time"] }
async-nats = "0.38"
futures = "0.3"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
anyhow = "1"
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
uuid = { version = "1", features = ["v4"] }

[dev-dependencies]
tempfile = "3"
```

- [ ] **Step 2: Write `build.rs`** (mirror swe-af's GIT_SHA stamp; the bins reference it)

```rust
use std::process::Command;
fn main() {
    let sha = Command::new("git")
        .args(["rev-parse", "--short", "HEAD"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_else(|| "unknown".into());
    println!("cargo:rustc-env=GIT_SHA={sha}");
    println!("cargo:rerun-if-changed=.git/HEAD");
}
```

- [ ] **Step 3: Write `src/lib.rs`** (module wiring)

```rust
pub mod config;
pub mod disk;
pub mod eventd;
pub mod lifecycle;
pub mod nats;
pub mod status;
pub mod task;
```

- [ ] **Step 4: Write `.gitignore`** with `target/`

- [ ] **Step 5: Stub `src/bin/orchestrator.rs`** so it compiles

```rust
fn main() {
    println!("swe-af-orchestrator {}+{}", env!("CARGO_PKG_VERSION"), env!("GIT_SHA"));
}
```

- [ ] **Step 6: Stub `src/bin/enqueue.rs`** identically (rename string to `swe-af-enqueue`).

- [ ] **Step 7: Build** — Run: `cargo build --manifest-path vaked-agents/ci/swe-af-orchestrator/Cargo.toml` — Expected: compiles (the module files don't exist yet, so temporarily comment out `src/lib.rs` module lines OR create empty module files in this task). Create empty `src/{config,disk,eventd,lifecycle,nats,status,task}.rs` files to satisfy `lib.rs`.

- [ ] **Step 8: Commit** — `git add vaked-agents/ci/swe-af-orchestrator && git commit -m "feat(swe-af-orchestrator): crate skeleton + 2 bins"`

---

## Task 2: Task schema + branch derivation (`task.rs`)

**Files:**
- Modify: `src/task.rs`

- [ ] **Step 1: Write failing tests** (append to `src/task.rs`)

```rust
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
        let j = r#"{"task_id":"t1","repo":"../evil","issue_number":1}"#;
        assert!(Task::from_json(j.as_bytes()).is_err());
    }

    #[test]
    fn rejects_zero_issue() {
        let j = r#"{"task_id":"t1","repo":"a/b","issue_number":0}"#;
        assert!(Task::from_json(j.as_bytes()).is_err());
    }

    #[test]
    fn branch_name_is_deterministic() {
        let t = Task { task_id: "t1".into(), repo: "a/b".into(), issue_number: 42,
            plan_model: None, code_model: None, max_files: None };
        assert_eq!(t.branch(), "swe-af/issue-42");
    }
}
```

- [ ] **Step 2: Run tests, verify fail** — Run: `cargo test -p vaked-swe-af-orchestrator task:: ` — Expected: FAIL (no `Task`).

- [ ] **Step 3: Implement** (prepend to `src/task.rs`)

```rust
use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};

/// A unit of work: run swe_af against one GitHub issue.
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

fn valid_repo(repo: &str) -> bool {
    let mut parts = repo.split('/');
    let (Some(owner), Some(name), None) = (parts.next(), parts.next(), parts.next()) else {
        return false;
    };
    let ok = |s: &str| {
        !s.is_empty()
            && s.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'))
            && !s.contains("..")
    };
    ok(owner) && ok(name)
}

impl Task {
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

    pub fn branch(&self) -> String {
        format!("swe-af/issue-{}", self.issue_number)
    }
}
```

- [ ] **Step 4: Run tests, verify pass** — Run: `cargo test -p vaked-swe-af-orchestrator task::` — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(orchestrator): Task schema + validation + branch derivation"`

---

## Task 3: Status events (`status.rs`)

**Files:**
- Modify: `src/status.rs`

- [ ] **Step 1: Write failing tests**

```rust
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
}
```

- [ ] **Step 2: Run, verify fail** — `cargo test -p vaked-swe-af-orchestrator status::` → FAIL.

- [ ] **Step 3: Implement**

```rust
use serde::Serialize;

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Node { Run, Plan, Code, Apply, Publish, Review, Done, Error }

impl Node {
    fn as_str(self) -> &'static str {
        match self {
            Node::Run => "run", Node::Plan => "plan", Node::Code => "code",
            Node::Apply => "apply", Node::Publish => "publish", Node::Review => "review",
            Node::Done => "done", Node::Error => "error",
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
        Self { task_id: task_id.to_string(), node, state: state.to_string(), detail: None }
    }
    pub fn with_detail(mut self, d: &str) -> Self { self.detail = Some(d.to_string()); self }
    pub fn subject(&self, prefix: &str) -> String {
        format!("{prefix}.{}.{}", self.task_id, self.node.as_str())
    }
    pub fn encode(&self) -> Vec<u8> {
        serde_json::to_vec(self).unwrap_or_default()
    }
}
```

- [ ] **Step 4: Run, verify pass** → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(orchestrator): status event schema + subject builder"`

---

## Task 4: Disk guard (`disk.rs`)

**Files:**
- Modify: `src/disk.rs`

- [ ] **Step 1: Write failing tests**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn guard_pauses_below_floor() {
        // free below floor -> pause
        assert!(!Guard { min_free_bytes: 10, scratch_cap_bytes: 100 }
            .admits(/*free*/ 5, /*used*/ 0));
        // free ok but scratch over cap -> pause
        assert!(!Guard { min_free_bytes: 10, scratch_cap_bytes: 100 }
            .admits(50, 100));
        // both ok -> admit
        assert!(Guard { min_free_bytes: 10, scratch_cap_bytes: 100 }
            .admits(50, 40));
    }
    #[test]
    fn dir_size_counts_files() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("a"), vec![0u8; 1234]).unwrap();
        assert!(dir_size_bytes(d.path()) >= 1234);
    }
}
```

- [ ] **Step 2: Run, verify fail** → FAIL.

- [ ] **Step 3: Implement** (`statvfs` via `nix` is avoidable — shell out to `df`/walk dir to keep deps minimal)

```rust
use std::path::Path;

#[derive(Debug, Clone, Copy)]
pub struct Guard {
    pub min_free_bytes: u64,
    pub scratch_cap_bytes: u64,
}

impl Guard {
    /// Admit a new task only if free space is above the floor AND scratch is under cap.
    pub fn admits(&self, free_bytes: u64, scratch_used_bytes: u64) -> bool {
        free_bytes >= self.min_free_bytes && scratch_used_bytes < self.scratch_cap_bytes
    }
}

/// Recursively sum regular-file sizes under `root` (best-effort).
pub fn dir_size_bytes(root: &Path) -> u64 {
    fn walk(p: &Path, acc: &mut u64) {
        let Ok(rd) = std::fs::read_dir(p) else { return };
        for e in rd.flatten() {
            let path = e.path();
            match e.file_type() {
                Ok(ft) if ft.is_dir() => walk(&path, acc),
                Ok(ft) if ft.is_file() => {
                    if let Ok(m) = e.metadata() { *acc += m.len(); }
                }
                _ => {}
            }
        }
    }
    let mut acc = 0;
    walk(root, &mut acc);
    acc
}

/// Free bytes on the filesystem containing `path`, via `df -kP` (portable).
pub fn free_bytes(path: &Path) -> std::io::Result<u64> {
    let out = std::process::Command::new("df").arg("-kP").arg(path).output()?;
    let s = String::from_utf8_lossy(&out.stdout);
    // line 2, column 4 (Available) is in 1K blocks
    let avail_k: u64 = s.lines().nth(1)
        .and_then(|l| l.split_whitespace().nth(3))
        .and_then(|v| v.parse().ok())
        .unwrap_or(0);
    Ok(avail_k * 1024)
}
```

- [ ] **Step 4: Run, verify pass** → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(orchestrator): disk free/usage guard"`

---

## Task 5: Config (`config.rs`)

**Files:**
- Modify: `src/config.rs`

- [ ] **Step 1: Write failing tests** (defaults + GB→bytes conversion; tests set/clear env then call `from_env`; run serially with `#[serial]`? avoid extra deps — instead test a pure `Config::from_map(HashMap)` helper)

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;
    fn base() -> HashMap<String,String> {
        let mut m = HashMap::new();
        m.insert("NATS_URL".into(), "nats://x:4222".into());
        m
    }
    #[test]
    fn defaults_apply() {
        let c = Config::from_map(&base()).unwrap();
        assert_eq!(c.pool, 6);
        assert_eq!(c.subject, "swe.af.tasks");
        assert_eq!(c.min_free_bytes, 10 * 1024 * 1024 * 1024);
        assert_eq!(c.plan_model, "deepseek/deepseek-v4-flash");
    }
    #[test]
    fn requires_nats_url() {
        assert!(Config::from_map(&HashMap::new()).is_err());
    }
    #[test]
    fn overrides_parse() {
        let mut m = base();
        m.insert("SWE_AF_POOL".into(), "12".into());
        m.insert("SWE_AF_MIN_FREE_GB".into(), "5".into());
        let c = Config::from_map(&m).unwrap();
        assert_eq!(c.pool, 12);
        assert_eq!(c.min_free_bytes, 5 * 1024 * 1024 * 1024);
    }
}
```

- [ ] **Step 2: Run, verify fail** → FAIL.

- [ ] **Step 3: Implement** (env reads delegate to `from_map(&std::env::vars().collect())`)

```rust
use anyhow::{anyhow, Result};
use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct Config {
    pub nats_url: String,
    pub nats_creds: Option<String>,
    pub stream: String,
    pub subject: String,
    pub consumer: String,
    pub status_prefix: String,
    pub pool: usize,
    pub scratch: String,
    pub min_free_bytes: u64,
    pub scratch_cap_bytes: u64,
    pub swe_af_bin: String,
    pub bwrap: bool,
    pub base_url: String,
    pub api_key: String,
    pub gh_read_token: Option<String>,
    pub gh_write_token: Option<String>,
    pub plan_model: String,
    pub code_model: String,
}

fn get<'a>(m: &'a HashMap<String,String>, k: &str) -> Option<&'a str> {
    m.get(k).map(|s| s.as_str()).filter(|s| !s.is_empty())
}
fn or(m: &HashMap<String,String>, k: &str, d: &str) -> String {
    get(m, k).unwrap_or(d).to_string()
}
fn gb(m: &HashMap<String,String>, k: &str, d: u64) -> u64 {
    get(m, k).and_then(|s| s.parse::<u64>().ok()).unwrap_or(d) * 1024 * 1024 * 1024
}

impl Config {
    pub fn from_env() -> Result<Self> {
        Self::from_map(&std::env::vars().collect())
    }
    pub fn from_map(m: &HashMap<String,String>) -> Result<Self> {
        let nats_url = get(m, "NATS_URL").ok_or_else(|| anyhow!("NATS_URL required"))?.to_string();
        Ok(Config {
            nats_url,
            nats_creds: get(m, "NATS_CREDS").map(String::from),
            stream: or(m, "SWE_AF_STREAM", "SWE_AF_TASKS"),
            subject: or(m, "SWE_AF_SUBJECT", "swe.af.tasks"),
            consumer: or(m, "SWE_AF_CONSUMER", "swe-af-workers"),
            status_prefix: or(m, "SWE_AF_STATUS_PREFIX", "swe.af.status"),
            pool: get(m, "SWE_AF_POOL").and_then(|s| s.parse().ok()).unwrap_or(6),
            scratch: or(m, "SWE_AF_SCRATCH", "/var/lib/swe-af/scratch"),
            min_free_bytes: gb(m, "SWE_AF_MIN_FREE_GB", 10),
            scratch_cap_bytes: gb(m, "SWE_AF_SCRATCH_CAP_GB", 20),
            swe_af_bin: or(m, "SWE_AF_BIN", "/usr/local/bin/vaked-swe-af"),
            bwrap: get(m, "SWE_AF_BWRAP") == Some("1"),
            base_url: or(m, "OPENROUTER_BASE_URL", "https://nixai-base.tail2870dc.ts.net/aperture/v1"),
            api_key: or(m, "SWE_AF_API_KEY", "tailscale-identity"),
            gh_read_token: get(m, "GH_TOKEN").map(String::from),
            gh_write_token: get(m, "SWE_AF_GH_WRITE_TOKEN").map(String::from),
            plan_model: or(m, "SWE_AF_PLAN_MODEL", "deepseek/deepseek-v4-flash"),
            code_model: or(m, "SWE_AF_CODE_MODEL", "openai/gpt-5.3-codex"),
        })
    }
}
```

- [ ] **Step 4: Run, verify pass** → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(orchestrator): env/map config with defaults"`

---

## Task 6: eventd wrappers (`eventd.rs`)

**Files:**
- Modify: `src/eventd.rs`

- [ ] **Step 1: Write failing test** (build the argv, don't shell out in unit test)

```rust
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn append_argv_shape() {
        let a = append_argv("log.jsonl", r#"{"kind":"x"}"#);
        assert_eq!(a, vec!["-m","eventd","append","log.jsonl",r#"{"kind":"x"}"#]);
    }
    #[test]
    fn verify_argv_shape() {
        assert_eq!(verify_argv("log.jsonl"), vec!["-m","eventd","verify","log.jsonl"]);
    }
}
```

- [ ] **Step 2: Run, verify fail** → FAIL.

- [ ] **Step 3: Implement** (argv builders are pure + testable; `run_*` use tokio in the binary)

```rust
use anyhow::{anyhow, Result};
use tokio::process::Command;

pub fn append_argv(log: &str, payload: &str) -> Vec<String> {
    vec!["-m".into(), "eventd".into(), "append".into(), log.into(), payload.into()]
}
pub fn verify_argv(log: &str) -> Vec<String> {
    vec!["-m".into(), "eventd".into(), "verify".into(), log.into()]
}

/// Append one entry; non-fatal (audit is best-effort during a node, gated at end).
pub async fn append(cwd: &str, log: &str, payload: &str) -> Result<()> {
    let st = Command::new("python3").current_dir(cwd).args(append_argv(log, payload))
        .status().await.map_err(|e| anyhow!("eventd append spawn: {e}"))?;
    if !st.success() { return Err(anyhow!("eventd append exit {:?}", st.code())); }
    Ok(())
}

/// Verify the chain; exit 0 = ok, 4 = tampered (see eventd/__main__.py).
pub async fn verify(cwd: &str, log: &str) -> Result<()> {
    let st = Command::new("python3").current_dir(cwd).args(verify_argv(log))
        .status().await.map_err(|e| anyhow!("eventd verify spawn: {e}"))?;
    match st.code() {
        Some(0) => Ok(()),
        Some(c) => Err(anyhow!("eventd verify failed exit {c}")),
        None => Err(anyhow!("eventd verify killed")),
    }
}
```

- [ ] **Step 4: Run, verify pass** → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(orchestrator): eventd append/verify wrappers"`

---

## Task 7: Lifecycle pipeline (`lifecycle.rs`)

This mirrors `.github/workflows/swe-af.yml` as subprocess calls in a per-task scratch checkout. It is IO-heavy; unit-test the pure helpers, integration-test the swe-af invocation with `DRY_RUN=1`.

**Files:**
- Modify: `src/lifecycle.rs`

- [ ] **Step 1: Write failing tests** (pure helpers: env assembly + swe-af argv + apply-files writer)

```rust
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
        Task { task_id: "t1".into(), repo: "a/b".into(), issue_number: 7,
            plan_model: None, code_model: Some("zzz/coder".into()), max_files: Some(5) }
    }

    #[test]
    fn plan_env_routes_to_aperture() {
        let env = swe_af_env(&cfg(), &task(), "plan", None);
        assert_eq!(env.get("MODE").unwrap(), "plan");
        assert_eq!(env.get("ISSUE_NUMBER").unwrap(), "7");
        assert_eq!(env.get("GITHUB_REPOSITORY").unwrap(), "a/b");
        assert_eq!(env.get("OPENROUTER_BASE_URL").unwrap(), &cfg().base_url);
        assert_eq!(env.get("SWE_AF_MODEL").unwrap(), "deepseek/deepseek-v4-flash");
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
            "files":[{"path":"src/x.rs","content":"fn x(){}"},
                     {"path":"../escape","content":"no"}],
            "commit_message":"feat: x","notes":""
        });
        let written = apply_files(d.path(), &code).unwrap();
        assert_eq!(written, vec!["src/x.rs".to_string()]); // escape dropped
        assert_eq!(std::fs::read_to_string(d.path().join("src/x.rs")).unwrap(), "fn x(){}");
    }
}
```

- [ ] **Step 2: Run, verify fail** → FAIL.

- [ ] **Step 3: Implement the pure helpers + the pipeline**

```rust
use anyhow::{anyhow, Context, Result};
use serde_json::Value;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use tokio::process::Command;

use crate::config::Config;
use crate::task::Task;

fn safe_rel(path: &str) -> bool {
    !path.is_empty() && !path.contains("..") && !path.starts_with('/')
}

/// Env for one `vaked-swe-af` invocation (mode = "plan"|"code").
pub fn swe_af_env(cfg: &Config, task: &Task, mode: &str, plan_file: Option<&str>) -> HashMap<String, String> {
    let mut e = HashMap::new();
    e.insert("MODE".into(), mode.into());
    e.insert("ISSUE_NUMBER".into(), task.issue_number.to_string());
    e.insert("GITHUB_REPOSITORY".into(), task.repo.clone());
    e.insert("OPENROUTER_BASE_URL".into(), cfg.base_url.clone());
    e.insert("SWE_AF_API_KEY".into(), cfg.api_key.clone());
    e.insert("SWE_AF_MODEL".into(), task.plan_model.clone().unwrap_or_else(|| cfg.plan_model.clone()));
    if mode == "code" {
        e.insert("SWE_AF_CODE_MODEL".into(), task.code_model.clone().unwrap_or_else(|| cfg.code_model.clone()));
        if let Some(p) = plan_file { e.insert("PLAN_FILE".into(), p.into()); }
        if let Some(n) = task.max_files { e.insert("SWE_AF_MAX_FILES".into(), n.to_string()); }
    }
    if let Some(t) = &cfg.gh_read_token { e.insert("GH_TOKEN".into(), t.clone()); }
    e
}

/// Write each `{path,content}` verbatim under `root`; returns the written paths.
pub fn apply_files(root: &Path, code: &Value) -> Result<Vec<String>> {
    let mut written = Vec::new();
    let files = code.get("files").and_then(Value::as_array).cloned().unwrap_or_default();
    for f in files {
        let path = f.get("path").and_then(Value::as_str).unwrap_or_default();
        let content = f.get("content").and_then(Value::as_str).unwrap_or_default();
        if !safe_rel(path) { continue; }
        let full = root.join(path);
        if let Some(parent) = full.parent() { std::fs::create_dir_all(parent)?; }
        std::fs::write(&full, content).with_context(|| format!("write {path}"))?;
        written.push(path.to_string());
    }
    Ok(written)
}

/// Run `vaked-swe-af` in `cwd` with `env`, capture stdout JSON.
async fn run_swe_af(cfg: &Config, cwd: &Path, env: &HashMap<String,String>) -> Result<Value> {
    let mut cmd = Command::new(&cfg.swe_af_bin);
    cmd.current_dir(cwd);
    for (k, v) in env { cmd.env(k, v); }
    let out = cmd.output().await.map_err(|e| anyhow!("spawn swe-af: {e}"))?;
    let stdout = String::from_utf8_lossy(&out.stdout);
    let last = stdout.lines().rev().find(|l| l.trim_start().starts_with('{'))
        .ok_or_else(|| anyhow!("swe-af produced no JSON: {}", String::from_utf8_lossy(&out.stderr)))?;
    serde_json::from_str(last).map_err(|e| anyhow!("swe-af json: {e}"))
}

pub struct Outcome { pub pr_url: Option<String>, pub note: String }

/// Full per-task pipeline. `work` is the task scratch dir (already created).
pub async fn run_task(cfg: &Config, task: &Task, work: &Path) -> Result<Outcome> {
    let checkout = work.join("repo");
    let log = work.join("eventd/log.jsonl");
    std::fs::create_dir_all(log.parent().unwrap())?;
    let log_s = log.to_string_lossy().to_string();
    let co_s = checkout.to_string_lossy().to_string();

    // 1. clone (shallow, blobless) using the write token for push later
    git_clone(cfg, &task.repo, &checkout).await?;

    // 2. plan
    let plan = run_swe_af(cfg, &checkout, &swe_af_env(cfg, task, "plan", None)).await?;
    let plan_md = plan.get("plan").and_then(Value::as_str).unwrap_or_default();
    let summary = plan.get("summary").and_then(Value::as_str).unwrap_or_default();
    std::fs::write(work.join("plan.md"), plan_md)?;
    crate::eventd::append(&co_s, &log_s,
        &format!(r#"{{"kind":"swe_af.plan","producer":"swe_af","issue":{}}}"#, task.issue_number)).await.ok();

    // 3. code
    let code = run_swe_af(cfg, &checkout,
        &swe_af_env(cfg, task, "code", Some(work.join("plan.md").to_str().unwrap()))).await?;
    let written = apply_files(&checkout, &code)?;
    crate::eventd::append(&co_s, &log_s,
        &format!(r#"{{"kind":"swe_af.code","producer":"swe_af","issue":{},"files":{}}}"#,
            task.issue_number, written.len())).await.ok();
    if written.is_empty() {
        return Ok(Outcome { pr_url: None, note: "no files produced".into() });
    }

    // 4. commit + push branch
    let branch = task.branch();
    git_commit_push(&checkout, &branch,
        code.get("commit_message").and_then(Value::as_str).unwrap_or("chore(swe_af): change"),
        &written).await?;

    // 5. broker: open draft PR (write token only here)
    let title = if summary.is_empty() { format!("swe_af: resolve #{}", task.issue_number) }
                else { format!("swe_af: {summary}") };
    let pr_url = gh_pr_create(cfg, &checkout, &task.repo, &branch, &title, &work.join("plan.md")).await?;
    crate::eventd::append(&co_s, &log_s,
        &format!(r#"{{"kind":"swe_af.publish_draft","producer":"swe_af","issue":{}}}"#, task.issue_number)).await.ok();

    // 6. verify chain (non-fatal -> log)
    if let Err(e) = crate::eventd::verify(&co_s, &log_s).await { tracing::warn!(%e, "eventd verify"); }

    Ok(Outcome { pr_url: Some(pr_url), note: code.get("notes").and_then(Value::as_str).unwrap_or("").into() })
}

async fn git_clone(cfg: &Config, repo: &str, dest: &Path) -> Result<()> {
    let token = cfg.gh_write_token.as_deref().or(cfg.gh_read_token.as_deref());
    let url = match token {
        Some(t) => format!("https://x-access-token:{t}@github.com/{repo}.git"),
        None => format!("https://github.com/{repo}.git"),
    };
    run("git", &["clone", "--filter=blob:none", "--no-tags", &url, dest.to_str().unwrap()], None).await
}

async fn git_commit_push(checkout: &Path, branch: &str, msg: &str, files: &[String]) -> Result<()> {
    run("git", &["-C", checkout.to_str().unwrap(), "config", "user.name", "vaked-swe-af[bot]"], None).await?;
    run("git", &["-C", checkout.to_str().unwrap(), "config", "user.email", "swe-af@users.noreply.github.com"], None).await?;
    run("git", &["-C", checkout.to_str().unwrap(), "checkout", "-b", branch], None).await?;
    for f in files {
        run("git", &["-C", checkout.to_str().unwrap(), "add", "--", f], None).await?;
    }
    run("git", &["-C", checkout.to_str().unwrap(), "commit", "-m", msg], None).await?;
    run("git", &["-C", checkout.to_str().unwrap(), "push", "-u", "origin", branch, "--force-with-lease"], None).await
}

async fn gh_pr_create(cfg: &Config, checkout: &Path, repo: &str, branch: &str, title: &str, body_file: &Path) -> Result<String> {
    let env = cfg.gh_write_token.as_ref().map(|t| ("GH_TOKEN", t.as_str()));
    let out = {
        let mut cmd = Command::new("gh");
        cmd.current_dir(checkout)
            .args(["pr", "create", "--repo", repo, "--draft", "--head", branch, "--title", title,
                   "--body-file", body_file.to_str().unwrap()]);
        if let Some((k, v)) = env { cmd.env(k, v); }
        cmd.output().await.map_err(|e| anyhow!("gh pr create spawn: {e}"))?
    };
    if !out.status.success() {
        return Err(anyhow!("gh pr create: {}", String::from_utf8_lossy(&out.stderr)));
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

async fn run(bin: &str, args: &[&str], env: Option<(&str,&str)>) -> Result<()> {
    let mut cmd = Command::new(bin);
    cmd.args(args);
    if let Some((k,v)) = env { cmd.env(k, v); }
    let out = cmd.output().await.map_err(|e| anyhow!("spawn {bin}: {e}"))?;
    if !out.status.success() {
        return Err(anyhow!("{bin} {:?} failed: {}", args, String::from_utf8_lossy(&out.stderr)));
    }
    Ok(())
}

#[allow(unused_imports)]
use std::convert::identity as _keep_pathbuf; // keep PathBuf import if unused in some builds
const _: fn() -> PathBuf = PathBuf::new;
```

- [ ] **Step 4: Run unit tests, verify pass** — `cargo test -p vaked-swe-af-orchestrator lifecycle::` — Expected: PASS (pure helpers only).

- [ ] **Step 5: Integration test with DRY_RUN** (gated; needs the swe-af binary present)

```rust
// tests/dryrun.rs
#[tokio::test]
#[ignore] // run with: SWE_AF_BIN=... cargo test -p vaked-swe-af-orchestrator --test dryrun -- --ignored
async fn swe_af_dryrun_emits_noop_json() {
    // Requires a built vaked-swe-af on PATH or SWE_AF_BIN; DRY_RUN short-circuits the model.
    // Asserts run_swe_af returns an object with a "plan" key in plan mode.
}
```

- [ ] **Step 6: Commit** — `git commit -am "feat(orchestrator): per-task lifecycle (clone->plan->code->apply->push->broker)"`

---

## Task 8: NATS JetStream consumer (`nats.rs`)

**Files:**
- Modify: `src/nats.rs`

- [ ] **Step 1: Write failing test** (pure: stream config builder)

```rust
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn stream_cfg_is_workqueue() {
        let c = stream_config("SWE_AF_TASKS", "swe.af.tasks");
        assert_eq!(c.name, "SWE_AF_TASKS");
        assert_eq!(c.subjects, vec!["swe.af.tasks".to_string()]);
        assert!(matches!(c.retention, async_nats::jetstream::stream::RetentionPolicy::WorkQueue));
    }
}
```

- [ ] **Step 2: Run, verify fail** → FAIL.

- [ ] **Step 3: Implement**

```rust
use anyhow::{anyhow, Result};
use async_nats::jetstream::{self, consumer::PullConsumer, stream::{Config as StreamCfg, RetentionPolicy}};

pub fn stream_config(name: &str, subject: &str) -> StreamCfg {
    StreamCfg {
        name: name.to_string(),
        subjects: vec![subject.to_string()],
        retention: RetentionPolicy::WorkQueue,
        ..Default::default()
    }
}

pub async fn connect(url: &str, creds: Option<&str>) -> Result<async_nats::Client> {
    let opts = match creds {
        Some(path) => async_nats::ConnectOptions::with_credentials_file(path).await
            .map_err(|e| anyhow!("nats creds: {e}"))?,
        None => async_nats::ConnectOptions::new(),
    };
    opts.connect(url).await.map_err(|e| anyhow!("nats connect {url}: {e}"))
}

pub async fn ensure_consumer(
    js: &jetstream::Context, stream: &str, subject: &str, durable: &str,
) -> Result<PullConsumer> {
    let s = js.get_or_create_stream(stream_config(stream, subject)).await
        .map_err(|e| anyhow!("get_or_create_stream: {e}"))?;
    let c = s.get_or_create_consumer(durable, jetstream::consumer::pull::Config {
        durable_name: Some(durable.to_string()),
        ack_policy: jetstream::consumer::AckPolicy::Explicit,
        max_deliver: 3,
        ack_wait: std::time::Duration::from_secs(3600),
        ..Default::default()
    }).await.map_err(|e| anyhow!("get_or_create_consumer: {e}"))?;
    Ok(c)
}
```

- [ ] **Step 4: Run, verify pass** → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(orchestrator): JetStream work-queue stream + durable pull consumer"`

---

## Task 9: Orchestrator binary — wire the pool (`bin/orchestrator.rs`)

**Files:**
- Modify: `src/bin/orchestrator.rs`

- [ ] **Step 1: Implement** (no new unit tests; this is the wiring — verified by Task 11 e2e)

```rust
use std::sync::Arc;
use anyhow::Result;
use async_nats::jetstream;
use futures::StreamExt;
use tokio::sync::Semaphore;
use uuid::Uuid;
use vaked_swe_af_orchestrator::{config::Config, disk::{self, Guard}, lifecycle, nats, status::{Node, StatusEvent}, task::Task};

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter(
        tracing_subscriber::EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| "info".into())).init();
    if std::env::args().any(|a| a == "--version" || a == "-V") {
        println!("swe-af-orchestrator {}+{}", env!("CARGO_PKG_VERSION"), env!("GIT_SHA"));
        return Ok(());
    }
    let cfg = Arc::new(Config::from_env()?);
    std::fs::create_dir_all(&cfg.scratch)?;
    let client = nats::connect(&cfg.nats_url, cfg.nats_creds.as_deref()).await?;
    let js = jetstream::new(client.clone());
    let consumer = nats::ensure_consumer(&js, &cfg.stream, &cfg.subject, &cfg.consumer).await?;
    let sem = Arc::new(Semaphore::new(cfg.pool));
    let guard = Guard { min_free_bytes: cfg.min_free_bytes, scratch_cap_bytes: cfg.scratch_cap_bytes };
    tracing::info!(pool = cfg.pool, subject = %cfg.subject, "orchestrator up");

    let mut messages = consumer.messages().await?;
    loop {
        // disk guard: pause intake when low
        let free = disk::free_bytes(std::path::Path::new(&cfg.scratch)).unwrap_or(0);
        let used = disk::dir_size_bytes(std::path::Path::new(&cfg.scratch));
        if !guard.admits(free, used) {
            tracing::warn!(free, used, "disk guard: pausing intake 30s");
            tokio::time::sleep(std::time::Duration::from_secs(30)).await;
            continue;
        }
        let Some(msg) = messages.next().await else { break };
        let msg = match msg { Ok(m) => m, Err(e) => { tracing::warn!(%e, "pull"); continue } };
        let permit = sem.clone().acquire_owned().await.unwrap();
        let cfg2 = cfg.clone();
        let client2 = client.clone();
        tokio::spawn(async move {
            let _permit = permit;
            let payload = msg.payload.clone();
            let task = match Task::from_json(&payload) {
                Ok(t) => t,
                Err(e) => { tracing::error!(%e, "bad task — term"); let _ = msg.ack_with(jetstream::AckKind::Term).await; return; }
            };
            let work = std::path::Path::new(&cfg2.scratch).join(format!("{}-{}", task.task_id, Uuid::new_v4()));
            let _ = std::fs::create_dir_all(&work);
            let pub_status = |node: Node, state: &str, detail: Option<String>| {
                let c = client2.clone(); let prefix = cfg2.status_prefix.clone();
                let mut ev = StatusEvent::new(&task.task_id, node, state);
                if let Some(d) = detail { ev = ev.with_detail(&d); }
                async move { let _ = c.publish(ev.subject(&prefix), ev.encode().into()).await; }
            };
            pub_status(Node::Run, "started", None).await;
            // keepalive: extend ack while running
            let res = lifecycle::run_task(&cfg2, &task, &work).await;
            match res {
                Ok(o) => {
                    pub_status(Node::Done, "ok", o.pr_url.clone()).await;
                    let _ = msg.ack().await;
                }
                Err(e) => {
                    tracing::error!(task = %task.task_id, %e, "task failed");
                    pub_status(Node::Error, "failed", Some(format!("{e:#}"))).await;
                    let _ = msg.ack_with(jetstream::AckKind::Nak(None)).await;
                }
            }
            let _ = std::fs::remove_dir_all(&work); // disk cleanup
        });
    }
    Ok(())
}
```

- [ ] **Step 2: Build** — `cargo build -p vaked-swe-af-orchestrator` — Expected: compiles.
- [ ] **Step 3: Commit** — `git commit -am "feat(orchestrator): pool daemon — pull, guard, spawn, status, ack/cleanup"`

---

## Task 10: Enqueue CLI (`bin/enqueue.rs`)

**Files:**
- Modify: `src/bin/enqueue.rs`

- [ ] **Step 1: Implement** (publish one Task; args: `--repo`, `--issue`, optional `--plan-model/--code-model`)

```rust
use anyhow::{anyhow, Result};
use vaked_swe_af_orchestrator::{config::Config, nats, task::Task};
use uuid::Uuid;

#[tokio::main]
async fn main() -> Result<()> {
    let mut repo = None; let mut issue = None;
    let mut plan_model = None; let mut code_model = None;
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--repo" => repo = args.next(),
            "--issue" => issue = args.next().and_then(|s| s.parse::<u64>().ok()),
            "--plan-model" => plan_model = args.next(),
            "--code-model" => code_model = args.next(),
            _ => return Err(anyhow!("unknown arg {a}")),
        }
    }
    let task = Task {
        task_id: Uuid::new_v4().to_string(),
        repo: repo.ok_or_else(|| anyhow!("--repo required"))?,
        issue_number: issue.ok_or_else(|| anyhow!("--issue required"))?,
        plan_model, code_model, max_files: None,
    };
    let cfg = Config::from_env()?;
    let client = nats::connect(&cfg.nats_url, cfg.nats_creds.as_deref()).await?;
    let js = async_nats::jetstream::new(client.clone());
    js.get_or_create_stream(nats::stream_config(&cfg.stream, &cfg.subject)).await
        .map_err(|e| anyhow!("ensure stream: {e}"))?;
    let bytes = serde_json::to_vec(&task)?;
    let ack = js.publish(cfg.subject.clone(), bytes.into()).await.map_err(|e| anyhow!("publish: {e}"))?;
    ack.await.map_err(|e| anyhow!("publish ack: {e}"))?;
    println!("enqueued {} -> {} (issue #{})", task.task_id, task.repo, task.issue_number);
    Ok(())
}
```

- [ ] **Step 2: Build** — `cargo build -p vaked-swe-af-orchestrator` — Expected: compiles.
- [ ] **Step 3: Commit** — `git commit -am "feat(orchestrator): swe-af-enqueue producer CLI"`

---

## Task 11: Lint + full test gate

- [ ] **Step 1:** `cargo fmt --manifest-path vaked-agents/ci/swe-af-orchestrator/Cargo.toml`
- [ ] **Step 2:** `cargo clippy -p vaked-swe-af-orchestrator -- -D warnings` — fix the cause of any warning (no `#[allow]` silencing).
- [ ] **Step 3:** `cargo test -p vaked-swe-af-orchestrator` — Expected: all unit tests PASS; `--ignored` integration tests skipped.
- [ ] **Step 4: Confirm swe-af untouched** — `cargo test --manifest-path vaked-agents/ci/swe-af/Cargo.toml` still green (7 tests).
- [ ] **Step 5: Commit** — `git commit -am "chore(orchestrator): fmt + clippy clean"`

---

## Task 12: Deploy unit + runbook (applied post-P1)

**Files:**
- Create: `vaked-agents/ci/swe-af-orchestrator/deploy/swe-af.slice`
- Create: `vaked-agents/ci/swe-af-orchestrator/deploy/swe-af-orchestrator.service`
- Create: `vaked-agents/ci/swe-af-orchestrator/deploy/swe-af-orchestrator.env.example`
- Create: `vaked-agents/ci/swe-af-orchestrator/deploy/README.md`

- [ ] **Step 1: `swe-af.slice`** (aggregate fence — swe-af is the guest on the box)

```ini
[Unit]
Description=swe-af batch slice (bounded guest)
[Slice]
MemoryMax=8G
MemoryHigh=6G
CPUQuota=600%
TasksMax=4096
```

- [ ] **Step 2: `swe-af-orchestrator.service`**

```ini
[Unit]
Description=swe-af fan-out batch orchestrator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Slice=swe-af.slice
DynamicUser=yes
StateDirectory=swe-af
EnvironmentFile=/etc/swe-af/orchestrator.env
ExecStart=/usr/local/bin/swe-af-orchestrator
Restart=on-failure
RestartSec=5
# disk: scratch lives under StateDirectory (/var/lib/swe-af)

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: `orchestrator.env.example`**

```sh
NATS_URL=nats://100.73.72.35:4222
SWE_AF_POOL=6
SWE_AF_SCRATCH=/var/lib/swe-af/scratch
SWE_AF_MIN_FREE_GB=10
SWE_AF_SCRATCH_CAP_GB=20
SWE_AF_BIN=/usr/local/bin/vaked-swe-af
OPENROUTER_BASE_URL=https://nixai-base.tail2870dc.ts.net/aperture/v1
SWE_AF_API_KEY=tailscale-identity
SWE_AF_PLAN_MODEL=deepseek/deepseek-v4-flash
SWE_AF_CODE_MODEL=openai/gpt-5.3-codex
# GH_TOKEN=<read scope, for `gh issue view`>
# SWE_AF_GH_WRITE_TOKEN=<write scope, broker step only>
```

- [ ] **Step 4: `deploy/README.md`** — the post-P1 runbook. Document, in order:
  1. **P1 (operator):** `ssh bench-node 'curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up --advertise-tags=tag:agents'`; verify `tailscale status` shows it and `curl https://nixai-base.tail2870dc.ts.net/aperture/openapi.json` == 200 from the box.
  2. **P2 (operator, Aperture Visual editor `/ui/settings`):** add grant `{ "src": ["tag:agents"], "app": { "tailscale.com/cap/aperture": [ {"role":"user"}, {"models":"**"} ] } }`; Test; Save. (Do NOT round-trip the config via API — GET redacts the key.)
  3. **P3:** install `gh` on bench-node (`sudo apt-get install -y gh` via the cli.github.com apt repo); `gh release download swe-af-bin -R peterlodri-sec/vaked-base -p vaked-swe-af-linux-x86_64 -O /usr/local/bin/vaked-swe-af && chmod +x`; build + install `swe-af-orchestrator` + `swe-af-enqueue` (`cargo build --release` on a rust host, scp the two bins to `/usr/local/bin`).
  4. **P4:** `docker image prune -f` on bench-node; create `/var/lib/swe-af`.
  5. Install units: copy `swe-af.slice` + `swe-af-orchestrator.service` to `/etc/systemd/system/`, write `/etc/swe-af/orchestrator.env`, `systemctl daemon-reload && systemctl enable --now swe-af-orchestrator`.
  6. **Smoke:** `NATS_URL=... swe-af-enqueue --repo peterlodri-sec/vaked-base --issue <n>`; watch `journalctl -u swe-af-orchestrator -f`; confirm a draft PR + `swe.af.status.*` frames in the Sentinel Console.

- [ ] **Step 5: Commit** — `git commit -am "feat(orchestrator): systemd slice/unit + post-P1 deploy runbook"`

---

## Task 13: Console subject + CI build workflow (integration)

**Files:**
- Modify: the Sentinel Console NATS subscriber (crabcc-viz; subscribes `crabcc.>`) to also accept `swe.af.>` — **note:** this lives in the *crabcc* repo, not vaked-base. Track as a cross-repo follow-up issue; do NOT edit crabcc from this PR.
- Create: `.github/workflows/swe-af-orchestrator-build.yml` (mirror `swe-af-build.yml`: build `swe-af-orchestrator` + `swe-af-enqueue` for `linux-x86_64`, publish to a rolling `swe-af-orchestrator-bin` pre-release).

- [ ] **Step 1: Write the build workflow** (mirror `.github/workflows/swe-af-build.yml` exactly, swapping crate path to `vaked-agents/ci/swe-af-orchestrator` and asset names).
- [ ] **Step 2: Open the cross-repo console issue** (`gh issue create -R peterlodri-sec/crabcc` ... "console: subscribe swe.af.> for batch status") — link it in the PR body.
- [ ] **Step 3: Commit** — `git commit -am "ci(orchestrator): rolling prebuilt binary workflow"`

---

## Verification (whole feature)

- [ ] `cargo test -p vaked-swe-af-orchestrator` green; `cargo clippy -- -D warnings` clean; `cargo fmt --check`.
- [ ] `vaked-agents/ci/swe-af` tests still green (binary reused, not modified).
- [ ] Post-P1 smoke (runbook step 6): one enqueued issue -> draft PR + clean `eventd verify` + Console status frames.
- [ ] Fan-out: enqueue K+2 issues; pool never exceeds K concurrent; scratch free never < `SWE_AF_MIN_FREE_GB`; every task reaches done|error.

## Open follow-ups (not in this PR)
- Freeform `prompt` tasks (needs a swe-af mode that doesn't require an issue).
- Per-task cgroup cells via sandboxd (v1 uses the aggregate slice).
- GCP c3 / ccx33 workers; autoscaling by queue depth.
- crabcc-viz console `swe.af.>` subscription (cross-repo issue).
