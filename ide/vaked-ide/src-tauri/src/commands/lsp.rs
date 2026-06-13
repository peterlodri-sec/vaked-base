use std::process::Stdio;
use std::sync::Arc;
use tauri::{AppHandle, State};
use tokio::process::Command;
use tokio::sync::Mutex;

use crate::error::{AppError, Result};
use crate::lsp::client::{make_lsp_message, LspProcess};

pub struct LspState {
    pub process: Arc<Mutex<Option<LspProcess>>>,
}

impl LspState {
    pub fn new() -> Self {
        LspState {
            process: Arc::new(Mutex::new(None)),
        }
    }
}

#[tauri::command]
pub async fn start_lsp(
    app: AppHandle,
    state: State<'_, LspState>,
) -> std::result::Result<(), AppError> {
    let vaked_base = std::env::var("VAKED_BASE").unwrap_or_else(|_| {
        app.path()
            .resource_dir()
            .map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_default()
    });

    let mut child = Command::new("python3")
        .arg("-m")
        .arg("vakedc")
        .arg("lsp")
        .env("PYTHONPATH", &vaked_base)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| AppError(format!("failed to start LSP: {e}")))?;

    let stdin = child.stdin.take().ok_or(AppError("no stdin".into()))?;
    let stdout = child.stdout.take().ok_or(AppError("no stdout".into()))?;

    let lsp = LspProcess::new(child, stdout, stdin, app);
    let mut guard = state.process.lock().await;
    *guard = Some(lsp);
    Ok(())
}

#[tauri::command]
pub async fn lsp_send(
    message: String,
    state: State<'_, LspState>,
) -> std::result::Result<(), AppError> {
    let guard = state.process.lock().await;
    if let Some(proc) = guard.as_ref() {
        let bytes = make_lsp_message(&message);
        let mut stdin = proc.stdin.lock().await;
        use tokio::io::AsyncWriteExt;
        stdin
            .write_all(&bytes)
            .await
            .map_err(|e| AppError(e.to_string()))?;
        stdin.flush().await.map_err(|e| AppError(e.to_string()))?;
    }
    Ok(())
}

#[tauri::command]
pub async fn stop_lsp(state: State<'_, LspState>) -> std::result::Result<(), AppError> {
    let mut guard = state.process.lock().await;
    *guard = None; // Drop kills the child
    Ok(())
}
