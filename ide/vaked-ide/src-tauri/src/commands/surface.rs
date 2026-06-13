use std::path::Path;
use tauri::AppHandle;

use crate::error::{AppError, Result};

/// Register vaked-ide as the surface launcher for a declared surface.
/// Writes a surface-launcher.json alongside the .vaked file.
#[tauri::command]
pub async fn register_surface_launcher(
    surface_name: String,
    vaked_file: String,
    app: AppHandle,
) -> std::result::Result<(), AppError> {
    let vaked_path = Path::new(&vaked_file);
    let dir = vaked_path
        .parent()
        .ok_or_else(|| AppError("invalid vaked file path".into()))?;

    let launcher_path = std::env::current_exe()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|_| "vaked-ide".to_string());

    let config = serde_json::json!({
        "surface": surface_name,
        "launcher": launcher_path,
        "args": ["--surface", surface_name, "--vaked-file", vaked_file],
        "registered_at": chrono_now()
    });

    let out_path = dir.join("surface-launcher.json");
    tokio::fs::write(
        &out_path,
        serde_json::to_string_pretty(&config).unwrap_or_default(),
    )
    .await
    .map_err(|e| AppError(e.to_string()))?;

    Ok(())
}

#[tauri::command]
pub async fn open_surface_view(
    surface_name: String,
    vaked_file: String,
    app: AppHandle,
) -> std::result::Result<(), AppError> {
    // Open a new webview window configured as a surface view
    // The SurfaceLauncher component reads the surface_name from the URL params
    let label = format!("surface-{surface_name}");

    use tauri::WebviewWindowBuilder;
    WebviewWindowBuilder::new(
        &app,
        &label,
        tauri::WebviewUrl::App(format!("/surface?name={surface_name}&file={vaked_file}").into()),
    )
    .title(format!("Surface: {surface_name}"))
    .inner_size(1280.0, 800.0)
    .build()
    .map_err(|e| AppError(e.to_string()))?;

    Ok(())
}

fn chrono_now() -> String {
    // Simple timestamp without chrono dependency
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs().to_string())
        .unwrap_or_default()
}
