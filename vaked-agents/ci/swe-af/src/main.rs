use std::collections::{HashMap, HashSet};
use std::process::Command as StdCommand;
use std::sync::Arc;
use std::time::Duration;
use adk_core::{Content, GenerateContentConfig, SessionId, UserId};
use adk_rust::prelude::*;
use adk_rust::session::{CreateRequest, SessionService};
use adk_rust::{RetryBudget, ToolExecutionStrategy};
use adk_runner::compaction::{CompactionConfig, TruncationCompaction};
use anyhow::{Context, Result, anyhow};
use futures::StreamExt;
use adk_rust::tool::McpToolset;
use rmcp::ServiceExt;
use rmcp::transport::TokioChildProcess;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use tokio::process::Command as TokioCommand;
use serde_json::{Value, json};
use tracing::{info, warn};
mod guardrails;
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;
const DEFAULT_MODEL: &str = "google/gemini-3.1-flash-lite";
const DEFAULT_BASE_URL: &str = "https://openrouter.ai/api/v1";
const DEFAULT_MAX_ITERS: u32 = 200;
const DEFAULT_DEADLINE_SECS: u64 = 180;
const COMPACTION_BUDGET_TOKENS: usize = 120_000;
const COMPACTION_PRESERVE_RECENT: usize = 6;
const CACHE_KEY: &str = "vaked-swe-af-v1";
const DEFAULT_MAX_FILES: usize = 20;
const MAX_FILE_CHARS: usize = 64_000;
const MAX_ISSUE_CHARS: usize = 16_000;
const MAX_SEED_FILES: usize = 8;
const MAX_SEED_FILE_CHARS: usize = 16_000;
const MAX_REPO_MAP_ENTRIES: usize = 800;
const MAX_REPO_MAP_CHARS: usize = 12_000;
enum Mode {
Plan,
Code,
}
impl Mode {
fn from_str(s: &str) -> Self {
match s.to_ascii_lowercase().trim() {
"code" => Mode::Code,
_ => Mode::Plan,
}
}
fn as_str(self) -> &'static str {
match self {
Mode::Plan => "plan",
Mode::Code => "code",
}
}
}
struct Config {
repo: String,
mode: Mode,
issue_number: Option<u64>,
plan_file: Option<String>,
model: String,
base_url: String,
api_key: Option<String>,
max_iters: u32,
max_files: usize,
dry_run: bool,
}
impl Config {
fn from_env() -> Result<Self> {
let repo = std::env::var("GITHUB_REPOSITORY")
.unwrap_or_else(|_| "peterlodri-sec/vaked-base".to_string());
let mode = Mode::from_str(&std::env::var("MODE").unwrap_or_default());
let issue_number = std::env::var("ISSUE_NUMBER")
.ok()
.and_then(|s| s.parse::<u64>().ok());
let plan_file = std::env::var("PLAN_FILE").ok().filter(|s| !s.is_empty());
let env_nonempty = |k: &str| std::env::var(k).ok().filter(|s| !s.is_empty());
let model = env_nonempty("SWE_AF_MODEL")
.or_else(|| match mode {
Mode::Plan => env_nonempty("SWE_AF_PLAN_MODEL"),
Mode::Code => env_nonempty("SWE_AF_CODE_MODEL"),
})
.unwrap_or_else(|| DEFAULT_MODEL.to_string());
let base_url = std::env::var("OPENROUTER_BASE_URL")
.unwrap_or_else(|_| DEFAULT_BASE_URL.to_string());
let api_key = std::env::var("SWE_AF_API_KEY")
.ok()
.or_else(|| std::env::var("OPENROUTER_API_KEY").ok())
.filter(|s| !s.is_empty());
let max_iters = std::env::var("SWE_AF_MAX_ITERS")
.ok()
.and_then(|s| s.parse().ok())
.unwrap_or(DEFAULT_MAX_ITERS);
let max_files = std::env::var("SWE_AF_MAX_FILES")
.ok()
.and_then(|s| s.parse().ok())
.unwrap_or(DEFAULT_MAX_FILES);
let dry_run = std::env::var("DRY_RUN")
.map(|s| s == "1" || s.to_ascii_lowercase() == "true")
.unwrap_or(false);
Ok(Config {
repo, mode, issue_number, plan_file, model, base_url, api_key,
max_iters, max_files, dry_run,
})
}
}
struct PlanOutput {
plan: String,
target_files: Vec<String>,
summary: String,
}
struct FileEdit {
path: String,
content: String,
}
struct CodeOutput {
files: Vec<FileEdit>,
commit_message: String,
notes: String,
}
fn plan_schema() -> Value {
json!({
"type": "object",
"additionalProperties": false,
"required": ["plan", "target_files", "summary"],
"properties": {
"plan": { "type": "string", "description": "Markdown implementation plan" },
"target_files": {
"type": "array",
"items": { "type": "string" },
"description": "Repo-relative files to create or modify"
},
"summary": { "type": "string", "description": "One-line change summary" }
}
})
}
fn code_schema() -> Value {
json!({
"type": "object",
"additionalProperties": false,
"required": ["files", "commit_message", "notes"],
"properties": {
"files": {
"type": "array",
"items": {
"type": "object",
"additionalProperties": false,
"required": ["path", "content"],
"properties": {
"path": { "type": "string" },
"content": { "type": "string" }
}
},
"description": "Full new content per file (create/overwrite)"
},
"commit_message": { "type": "string" },
"notes": { "type": "string" }
}
})
}
fn noop_json(mode: Mode) -> String {
match mode {
Mode::Plan => serde_json::to_string(&PlanOutput::default()).unwrap(),
Mode::Code => serde_json::to_string(&CodeOutput::default()).unwrap(),
}
}
struct AgentRunner {
runner: Runner,
sessions: Arc<dyn SessionService>,
}
async fn connect_explorer() -> Result<McpToolset> {
let bin = std::env::var("VAKED_BIN")
.ok()
.filter(|b| std::path::Path::new(b).is_absolute())
.unwrap_or_else(|| {
if std::path::Path::new("./bin/vaked").exists() {
"./bin/vaked".to_string()
} else {
"vaked".to_string()
}
});
let sub = if std::path::Path::new(".crabcc").is_dir() { "refresh" } else { "build" };
let bin2 = bin.clone();
let sub_str = sub.to_string();
let status = tokio::task::spawn_blocking(move || {
StdCommand::new(&bin2).args(["explore", "index", &sub_str]).status()
})
.await
.map_err(|e| anyhow!("spawn_blocking: {e}"))?;
match status {
Ok(s) if s.success() => info!(action = sub, "vaked→crabcc index ready"),
Ok(s) => warn!(action = sub, code = ?s.code(), "vaked explore index step non-zero"),
Err(e) => return Err(anyhow!("vaked not runnable ({bin}): {e}")),
}
let mut command = TokioCommand::new(&bin);
command.args(["explore", "--mcp"]);
let transport = TokioChildProcess::new(command).context("spawn vaked explore --mcp")?;
let client = ().serve(transport).await.context("crabcc MCP handshake")?;
Ok(McpToolset::new(client).with_name("crabcc"))
}
async fn build_runner(cfg: &Config, api_key: &str) -> Result<AgentRunner> {
let or_config = OpenRouterConfig::new(api_key.to_string(), cfg.model.clone())
.with_base_url(cfg.base_url.clone())
.with_http_referer("https://github.com/peterlodri-sec/vaked-base")
.with_title("vaked-swe-af")
.with_default_api_mode(OpenRouterApiMode::ChatCompletions);
let model = OpenRouterClient::new(or_config).map_err(|e| anyhow!("OpenRouter client: {e}"))?;
let (default_out, default_effort) = match cfg.mode {
Mode::Plan => (8192, "high"),
Mode::Code => (32768, "high"),
};
let max_out: i32 = std::env::var("SWE_AF_MAX_OUTPUT_TOKENS")
.ok()
.and_then(|s| s.parse::<i32>().ok())
.filter(|&v| v > 0 && v <= 131_072)
.unwrap_or(default_out);
let effort = std::env::var("SWE_AF_REASONING_EFFORT")
.ok()
.filter(|s| !s.is_empty())
.unwrap_or_else(|| default_effort.to_string());
let mut gen_cfg = GenerateContentConfig {
temperature: Some(0.1),
top_p: Some(0.9),
max_output_tokens: Some(max_out),
seed: Some(7),
..Default::default()
};
let reasoning_enabled = match std::env::var("SWE_AF_REASONING")
.unwrap_or_default()
.to_ascii_lowercase()
.as_str()
{
"1" | "on" | "true" | "yes" => true,
"0" | "off" | "false" | "no" => false,
_ => cfg.model.starts_with("google/gemini"),
};
let cache_key = format!("{CACHE_KEY}:{}:{}", cfg.model, cfg.mode.as_str());
let mut opts = OpenRouterRequestOptions::default()
.with_reasoning(OpenRouterReasoningConfig {
effort: Some(effort.clone()),
enabled: Some(reasoning_enabled),
..Default::default()
})
.with_prompt_cache_key(&cache_key)
.with_provider_preferences(OpenRouterProviderPreferences {
allow_fallbacks: Some(true),
..Default::default()
});
opts.extra.insert("usage".to_string(), json!({ "include": true }));
opts.insert_into_config(&mut gen_cfg)
.map_err(|e| anyhow!("OpenRouter options: {e}"))?;
let explorer = connect_explorer().await;
let iters = match &explorer {
Ok(_) => cfg.max_iters,
Err(_) => cfg.max_iters.min(20),
};
let mut builder = LlmAgentBuilder::new("vaked-swe-af")
.instruction(system_prompt(cfg.mode))
.model(Arc::new(model))
.generate_content_config(gen_cfg)
.max_iterations(iters)
.tool_timeout(Duration::from_secs(30))
.tool_execution_strategy(ToolExecutionStrategy::Auto)
.tool_retry_budget("read_file", RetryBudget {
max_retries: 2,
delay: Duration::from_millis(200),
})
.tool(read_file_tool())
.tool(list_dir_tool())
.tool(search_repo_tool());
match explorer {
Ok(ts) => {
info!("exploration via vaked→crabcc symbol index (+ native read for full files)");
builder = builder
.tool_retry_budget("crabcc", RetryBudget {
max_retries: 2,
delay: Duration::from_millis(250),
})
.toolset(Arc::new(ts) as Arc<dyn Toolset>);
}
Err(e) => {
warn!(error = %e, "crabcc unavailable — using native read/search tools only");
}
}
let agent = builder.build().map_err(|e| anyhow!("agent build: {e}"))?;
let sessions: Arc<dyn SessionService> = Arc::new(InMemorySessionService::new());
let run_config = RunConfig::builder().auto_cache(true).build();
let runner = Runner::builder()
.app_name("vaked-swe-af")
.agent(Arc::new(agent))
.session_service(sessions.clone())
.run_config(run_config)
.context_compaction(CompactionConfig::new(
Box::new(TruncationCompaction { preserve_recent: COMPACTION_PRESERVE_RECENT }),
COMPACTION_BUDGET_TOKENS,
))
.build()
.map_err(|e| anyhow!("runner build: {e}"))?;
Ok(AgentRunner { runner, sessions })
}
struct Conversation<'a> {
rr: &'a AgentRunner,
user: UserId,
session: SessionId,
}
impl<'a> Conversation<'a> {
async fn new(rr: &'a AgentRunner) -> Result<Self> {
let session = SessionId::generate();
rr.sessions
.create(CreateRequest {
app_name: "vaked-swe-af".into(),
user_id: "vaked-ci".into(),
session_id: Some(session.to_string()),
state: HashMap::new(),
})
.await
.map_err(|e| anyhow!("session create: {e}"))?;
let user = UserId::new("vaked-ci").map_err(|e| anyhow!("user id: {e}"))?;
Ok(Self { rr, user, session })
}
async fn send(&self, prompt: String, deadline: tokio::time::Instant) -> Result<TurnResult> {
let content = Content::new("user").with_text(prompt);
let mut stream = self
.rr
.runner
.run(self.user.clone(), self.session.clone(), content)
.await
.map_err(|e| anyhow!("runner.run: {e}"))?;
let mut out = String::new();
let mut hit_limit = false;
let (mut n_text, mut n_calls, mut n_think) = (0u32, 0u32, 0u32);
let mut tools_called: Vec<String> = Vec::new();
loop {
let event = match tokio::time::timeout_at(deadline, stream.next()).await {
Err(_) => {
warn!("agent turn hit wall-clock deadline — keeping partial output");
hit_limit = true;
break;
}
Ok(None) => break,
Ok(Some(Err(e))) => {
warn!(error = %e, "agent stream ended early — keeping partial output");
hit_limit = true;
break;
}
Ok(Some(Ok(ev))) => ev,
};
if let Some(content) = &event.llm_response.content {
for part in &content.parts {
match part {
adk_core::Part::FunctionCall { name, .. } => {
n_calls += 1;
tools_called.push(name.clone());
}
adk_core::Part::Thinking { .. } => n_think += 1,
adk_core::Part::Text { text } => {
n_text += 1;
out.push_str(text);
}
_ => {}
}
}
}
}
info!(
text_parts = n_text,
thinking_parts = n_think,
tool_calls = n_calls,
out_chars = out.len(),
hit_limit,
tools = ?tools_called,
"agent turn complete"
);
Ok(TurnResult { text: out, hit_limit })
}
}
struct TurnResult {
text: String,
hit_limit: bool,
}
fn safe_rel_path(path: &str) -> bool {
!path.is_empty() && !path.contains("..") && !path.starts_with('/')
}
fn safe_rel_path_for_read(path: &str) -> bool {
if !safe_rel_path(path) { return false; }
let Ok(cwd) = std::env::current_dir() else { return true; };
match std::fs::canonicalize(path) {
Ok(abs) => abs.starts_with(&cwd),
Err(_) => false,
}
}
struct PathArg {
path: String,
}
struct SearchArg {
query: String,
path: Option<String>,
}
fn read_file_tool() -> Arc<dyn Tool> {
Arc::new(
FunctionTool::new(
"read_file",
"Read a full repo-relative file (read-only). Use this to inspect the \
files you plan to change BEFORE emitting their new content.",
|_ctx: Arc<dyn ToolContext>, args: Value| async move {
let path = args.get("path").and_then(Value::as_str).unwrap_or_default().to_string();
if !safe_rel_path_for_read(&path) {
return Ok(json!({"error": "path must be repo-relative, no '..', no leading /"}));
}
match std::fs::read_to_string(&path) {
Ok(t) => Ok(json!({"path": path, "content": t.chars().take(MAX_FILE_CHARS).collect::<String>()})),
Err(e) => Ok(json!({"error": format!("read {path}: {e}")})),
}
},
)
.with_read_only(true)
.with_concurrency_safe(true)
.with_parameters_schema::<PathArg>(),
)
}
fn list_dir_tool() -> Arc<dyn Tool> {
Arc::new(
FunctionTool::new(
"list_dir",
"List the entries of a repo-relative directory (read-only). Use to \
discover file names before reading them.",
|_ctx: Arc<dyn ToolContext>, args: Value| async move {
let path = args.get("path").and_then(Value::as_str).unwrap_or(".").to_string();
if !safe_rel_path(&path) && path != "." {
return Ok(json!({"error": "path must be repo-relative, no '..', no leading /"}));
}
match std::fs::read_dir(&path) {
Ok(rd) => {
let mut entries: Vec<String> = rd
.filter_map(|e| e.ok())
.map(|e| {
let name = e.file_name().to_string_lossy().into_owned();
if e.path().is_dir() { format!("{name}/") } else { name }
})
.collect();
entries.sort();
entries.truncate(400);
Ok(json!({"path": path, "entries": entries}))
}
Err(e) => Ok(json!({"error": format!("list {path}: {e}")})),
}
},
)
.with_read_only(true)
.with_concurrency_safe(true)
.with_parameters_schema::<PathArg>(),
)
}
fn search_repo_tool() -> Arc<dyn Tool> {
Arc::new(
FunctionTool::new(
"search_repo",
"Search the repo with `git grep` (read-only). args: { query: string, \
path?: string }. Returns matching `file:line:text`. Use this FIRST to \
locate the symbol, string, or function the issue is about before reading \
whole files.",
|_ctx: Arc<dyn ToolContext>, args: Value| async move {
let query = args
.get("query")
.and_then(Value::as_str)
.unwrap_or_default()
.to_string();
if query.trim().is_empty() {
return Ok(json!({"error": "query is required"}));
}
let path = args.get("path").and_then(Value::as_str).unwrap_or(".").to_string();
if path != "." && !safe_rel_path(&path) {
return Ok(json!({"error": "path must be repo-relative, no '..', no leading /"}));
}
let out = StdCommand::new("git")
.args(["grep", "-n", "-I", "--no-color", "-e", &query, "--", &path])
.output();
match out {
Ok(o) => {
let text = String::from_utf8_lossy(&o.stdout);
let matches: String = text
.lines()
.take(200)
.collect::<Vec<_>>()
.join("\n")
.chars()
.take(16_000)
.collect();
Ok(json!({"query": query, "matches": matches}))
}
Err(e) => Ok(json!({"error": format!("git grep: {e}")})),
}
},
)
.with_read_only(true)
.with_concurrency_safe(true)
.with_parameters_schema::<SearchArg>(),
)
}
fn system_prompt(mode: Mode) -> String {
match mode {
Mode::Plan => PLAN_SYSTEM.to_string(),
Mode::Code => CODE_SYSTEM.to_string(),
}
}
const PLAN_SYSTEM: &str = r#"You are the PLAN node of the Vaked `swe_af` workflow (the `planner` mesh role,
read-only: capabilities fs.repo_ro + mem.recall). Given a GitHub issue, produce a
concrete, minimal implementation plan for the vaked-base monorepo.
1. GROUND yourself. A repo file map and the most relevant files are already inlined in
the user message — read them first. If you need more, you ARE in a tool loop and may
CALL the tools (do it, don't narrate): `search_repo(query)` to locate a symbol,
`read_file(path)` to read a file, `list_dir(path)` to discover files. Never invent
paths — every entry in `target_files` must exist in the file map (or be a new file in
a directory that does).
2. ANSWER. Once grounded, your FINAL message must be EXACTLY one JSON object matching
the output contract below — no prose, no markdown fences, nothing else.
Navigate with the crabcc symbol index when present (a symbol's definition, references,
callers, a file's outline, fuzzy name search, and grep over indexed code) — cheap indexed
lookups, chain as many as you need. Fetch full file contents with `read_file` (and
`list_dir`/`search_repo`); always `read_file` a target before rewriting it so you preserve
everything you're not changing. Key files are already inlined above, so you mostly need
tools to find and read *related* code, callers, and tests.
- Smallest change that fully resolves the issue. Prefer editing existing files and
reusing existing utilities over adding new ones.
- Respect repo conventions (grammar-first for language changes; design→plan→impl
for subsystems). If the issue is a versioned-language change, note that in the plan.
- The plan becomes the PR body — write it for a human reviewer: numbered steps, the
exact files to change, and how to verify.
You MAY reason in AI-lish register frames during the tool loop to keep intermediate turns
dense, e.g. `[R:plan] read(`x.rs`) -> map(callers)` or `[R:risk] ... gate(ci:warn)`. Those
frames are for your reasoning ONLY. The FINAL JSON is an ARTIFACT: `plan` and `summary`
become a PR body, so they MUST be standard English with no CJK and no `[R:*]` frames,
operators, or compression notation. Compression never reaches an artifact.
A single JSON object:
- `plan`: the markdown plan.
- `target_files`: every repo-relative path the coder will create or modify.
- `summary`: a <=72-char imperative one-liner (used as the PR title).
Keep `target_files` tight and correct — the coder will only edit those files."#;
const CODE_SYSTEM: &str = r#"You are the CODE node of the Vaked `swe_af` workflow (the `coder` mesh role:
capabilities fs.repo_rw + process.spawn_sandboxed + mem.recall). You are given an
issue and an approved plan. Produce the actual change as FULL file contents.
1. GROUND yourself. The target files' current contents are inlined in the user message —
read them so you preserve everything you are not deliberately changing. If you need
more, you ARE in a tool loop and may CALL the tools (do it, don't narrate):
`read_file`, `search_repo`, `list_dir` for related code, callers, and tests.
2. ANSWER. Your FINAL message must be EXACTLY one JSON object matching the output
contract below — no prose, no markdown fences, nothing else.
Navigate with the crabcc symbol index when present (a symbol's definition, references,
callers, a file's outline, fuzzy name search, and grep over indexed code) — cheap indexed
lookups, chain as many as you need. Fetch full file contents with `read_file` (and
`list_dir`/`search_repo`); always `read_file` a target before rewriting it so you preserve
everything you're not changing. Key files are already inlined above, so you mostly need
tools to find and read *related* code, callers, and tests.
For each file you create or modify, return an object `{ "path", "content" }` where
`content` is the COMPLETE new file (NOT a diff, NOT a fragment). The workflow writes
each file verbatim, commits, and opens a PR — so partial content WILL corrupt files.
- Implement exactly the approved plan. Stay within the plan's target files unless a
change is strictly required elsewhere (then include that file fully too).
- Match the surrounding code's style, naming, and comment density.
- Do not add license headers, unrelated reformatting, or generated artifacts.
- Keep the change minimal and correct. If something in the plan is infeasible, do
your best partial and explain the gap in `notes`.
You MAY reason in AI-lish register frames during the tool loop to keep intermediate turns
dense, e.g. `[R:tool] read(`x.rs`)` or `[R:risk] ... gate(test:warn)`. Those frames are for
your reasoning ONLY. The FINAL JSON is an ARTIFACT: every `files[].content` is written
verbatim and committed, and `commit_message` is committed too, so they MUST be valid code
or standard English with no CJK and no `[R:*]` frames, operators, or compression notation
anywhere in file contents, comments, or the commit message.
A single JSON object:
- `files`: array of `{ path, content }` full-content writes.
- `commit_message`: a conventional-commits message (e.g. `fix(eventd): ...`).
- `notes`: short reviewer notes — limitations, follow-ups, anything you skipped."#;
fn gh(args: &[&str]) -> Result<String> {
let out = StdCommand::new("gh")
.args(args)
.output()
.with_context(|| format!("running `gh {}`", args.join(" ")))?;
if !out.status.success() {
return Err(anyhow!(
"`gh {}` failed: {}",
args.join(" "),
String::from_utf8_lossy(&out.stderr).trim()
));
}
Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}
struct IssueMeta {
number: u64,
title: String,
body: String,
labels: Vec<String>,
}
fn fetch_issue_meta(cfg: &Config, issue: u64) -> Result<IssueMeta> {
let issue_s = issue.to_string();
let raw = gh(&["issue", "view", &issue_s, "--repo", &cfg.repo, "--json", "title,body,labels,number"])?;
let v: Value = serde_json::from_str(&raw).context("parsing gh issue view JSON")?;
let labels = v["labels"].as_array().map(|a| {
a.iter().filter_map(|l| l["name"].as_str().map(String::from)).collect()
}).unwrap_or_default();
Ok(IssueMeta {
number: v["number"].as_u64().unwrap_or(issue),
title: v["title"].as_str().unwrap_or_default().to_string(),
body: v["body"].as_str().unwrap_or_default().to_string(),
labels,
})
}
fn truncate(s: &str, max: usize) -> String {
if s.chars().count() <= max {
s.to_string()
} else {
s.chars().take(max).collect::<String>() + "\n…(truncated)…"
}
}
fn tracked_files() -> Vec<String> {
match StdCommand::new("git").arg("ls-files").output() {
Ok(o) if o.status.success() => String::from_utf8_lossy(&o.stdout)
.lines()
.map(str::to_string)
.collect(),
_ => Vec::new(),
}
}
fn repo_file_map(tracked: &[String]) -> String {
let mut lines: Vec<&str> = tracked.iter().map(String::as_str).collect();
lines.truncate(MAX_REPO_MAP_ENTRIES);
truncate(&lines.join("\n"), MAX_REPO_MAP_CHARS)
}
fn referenced_files(text: &str, tracked: &[String]) -> Vec<String> {
let mut result: Vec<String> = Vec::new();
let mut seen: HashSet<String> = HashSet::new();
for tok in text.split(|c: char| !(c.is_alphanumeric() || matches!(c, '/' | '.' | '_' | '-'))) {
let tok = tok.trim_matches('.');
if tok.len() < 4 || tok.contains("..") {
continue;
}
let base = tok.rsplit('/').next().unwrap_or(tok);
if !base.contains('.') || base.starts_with('.') {
continue; // needs a file.ext shape
}
if tracked.iter().any(|f| f == tok) {
if seen.insert(tok.to_string()) {
result.push(tok.to_string());
}
continue;
}
if base.len() < 5 {
continue;
}
let mut hits = 0;
for f in tracked {
if f.rsplit('/').next() == Some(base) {
if seen.insert(f.clone()) {
result.push(f.clone());
hits += 1;
}
if hits >= 2 {
break;
}
}
}
}
result
}
fn context_pack(sources: &str) -> String {
let tracked = tracked_files();
let mut s = String::new();
if tracked.is_empty() {
return s; // not a git checkout (e.g. some tests) — nothing to seed
}
s.push_str("\n## Repository file map (tracked files)\n```\n");
s.push_str(&repo_file_map(&tracked));
s.push_str("\n```\n");
let mut paths: Vec<String> = Vec::new();
for must in ["README.md", "CLAUDE.md"] {
if tracked.iter().any(|f| f == must) {
paths.push(must.to_string());
}
}
for p in referenced_files(sources, &tracked) {
if !paths.contains(&p) {
paths.push(p);
}
}
paths.truncate(MAX_SEED_FILES);
if !paths.is_empty() {
s.push_str("\n## Key files (already read for you)\n");
for p in &paths {
if let Ok(content) = std::fs::read_to_string(p) {
s.push_str(&format!(
"\n### {p}\n```\n{}\n```\n",
truncate(&content, MAX_SEED_FILE_CHARS)
));
}
}
}
s
}
fn build_plan_prompt(meta: &IssueMeta) -> String {
let mut s = String::new();
s.push_str("# Plan the fix for this issue\n\n");
s.push_str(&format!("Issue #{}: {}\n", meta.number, guardrails::sanitize_untrusted(&meta.title)));
if !meta.body.trim().is_empty() {
s.push_str("\n## Issue body\n");
s.push_str(&truncate(&guardrails::sanitize_untrusted(meta.body.trim()), MAX_ISSUE_CHARS));
s.push('\n');
}
if !meta.labels.is_empty() {
s.push_str(&format!("\nLabels: {}\n", meta.labels.join(", ")));
}
s.push_str(&context_pack(&format!("{}\n{}", meta.title, meta.body)));
s.push_str(
"\nUse the inlined context above (and the tools if you need more), then end with \
the final JSON object.\n",
);
s.push_str("\n## Output schema\n");
s.push_str(&serde_json::to_string_pretty(&plan_schema()).unwrap_or_default());
s
}
fn build_code_prompt(meta: &IssueMeta, plan: &str) -> String {
let mut s = String::new();
s.push_str("# Implement the approved plan\n\n");
s.push_str(&format!("Issue #{}: {}\n", meta.number, guardrails::sanitize_untrusted(&meta.title)));
if !meta.body.trim().is_empty() {
s.push_str("\n## Issue body\n");
s.push_str(&truncate(&guardrails::sanitize_untrusted(meta.body.trim()), MAX_ISSUE_CHARS));
s.push('\n');
}
s.push_str("\n## Approved plan\n");
s.push_str(&truncate(&guardrails::sanitize_untrusted(plan), MAX_ISSUE_CHARS));
s.push_str(&context_pack(&format!("{}\n{}\n{}", meta.title, meta.body, plan)));
s.push_str(
"\nThe target files are inlined above — rewrite them in FULL (use the tools only \
if something is missing), then end with the final JSON object.\n",
);
s.push_str("\n## Output schema\n");
s.push_str(&serde_json::to_string_pretty(&code_schema()).unwrap_or_default());
s
}
fn finalize_nudge(mode: Mode) -> String {
let shape = match mode {
Mode::Plan => plan_schema(),
Mode::Code => code_schema(),
};
format!(
"You have explored enough. Do NOT call any more tools. Output ONLY a single JSON \
object that EXACTLY matches this schema — no prose, no markdown fences:\n\n{}",
serde_json::to_string_pretty(&shape).unwrap_or_default(),
)
}
fn strip_fences(s: &str) -> &str {
let s = s.trim();
if let Some(rest) = s.strip_prefix("```json").or_else(|| s.strip_prefix("```")) {
return rest.trim_end_matches("```").trim();
}
s
}
fn extract_json<T: serde::de::DeserializeOwned>(raw: &str, accept: impl Fn(&T) -> bool) -> Option<T> {
if let Ok(v) = serde_json::from_str::<T>(strip_fences(raw)) {
if accept(&v) {
return Some(v);
}
}
let bytes = raw.as_bytes();
let mut spans: Vec<(usize, usize)> = Vec::new();
let (mut depth, mut start) = (0i32, 0usize);
let (mut in_str, mut esc) = (false, false);
for (i, &b) in bytes.iter().enumerate() {
if in_str {
if esc {
esc = false;
} else if b == b'\\' {
esc = true;
} else if b == b'"' {
in_str = false;
}
continue;
}
match b {
b'"' => in_str = true,
b'{' => {
if depth == 0 {
start = i;
}
depth += 1;
}
b'}' => {
if depth > 0 {
depth -= 1;
if depth == 0 {
spans.push((start, i + 1));
}
}
}
_ => {}
}
}
spans
.iter()
.rev()
.filter_map(|&(a, b)| serde_json::from_str::<T>(&raw[a..b]).ok())
.find(|v| accept(v))
}
fn parse_plan(raw: &str) -> PlanOutput {
match extract_json::<PlanOutput>(raw, |p| !p.plan.trim().is_empty()) {
Some(mut out) => {
out.target_files.retain(|p| safe_rel_path(p));
out.target_files.truncate(40);
out
}
None => {
warn!("failed to parse plan JSON — using noop");
PlanOutput::default()
}
}
}
fn parse_code(raw: &str, max_files: usize) -> CodeOutput {
match extract_json::<CodeOutput>(raw, |c| !c.files.is_empty()) {
Some(mut out) => {
out.files.retain(|f| safe_rel_path(&f.path));
for f in &mut out.files {
if f.content.chars().count() > MAX_FILE_CHARS {
f.content = f.content.chars().take(MAX_FILE_CHARS).collect();
}
}
out.files.truncate(max_files);
if out.commit_message.trim().is_empty() {
out.commit_message = "chore(swe_af): apply agent-generated change".to_string();
}
out
}
None => {
warn!("failed to parse code JSON — using noop");
CodeOutput::default()
}
}
}
async fn main() {
let tracer_provider = vaked_telemetry::setup_tracing("vaked-swe-af", "vaked-swe-af");
let mode = Mode::from_str(&std::env::var("MODE").unwrap_or_default());
let code = match run().await {
Ok(()) => 0,
Err(e) => {
warn!(error = %e, "swe-af failed (advisory — exiting 0)");
eprintln!("swe-af: {e:#}");
println!("{}", noop_json(mode));
0
}
};
if let Some(provider) = tracer_provider {
if let Err(e) = provider.force_flush() {
eprintln!("swe-af: telemetry force_flush failed: {e}");
}
if let Err(e) = provider.shutdown() {
eprintln!("swe-af: telemetry shutdown failed: {e}");
}
}
std::process::exit(code);
}
async fn run() -> Result<()> {
let cfg = Config::from_env()?;
let issue = cfg.issue_number
.ok_or_else(|| anyhow!("swe-af requires ISSUE_NUMBER"))?;
let api_key = cfg.api_key.as_deref()
.ok_or_else(|| anyhow!("no OPENROUTER_API_KEY — set it to enable swe_af"))?;
let meta = fetch_issue_meta(&cfg, issue)?;
info!(issue = meta.number, mode = cfg.mode.as_str(), "swe-af start");
let budget = std::env::var("SWE_AF_DEADLINE_SECS")
.ok()
.and_then(|s| s.parse::<u64>().ok())
.unwrap_or(DEFAULT_DEADLINE_SECS);
let start = tokio::time::Instant::now();
let explore_deadline = start + Duration::from_secs(budget * 4 / 5);
let hard_deadline = start + Duration::from_secs(budget);
match cfg.mode {
Mode::Plan => {
let prompt = build_plan_prompt(&meta);
if cfg.dry_run {
eprintln!("swe-af: dry-run plan — prompt {} chars", prompt.len());
println!("{}", noop_json(Mode::Plan));
return Ok(());
}
let runner = build_runner(&cfg, api_key).await?;
let conv = Conversation::new(&runner).await?;
let r = conv.send(prompt, explore_deadline).await?;
info!(response_chars = r.text.len(), hit_limit = r.hit_limit, "plan response received");
let mut out = parse_plan(&r.text);
if r.hit_limit || out.plan.trim().is_empty() || out.target_files.is_empty() {
warn!("plan incomplete — same-session finalize nudge");
let r2 = conv.send(finalize_nudge(Mode::Plan), hard_deadline).await?;
let out2 = parse_plan(&r2.text);
if !out2.plan.trim().is_empty() {
out = out2;
}
}
println!("{}", serde_json::to_string(&out)?);
}
Mode::Code => {
let plan = match &cfg.plan_file {
Some(p) => std::fs::read_to_string(p)
.with_context(|| format!("reading PLAN_FILE {p}"))?,
None => return Err(anyhow!("code mode requires PLAN_FILE")),
};
let prompt = build_code_prompt(&meta, &plan);
if cfg.dry_run {
eprintln!("swe-af: dry-run code — prompt {} chars", prompt.len());
println!("{}", noop_json(Mode::Code));
return Ok(());
}
let runner = build_runner(&cfg, api_key).await?;
let conv = Conversation::new(&runner).await?;
let r = conv.send(prompt, explore_deadline).await?;
info!(response_chars = r.text.len(), hit_limit = r.hit_limit, "code response received");
let mut out = parse_code(&r.text, cfg.max_files);
if r.hit_limit || out.files.is_empty() {
warn!("code incomplete — same-session finalize nudge");
let r2 = conv.send(finalize_nudge(Mode::Code), hard_deadline).await?;
let out2 = parse_code(&r2.text, cfg.max_files);
if !out2.files.is_empty() {
out = out2;
}
}
println!("{}", serde_json::to_string(&out)?);
}
}
Ok(())
}
mod tests {
use super::*;
fn mode_from_str() {
assert_eq!(Mode::from_str("plan"), Mode::Plan);
assert_eq!(Mode::from_str("code"), Mode::Code);
assert_eq!(Mode::from_str(""), Mode::Plan);
assert_eq!(Mode::from_str("CODE"), Mode::Code);
}
fn safe_rel_path_rejects_escapes() {
assert!(safe_rel_path("vaked/examples/x.vaked"));
assert!(!safe_rel_path("../etc/passwd"));
assert!(!safe_rel_path("/etc/passwd"));
assert!(!safe_rel_path(""));
}
fn parse_plan_valid() {
let j = r#"{"plan":"do x","target_files":["a.md","../bad"],"summary":"fix x"}"#;
let out = parse_plan(j);
assert_eq!(out.summary, "fix x");
assert_eq!(out.target_files, vec!["a.md"]); // ../bad dropped
}
fn parse_plan_invalid_is_noop() {
let out = parse_plan("not json");
assert!(out.plan.is_empty());
assert!(out.target_files.is_empty());
}
fn parse_code_drops_unsafe_and_defaults_msg() {
let j = r#"{"files":[{"path":"ok.txt","content":"hi"},{"path":"/abs","content":"x"}],"commit_message":"","notes":""}"#;
let out = parse_code(j, 20);
assert_eq!(out.files.len(), 1);
assert_eq!(out.files[0].path, "ok.txt");
assert!(!out.commit_message.is_empty()); // defaulted
}
fn extract_json_after_explore_prose() {
let s = "Let me read graph.py first.\nOK, here is the plan:\n\
{\"plan\":\"add a kind to node_id\",\"target_files\":[\"vakedc/graph.py\"],\"summary\":\"qualify node ids\"}\nDone.";
let out: PlanOutput = extract_json(s, |p: &PlanOutput| !p.plan.trim().is_empty()).expect("should find trailing JSON");
assert_eq!(out.summary, "qualify node ids");
assert_eq!(out.target_files, vec!["vakedc/graph.py"]);
}
fn extract_json_prefers_last_object() {
let s = "{\"plan\":\"draft\",\"target_files\":[],\"summary\":\"a\"} ... revised: \
{\"plan\":\"final\",\"target_files\":[\"b.rs\"],\"summary\":\"b\"}";
let out: PlanOutput = extract_json(s, |p: &PlanOutput| !p.plan.trim().is_empty()).expect("json");
assert_eq!(out.summary, "b");
}
fn extract_json_ignores_braces_in_strings() {
let s = "noise {\"plan\":\"use a HashMap<K,{}>\",\"target_files\":[\"x\"],\"summary\":\"s\"} tail";
let out: PlanOutput = extract_json(s, |p: &PlanOutput| !p.plan.trim().is_empty()).expect("json");
assert_eq!(out.target_files, vec!["x"]);
}
fn extract_json_none_when_absent() {
assert!(extract_json::<PlanOutput>("no json here at all", |_| true).is_none());
}
fn parse_code_skips_trailing_empty_object() {
let s = "{\"files\":[{\"path\":\"a.rs\",\"content\":\"x\"}],\"commit_message\":\"c\",\"notes\":\"\"} \
then schema echo {\"files\":[],\"commit_message\":\"\",\"notes\":\"\"}";
let out = parse_code(s, 20);
assert_eq!(out.files.len(), 1);
assert_eq!(out.files[0].path, "a.rs");
assert_eq!(out.commit_message, "c");
}
fn referenced_files_resolves_basenames_and_paths() {
let tracked = vec![
"vakedc/graph.py".to_string(),
"vakedc/resolve.py".to_string(),
"README.md".to_string(),
"tests/spec/golden/operator-field.graph.json".to_string(),
];
let text = "graph.py:97 collides; see resolve.py and \
tests/spec/golden/operator-field.graph.json";
let got = referenced_files(text, &tracked);
assert!(got.contains(&"vakedc/graph.py".to_string()));
assert!(got.contains(&"vakedc/resolve.py".to_string()));
assert!(got.contains(&"tests/spec/golden/operator-field.graph.json".to_string()));
}
fn referenced_files_ignores_non_paths() {
let tracked = vec!["vakedc/graph.py".to_string()];
let got = referenced_files("the fix for LPG node ids", &tracked);
assert!(got.is_empty());
}
fn parse_code_strips_fences() {
let j = "```json\n{\"files\":[{\"path\":\"a.rs\",\"content\":\"hi\"}],\"commit_message\":\"x\",\"notes\":\"\"}\n```";
let out = parse_code(j, 20);
assert_eq!(out.files.len(), 1);
assert_eq!(out.commit_message, "x");
}
fn noop_json_valid_both_modes() {
for m in [Mode::Plan, Mode::Code] {
let v: Value = serde_json::from_str(&noop_json(m)).unwrap();
assert!(v.is_object());
}
}
fn truncate_clips() {
assert_eq!(truncate("hello", 100), "hello");
assert!(truncate("hello world", 5).starts_with("hello"));
}
}