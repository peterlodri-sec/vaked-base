//! Shared constants.

pub(crate) use vaked_agents_shared::{
    COMPACTION_BUDGET_TOKENS, COMPACTION_PRESERVE_RECENT, DEFAULT_BASE_URL,
};

pub(crate) const DEFAULT_MODEL: &str = "openai/gpt-oss-120b";
pub(crate) const DEFAULT_MAX_ITERS: u32 = 6;
pub(crate) const CACHE_KEY: &str = "vaked-label-tagger-v1";
pub(crate) const OPT_OUT_LABEL: &str = "no-auto-label";
pub(crate) const COMMENT_MARKER: &str = "<!-- vaked-label-tagger -->";
pub(crate) const MAX_DIFF_CHARS: usize = 16_000;

pub(crate) const VERSION: &str = env!("CARGO_PKG_VERSION");
pub(crate) const GIT_SHA: &str = env!("GIT_SHA");
