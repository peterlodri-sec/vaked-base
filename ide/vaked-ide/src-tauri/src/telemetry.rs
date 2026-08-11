use futures_util::{SinkExt, StreamExt};
use serde::Serialize;
use std::time::Duration;
use tokio::net::TcpListener;
use tokio_tungstenite::accept_async;

#[derive(Serialize)]
pub struct TelemetryPacket {
    pub timestamp: String,
    pub node_id: String,
    pub latency_ms: u64,
    pub memory_mb: f64,
    pub status: String,
}

pub async fn start_telemetry_server(addr: &str) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let listener = TcpListener::bind(addr).await?;
    log::info!("🚀 Telemetry WebSocket Server listening on ws://{}", addr);

    while let Ok((stream, _)) = listener.accept().await {
        tokio::spawn(async move {
            if let Ok(mut ws_stream) = accept_async(stream).await {
                let mut interval = tokio::time::interval(Duration::from_millis(1000));
                loop {
                    interval.tick().await;
                    let packet = TelemetryPacket {
                        timestamp: chrono::Utc::now().to_rfc3339(),
                        node_id: "portail-vaked-dev".to_string(),
                        latency_ms: 15,
                        memory_mb: 142.5,
                        status: "ONLINE".to_string(),
                    };
                    if let Ok(json_str) = serde_json::to_string(&packet) {
                        if ws_stream.send(tokio_tungstenite::tungstenite::Message::Text(json_str.into())).await.is_err() {
                            break;
                        }
                    }
                }
            }
        });
    }
    Ok(())
}
