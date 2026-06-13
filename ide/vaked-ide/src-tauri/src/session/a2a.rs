use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::Arc;

use futures_util::{SinkExt, StreamExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{broadcast, Mutex};
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::{accept_async, WebSocketStream};

type Tx = broadcast::Sender<Vec<u8>>;
type RoomMap = Arc<Mutex<HashMap<String, Tx>>>;

/// Start the Yjs WebSocket relay server on a random port.
/// Returns the port number.
pub async fn start_yjs_relay() -> anyhow::Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let port = listener.local_addr()?.port();
    let rooms: RoomMap = Arc::new(Mutex::new(HashMap::new()));

    tokio::spawn(async move {
        loop {
            if let Ok((stream, addr)) = listener.accept().await {
                let rooms = rooms.clone();
                tokio::spawn(handle_connection(stream, addr, rooms));
            }
        }
    });

    Ok(port)
}

async fn handle_connection(stream: TcpStream, _addr: SocketAddr, rooms: RoomMap) {
    // Extract room name from the URL path query param or use "default"
    let ws_stream = match accept_async(stream).await {
        Ok(ws) => ws,
        Err(_) => return,
    };

    // Use a single broadcast channel per "room" (vaked-source doc)
    let room_name = "vaked-source".to_string();
    let tx = {
        let mut map = rooms.lock().await;
        map.entry(room_name)
            .or_insert_with(|| {
                let (tx, _) = broadcast::channel(64);
                tx
            })
            .clone()
    };
    let mut rx = tx.subscribe();

    let (mut ws_sink, mut ws_source) = ws_stream.split();

    // Forward incoming WS messages to the broadcast channel
    let tx2 = tx.clone();
    tokio::spawn(async move {
        while let Some(Ok(msg)) = ws_source.next().await {
            match msg {
                Message::Binary(data) => {
                    let _ = tx2.send(data.to_vec());
                }
                Message::Close(_) => break,
                _ => {}
            }
        }
    });

    // Forward broadcast messages to this WS client
    while let Ok(data) = rx.recv().await {
        if ws_sink.send(Message::Binary(data.into())).await.is_err() {
            break;
        }
    }
}
