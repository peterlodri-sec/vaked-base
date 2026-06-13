pub mod a2a;
pub mod gateway;
pub mod human;

use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::Mutex;

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct Message {
    pub role: String,
    pub content: String,
}

pub struct SessionState {
    pub sessions: Arc<Mutex<HashMap<String, Vec<Message>>>>,
    pub api_key: String,
    pub yjs_port: Arc<Mutex<Option<u16>>>,
}

impl SessionState {
    pub fn new() -> Self {
        let api_key = std::env::var("ANTHROPIC_API_KEY").unwrap_or_default();
        SessionState {
            sessions: Arc::new(Mutex::new(HashMap::new())),
            api_key,
            yjs_port: Arc::new(Mutex::new(None)),
        }
    }
}
