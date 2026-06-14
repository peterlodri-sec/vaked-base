//! Ralph decision ledger reader — surfaces recent track decisions for the agent.

use serde_json::Value;
use std::collections::HashMap;

pub(crate) fn recent_decisions(ledger_path: &str, per_track: usize) -> String {
    let content = match std::fs::read_to_string(ledger_path) {
        Ok(s) => s,
        Err(_) => return format!("(ralph ledger not found at {ledger_path})"),
    };

    // Collect last `per_track` decide events per track (reading in reverse).
    let mut by_track: HashMap<String, Vec<(u64, u64, f64)>> = HashMap::new();
    for line in content.lines().rev() {
        let Ok(v) = serde_json::from_str::<Value>(line) else { continue };
        let p = &v["payload"];
        if p["event"].as_str() != Some("decide") { continue }
        let Some(track) = p["track"].as_str() else { continue };
        let iter = p["iteration"].as_u64().unwrap_or(0);
        let cost = p["cost"].as_f64().unwrap_or(0.0);
        let seq  = v["seq"].as_u64().unwrap_or(0);
        let entries = by_track.entry(track.to_string()).or_default();
        if entries.len() < per_track {
            entries.push((seq, iter, cost));
        }
    }

    if by_track.is_empty() {
        return "(no ralph decisions recorded yet)".to_string();
    }

    let mut tracks: Vec<_> = by_track.into_iter().collect();
    tracks.sort_by_key(|(t, _)| t.clone());

    let mut out = String::from("Ralph track decisions (most recent per track):\n");
    for (track, mut entries) in tracks {
        entries.sort_by_key(|(seq, _, _)| *seq);
        let latest = entries.last().unwrap();
        out.push_str(&format!(
            "  {track}: {} decision(s), latest iter {} (${:.4})\n",
            entries.len(), latest.1, latest.2
        ));
    }
    out
}
