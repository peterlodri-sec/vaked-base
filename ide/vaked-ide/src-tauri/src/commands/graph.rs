use std::process::Stdio;
use tauri::AppHandle;
use tokio::process::Command;

use crate::error::AppError;

fn vaked_base(app: &AppHandle) -> String {
    std::env::var("VAKED_BASE").unwrap_or_else(|_| {
        app.path()
            .resource_dir()
            .map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_default()
    })
}

async fn run_vakedc(app: &AppHandle, subcommand: &str, extra_args: &[&str]) -> Result<String, AppError> {
    let base = vaked_base(app);
    let mut cmd = Command::new("python3");
    cmd.arg("-m").arg("vakedc").arg(subcommand);
    for arg in extra_args {
        cmd.arg(arg);
    }
    cmd.env("PYTHONPATH", &base)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let output = cmd.output().await.map_err(|e| AppError(e.to_string()))?;
    if !output.status.success() {
        return Err(AppError(String::from_utf8_lossy(&output.stderr).to_string()));
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

/// Parse a .vaked file → canonical LPG JSON (stdout from `vakedc parse --print`)
#[tauri::command]
pub async fn parse_vaked(file_path: String, app: AppHandle) -> Result<String, AppError> {
    run_vakedc(&app, "parse", &[&file_path, "--print"]).await
}

/// Check a .vaked file → canonical diagnostics JSON.
/// vakedc exits 1 when diagnostics are present; we capture stdout regardless.
#[tauri::command]
pub async fn check_vaked_raw(file_path: String, app: AppHandle) -> Result<String, AppError> {
    let base = vaked_base(&app);
    let output = Command::new("python3")
        .arg("-m").arg("vakedc").arg("check")
        .arg(&file_path).arg("--json")
        .env("PYTHONPATH", &base)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .await
        .map_err(|e| AppError(e.to_string()))?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    if stdout.trim().is_empty() {
        return Err(AppError(String::from_utf8_lossy(&output.stderr).to_string()));
    }
    Ok(stdout)
}

/// Lower a validated .vaked file to artifacts, return list of written paths.
#[tauri::command]
pub async fn lower_vaked(
    file_path: String,
    out_dir: String,
    app: AppHandle,
) -> Result<Vec<String>, AppError> {
    run_vakedc(&app, "lower", &[&file_path, "--out", &out_dir]).await?;

    let mut paths = Vec::new();
    let mut dir = tokio::fs::read_dir(&out_dir)
        .await
        .map_err(|e| AppError(e.to_string()))?;
    while let Some(entry) = dir.next_entry().await.map_err(|e| AppError(e.to_string()))? {
        paths.push(entry.path().to_string_lossy().to_string());
    }
    Ok(paths)
}
