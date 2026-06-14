//! Shared constants.

pub(crate) const DEFAULT_MODEL: &str = "openai/gpt-oss-120b";
pub(crate) const DEFAULT_BASE_URL: &str = "https://openrouter.ai/api/v1";
pub(crate) const DEFAULT_MAX_ITERS: u32 = 6;
pub(crate) const COMPACTION_BUDGET_TOKENS: usize = 80_000;
pub(crate) const COMPACTION_PRESERVE_RECENT: usize = 4;
pub(crate) const CACHE_KEY: &str = "vaked-label-tagger-v1";
pub(crate) const OPT_OUT_LABEL: &str = "no-auto-label";
pub(crate) const COMMENT_MARKER: &str = "<!-- vaked-label-tagger -->";
pub(crate) const MAX_DIFF_CHARS: usize = 16_000;

pub(crate) const VERSION: &str = env!("CARGO_PKG_VERSION");
pub(crate) const GIT_SHA: &str = env!("GIT_SHA");
