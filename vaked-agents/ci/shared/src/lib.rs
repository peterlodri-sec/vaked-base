//! Constants + small helpers shared across all vaked CI agents.

pub mod footer;

pub const DEFAULT_BASE_URL: &str = "https://openrouter.ai/api/v1";
pub const COMPACTION_BUDGET_TOKENS: usize = 80_000;
pub const COMPACTION_PRESERVE_RECENT: usize = 4;

// ══════════════════════════════════════════════════════════
// Binary self-verification (Genesis seal check)
// ══════════════════════════════════════════════════════════

/// Verify the binary's genesis seal at startup.
/// Reads own binary, searches for VAKED_SIGN marker.
/// Skip with VAKED_SKIP_VERIFY=1.
pub fn verify_binary() -> Result<(), String> {
    if std::env::var("VAKED_SKIP_VERIFY").is_ok() {
        tracing::info!("binary verification skipped (VAKED_SKIP_VERIFY set)");
        return Ok(());
    }

    let self_path = std::env::current_exe()
        .map_err(|e| format!("cannot resolve self path: {e}"))?;

    let content = std::fs::read(&self_path)
        .map_err(|e| format!("cannot read self: {e}"))?;

    // Check for genesis seal
    let genesis_marker = b"7c242080";
    if !content.windows(8).any(|w| w == genesis_marker) {
        return Err("genesis seal not found in binary".into());
    }

    // Check for VAKED_SIGN marker
    let sign_marker = b"VAKED_SIGN:";
    if let Some(idx) = content.windows(11).position(|w| w == sign_marker) {
        let sign_start = idx + 11;
        let sign_end = content[sign_start..].iter().position(|&b| b == b':').unwrap_or(64);
        let burned_hash = &content[sign_start..sign_start + sign_end];

        // Compute SHA256
        use sha2::{Sha256, Digest};
        let mut hasher = Sha256::new();
        hasher.update(&content);
        let computed = format!("{:x}", hasher.finalize());

        if burned_hash != computed.as_bytes() {
            tracing::error!(
                "binary hash mismatch!\n  burned:  {}\n  computed: {}",
                String::from_utf8_lossy(burned_hash),
                computed
            );
            return Err("binary hash mismatch — tampered binary?".into());
        }

        tracing::info!("binary verified — genesis 7c242080 (burned={})", String::from_utf8_lossy(&burned_hash[..8]));
        return Ok(());
    }

    // No signature — dev build, allow
    tracing::warn!("no VAKED_SIGN in binary — dev build, allowing");
    Ok(())
}
