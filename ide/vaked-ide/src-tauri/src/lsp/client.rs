use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout};
use tokio::sync::Mutex;
use tauri::{AppHandle, Emitter};

pub struct LspProcess {
    pub stdin: Arc<Mutex<ChildStdin>>,
    _child: Child,
}

impl LspProcess {
    pub fn new(child: Child, stdout: ChildStdout, stdin: ChildStdin, app: AppHandle) -> Self {
        let stdin = Arc::new(Mutex::new(stdin));
        // Spawn reader task: LSP stdout → Tauri "lsp-message" events
        tokio::spawn(async move {
            let mut reader = BufReader::new(stdout);
            loop {
                // Read Content-Length header
                let mut header_line = String::new();
                if reader.read_line(&mut header_line).await.unwrap_or(0) == 0 {
                    break;
                }
                let header = header_line.trim();
                if !header.starts_with("Content-Length:") {
                    continue;
                }
                let len: usize = header
                    .trim_start_matches("Content-Length:")
                    .trim()
                    .parse()
                    .unwrap_or(0);
                if len == 0 {
                    continue;
                }
                // Read blank line separator
                let mut blank = String::new();
                let _ = reader.read_line(&mut blank).await;

                // Read body
                let mut body = vec![0u8; len];
                if reader.read_exact(&mut body).await.is_err() {
                    break;
                }
                let body_str = String::from_utf8_lossy(&body).to_string();
                let _ = app.emit("lsp-message", body_str);
            }
        });
        LspProcess { stdin, _child: child }
    }
}

pub fn make_lsp_message(body: &str) -> Vec<u8> {
    let header = format!("Content-Length: {}\r\n\r\n", body.len());
    let mut out = header.into_bytes();
    out.extend_from_slice(body.as_bytes());
    out
}
