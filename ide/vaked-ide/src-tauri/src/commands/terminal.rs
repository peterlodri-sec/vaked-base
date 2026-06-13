//! Tauri commands for the embedded terminal.
//!
//! These names are stable on every platform. On macOS with `--features
//! ghostty` they drive a real libghostty surface; otherwise they report
//! `embedded: false` and `terminal_open_external` launches an external
//! Ghostty / `$TERMINAL` window. See `docs/terminal-embedding.md`.

use serde::{Deserialize, Serialize};
use tauri::AppHandle;

use crate::error::AppError;

/// Device-independent pane rectangle reported by the webview
/// (`getBoundingClientRect`, top-left origin) plus the display scale factor.
#[derive(Debug, Clone, Copy, Deserialize)]
pub struct TerminalBounds {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
    #[serde(default = "default_scale")]
    pub scale: f64,
}

fn default_scale() -> f64 {
    2.0
}

#[derive(Debug, Clone, Serialize)]
pub struct TerminalAvailability {
    /// True when an embedded native surface is available in this build.
    pub embedded: bool,
    /// Human-readable explanation for the UI's fallback messaging.
    pub reason: String,
}

#[tauri::command]
pub fn terminal_available() -> TerminalAvailability {
    #[cfg(all(feature = "ghostty", target_os = "macos"))]
    {
        TerminalAvailability {
            embedded: true,
            reason: "embedded libghostty surface (macOS)".into(),
        }
    }
    #[cfg(not(all(feature = "ghostty", target_os = "macos")))]
    {
        let reason = if cfg!(target_os = "macos") {
            "built without --features ghostty; using external Ghostty".into()
        } else if cfg!(target_os = "windows") {
            "no libghostty backend on Windows; using external terminal".into()
        } else {
            "libghostty C API has no Linux embedding; using external Ghostty".into()
        };
        TerminalAvailability {
            embedded: false,
            reason,
        }
    }
}

#[tauri::command]
pub async fn terminal_open(
    app: AppHandle,
    bounds: TerminalBounds,
    cwd: Option<String>,
) -> Result<(), AppError> {
    #[cfg(all(feature = "ghostty", target_os = "macos"))]
    {
        use crate::terminal::macos::PaneBounds;
        use crate::terminal::runtime;
        use tauri::Manager;

        let window = app
            .get_webview_window("main")
            .ok_or_else(|| AppError("no main window".into()))?;
        let pb = PaneBounds {
            x: bounds.x,
            y: bounds.y,
            width: bounds.width,
            height: bounds.height,
        };
        let scale = bounds.scale;
        let app2 = app.clone();
        app.run_on_main_thread(move || {
            if let Ok(nsw) = window.ns_window() {
                runtime::open_on_main(&app2, nsw, pb, cwd, scale);
            }
        })
        .map_err(|e| AppError(e.to_string()))?;
        return Ok(());
    }
    #[cfg(not(all(feature = "ghostty", target_os = "macos")))]
    {
        let _ = (&app, &bounds, &cwd);
        Err(AppError("embedded terminal unavailable in this build".into()))
    }
}

#[tauri::command]
pub async fn terminal_set_bounds(app: AppHandle, bounds: TerminalBounds) -> Result<(), AppError> {
    #[cfg(all(feature = "ghostty", target_os = "macos"))]
    {
        use crate::terminal::macos::PaneBounds;
        use crate::terminal::runtime;
        let pb = PaneBounds {
            x: bounds.x,
            y: bounds.y,
            width: bounds.width,
            height: bounds.height,
        };
        let scale = bounds.scale;
        app.run_on_main_thread(move || runtime::set_bounds_on_main(pb, scale))
            .map_err(|e| AppError(e.to_string()))?;
        return Ok(());
    }
    #[cfg(not(all(feature = "ghostty", target_os = "macos")))]
    {
        let _ = (&app, &bounds);
        Ok(())
    }
}

#[tauri::command]
pub async fn terminal_set_focus(app: AppHandle, focused: bool) -> Result<(), AppError> {
    #[cfg(all(feature = "ghostty", target_os = "macos"))]
    {
        use crate::terminal::runtime;
        app.run_on_main_thread(move || runtime::set_focus_on_main(focused))
            .map_err(|e| AppError(e.to_string()))?;
        return Ok(());
    }
    #[cfg(not(all(feature = "ghostty", target_os = "macos")))]
    {
        let _ = (&app, focused);
        Ok(())
    }
}

#[tauri::command]
pub async fn terminal_close(app: AppHandle) -> Result<(), AppError> {
    #[cfg(all(feature = "ghostty", target_os = "macos"))]
    {
        use crate::terminal::runtime;
        app.run_on_main_thread(runtime::close_on_main)
            .map_err(|e| AppError(e.to_string()))?;
        return Ok(());
    }
    #[cfg(not(all(feature = "ghostty", target_os = "macos")))]
    {
        let _ = &app;
        Ok(())
    }
}

/// Fallback path: launch an external Ghostty window (preferred) or the
/// platform terminal, rooted at `cwd`.
#[tauri::command]
pub fn terminal_open_external(cwd: Option<String>) -> Result<(), AppError> {
    use std::process::Command;
    let dir = cwd.unwrap_or_else(|| ".".to_string());

    // 1) Ghostty CLI on PATH (Linux, or macOS with the CLI symlink).
    if Command::new("ghostty")
        .arg(format!("--working-directory={dir}"))
        .spawn()
        .is_ok()
    {
        return Ok(());
    }

    // 2) macOS app bundle.
    #[cfg(target_os = "macos")]
    {
        if Command::new("open")
            .args(["-na", "Ghostty", "--args", "--working-directory", &dir])
            .spawn()
            .is_ok()
        {
            return Ok(());
        }
    }

    // 3) $TERMINAL.
    if let Ok(term) = std::env::var("TERMINAL") {
        if Command::new(&term).current_dir(&dir).spawn().is_ok() {
            return Ok(());
        }
    }

    Err(AppError("could not launch an external terminal".into()))
}
