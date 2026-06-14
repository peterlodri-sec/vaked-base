//! Shared constants + the footer signature stamped on every posted comment.

// Gemini 3.1 Flash Lite: cheap ($0.25/$1.50 per Mtok) and — critically — it actually
// DRIVES the structured-output / tool loop through adk→OpenRouter. deepseek/claude
// instead *narrate* their intent ("I'll start by reading the files…") and ship an
// empty/preamble review on large diffs — observed live: pr-review going green while
// posting nothing. Same failure mode the swe_af work identified. Override with
// PR_REVIEW_MODEL (e.g. google/gemini-3-flash or google/gemini-3.5-flash for deeper
// reviews, anthropic/claude-sonnet-4.6, z-ai/glm-5) — see README "Model choice".
pub(crate) const DEFAULT_MODEL: &str = "google/gemini-3.1-flash-lite";
pub(crate) const DEFAULT_BASE_URL: &str = "https://openrouter.ai/api/v1";
pub(crate) const DEFAULT_MAX_DIFF_CHARS: usize = 48_000;
pub(crate) const DEFAULT_MAPREDUCE_LINES: usize = 600;
// Findings cap. Lower than the old 20: runs showed the model padding toward the cap
// with low-value/fabricated nits. Restraint is also enforced in the prompt.
pub(crate) const DEFAULT_MAX_FINDINGS: u32 = 10;
pub(crate) const DEFAULT_CRABCC_BUDGET: u32 = 8;
pub(crate) const DEFAULT_MAX_ITERS: u32 = 12;
pub(crate) const DEFAULT_REASONING_EFFORT: &str = "high";
pub(crate) const PERFILE_REASONING_EFFORT: &str = "medium";
pub(crate) const DEFAULT_CONCURRENCY: usize = 6;
/// Blended $/million-token rate for the cost estimate in the footer (override with
/// PR_REVIEW_USD_PER_MTOK). Default is a rough gemini-3.1-flash-lite-class blend
/// ($0.25 in / $1.50 out); bump it when pointing PR_REVIEW_MODEL at a pricier model.
pub(crate) const DEFAULT_USD_PER_MTOK: f64 = 0.5;
pub(crate) const MAX_FILES_MAPREDUCE: usize = 40;
pub(crate) const CACHE_KEY: &str = "vaked-ci-reviewer-v1";
pub(crate) const COMMENT_MARKER: &str = "<!-- vaked-pr-review -->";
/// Marker on each inline ```suggestion``` review comment, so re-runs can find and
/// delete their prior suggestions (kept distinct from COMMENT_MARKER).
pub(crate) const AUTOFIX_MARKER: &str = "<!-- vaked-autofix -->";
/// Cap inline suggestions per run so a noisy review can't spam the diff.
pub(crate) const MAX_INLINE_SUGGESTIONS: usize = 10;
pub(crate) const OPT_OUT_LABEL: &str = "no-bot-review";
/// Marker on @vaked-ci conversational replies (distinct from the review/autofix
/// markers — replies form a thread and are never auto-deleted).
pub(crate) const REPLY_MARKER: &str = "<!-- vaked-ci-reply -->";
/// Mention that triggers the interactive responder.
pub(crate) const MENTION: &str = "@vaked-ci";
// Context compaction (item 4): a safety net for the tool loop, not the common
// path — the diff is already char-bounded by `max_diff_chars`. Budget sits well
// above a normal run so compaction only fires on genuine overflow; truncation
// keeps the system prompt + the most-recent events.
pub(crate) const COMPACTION_BUDGET_TOKENS: usize = 160_000;
pub(crate) const COMPACTION_PRESERVE_RECENT: usize = 8;

/// Agent version (from Cargo.toml) — always stamped in the posted comment footer.
pub(crate) const VERSION: &str = env!("CARGO_PKG_VERSION");
pub(crate) const GIT_SHA: &str = env!("GIT_SHA");
/// Compact build stamp for the footer: `v<semver>+<short-sha>`. No PII.
pub(crate) fn footer_signature() -> String {
    format!("v{VERSION}+{GIT_SHA}")
}
