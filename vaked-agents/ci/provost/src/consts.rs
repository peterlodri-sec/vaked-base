//! Shared constants.

pub(crate) const DEFAULT_MODEL: &str = "deepseek/deepseek-v4-flash";
pub(crate) const DEFAULT_BASE_URL: &str = "https://openrouter.ai/api/v1";
pub(crate) const DEFAULT_MAX_ITERS: u32 = 8;
pub(crate) const COMPACTION_BUDGET_TOKENS: usize = 80_000;
pub(crate) const COMPACTION_PRESERVE_RECENT: usize = 4;
pub(crate) const CACHE_KEY: &str = "vaked-provost-v1";
pub(crate) const EPIC_LABEL: &str = "type/epic";
pub(crate) const RFC_DIR: &str = "protocol/rfcs";
pub(crate) const SPEC_DIR: &str = "docs/superpowers/specs";
pub(crate) const PLAN_DIR: &str = "docs/superpowers/plans";
pub(crate) const MAX_ISSUES: usize = 100;

pub(crate) const VERSION: &str = env!("CARGO_PKG_VERSION");
pub(crate) const GIT_SHA: &str = env!("GIT_SHA");
