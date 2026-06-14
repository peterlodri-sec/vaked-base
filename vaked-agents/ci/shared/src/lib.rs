//! Constants + small helpers shared across all vaked CI agents.

pub mod footer;

pub const DEFAULT_BASE_URL: &str = "https://openrouter.ai/api/v1";
pub const COMPACTION_BUDGET_TOKENS: usize = 80_000;
pub const COMPACTION_PRESERVE_RECENT: usize = 4;
