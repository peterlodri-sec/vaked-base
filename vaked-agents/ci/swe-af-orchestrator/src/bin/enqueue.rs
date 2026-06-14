//! swe-af-enqueue: publish one Task to the work-queue subject.
//!
//! Usage: swe-af-enqueue --repo owner/name --issue N [--plan-model M] [--code-model M]
//! Reads NATS_URL (+ optional NATS_CREDS / SWE_AF_STREAM / SWE_AF_SUBJECT) from env.

use anyhow::{Result, anyhow};
use uuid::Uuid;
use vaked_swe_af_orchestrator::{config::Config, nats, task::Task};

#[tokio::main]
async fn main() -> Result<()> {
    let mut repo = None;
    let mut issue = None;
    let mut plan_model = None;
    let mut code_model = None;
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--repo" => repo = args.next(),
            "--issue" => {
                issue = args
                    .next()
                    .and_then(|s| s.parse::<u64>().ok())
                    .filter(|n| *n > 0);
            }
            "--plan-model" => plan_model = args.next(),
            "--code-model" => code_model = args.next(),
            "-h" | "--help" => {
                println!(
                    "swe-af-enqueue --repo owner/name --issue N [--plan-model M] [--code-model M]"
                );
                return Ok(());
            }
            other => return Err(anyhow!("unknown arg {other}")),
        }
    }

    let task = Task {
        task_id: Uuid::new_v4().to_string(),
        repo: repo.ok_or_else(|| anyhow!("--repo required"))?,
        issue_number: issue.ok_or_else(|| anyhow!("--issue required (positive integer)"))?,
        plan_model,
        code_model,
        max_files: None,
    };
    // Validate the same way the orchestrator will (fail fast on the producer side).
    let bytes = serde_json::to_vec(&task)?;
    Task::from_json(&bytes)?;

    let cfg = Config::from_env()?;
    let client = nats::connect(&cfg.nats_url, cfg.nats_creds.as_deref()).await?;
    let js = async_nats::jetstream::new(client.clone());
    js.get_or_create_stream(nats::stream_config(&cfg.stream, &cfg.subject))
        .await
        .map_err(|e| anyhow!("ensure stream: {e}"))?;
    js.publish(cfg.subject.clone(), bytes.into())
        .await
        .map_err(|e| anyhow!("publish: {e}"))?
        .await
        .map_err(|e| anyhow!("publish ack: {e}"))?;
    println!(
        "enqueued {} -> {} (issue #{})",
        task.task_id, task.repo, task.issue_number
    );
    Ok(())
}
