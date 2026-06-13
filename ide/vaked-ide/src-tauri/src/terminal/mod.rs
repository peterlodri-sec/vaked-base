//! Embedded native terminal subsystem (libghostty).
//!
//! See `docs/terminal-embedding.md`. The embedded surface is macOS-only,
//! compiled under `--features ghostty`. Everything else falls back to an
//! external Ghostty / `$TERMINAL` window. The Tauri command surface
//! (`commands::terminal`) is identical on every platform.

#[cfg(all(feature = "ghostty", target_os = "macos"))]
pub mod ffi;
#[cfg(all(feature = "ghostty", target_os = "macos"))]
pub mod macos;
#[cfg(all(feature = "ghostty", target_os = "macos"))]
pub mod runtime;
