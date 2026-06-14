//! swe-af-orchestrator: drain the NATS work-queue, run a bounded pool of
//! swe-af tasks in disk-guarded scratch, publish live status, ack/cleanup.

use std::sync::Arc;

use anyhow::Result;
use async_nats::Client;
use async_nats::jetstream::{self, AckKind};
use futures::StreamExt;
use tokio::sync::Semaphore;
use uuid::Uuid;

use vaked_swe_af_orchestrator::{
    config::Config,
    disk::{self, Guard},
    lifecycle, nats,
    status::{Node, StatusEvent},
    task::Task,
};

async fn publish_status(
    client: &Client,
    prefix: &str,
    task_id: &str,
    node: Node,
    state: &str,
    detail: Option<String>,
) {
    let mut ev = StatusEvent::new(task_id, node, state);
    if let Some(d) = detail {
        ev = ev.with_detail(&d);
    }
    let _ = client.publish(ev.subject(prefix), ev.encode().into()).await;
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()),
        )
        .init();

    if std::env::args().any(|a| a == "--version" || a == "-V") {
        println!(
            "swe-af-orchestrator {}+{}",
            env!("CARGO_PKG_VERSION"),
            env!("GIT_SHA")
        );
        return Ok(());
    }

    let cfg = Arc::new(Config::from_env()?);
    std::fs::create_dir_all(&cfg.scratch)?;

    let client = nats::connect(&cfg.nats_url, cfg.nats_creds.as_deref()).await?;
    let js = jetstream::new(client.clone());
    let consumer = nats::ensure_consumer(&js, &cfg.stream, &cfg.subject, &cfg.consumer).await?;
    let sem = Arc::new(Semaphore::new(cfg.pool));
    let guard = Guard {
        min_free_bytes: cfg.min_free_bytes,
        scratch_cap_bytes: cfg.scratch_cap_bytes,
    };

    tracing::info!(pool = cfg.pool, subject = %cfg.subject, scratch = %cfg.scratch, "orchestrator up");

    let mut messages = consumer.messages().await?;
    loop {
        // Disk guard: pause intake while free space is low or scratch is over cap.
        let scratch = std::path::Path::new(&cfg.scratch);
        let free = disk::free_bytes(scratch).unwrap_or(0);
        let used = disk::dir_size_bytes(scratch);
        if !guard.admits(free, used) {
            tracing::warn!(free, used, "disk guard: pausing intake 30s");
            tokio::time::sleep(std::time::Duration::from_secs(30)).await;
            continue;
        }

        let Some(next) = messages.next().await else {
            tracing::warn!("message stream ended");
            break;
        };
        let msg = match next {
            Ok(m) => m,
            Err(e) => {
                tracing::warn!(%e, "pull error");
                continue;
            }
        };

        let permit = sem.clone().acquire_owned().await.expect("semaphore open");
        let cfg2 = cfg.clone();
        let client2 = client.clone();

        tokio::spawn(async move {
            let _permit = permit;
            let task = match Task::from_json(&msg.payload) {
                Ok(t) => t,
                Err(e) => {
                    tracing::error!(%e, "bad task payload — terminating message");
                    let _ = msg.ack_with(AckKind::Term).await;
                    return;
                }
            };

            let work = std::path::Path::new(&cfg2.scratch).join(format!(
                "{}-{}",
                task.task_id,
                Uuid::new_v4()
            ));
            if let Err(e) = std::fs::create_dir_all(&work) {
                tracing::error!(%e, "scratch mkdir failed");
                let _ = msg.ack_with(AckKind::Nak(None)).await;
                return;
            }

            publish_status(
                &client2,
                &cfg2.status_prefix,
                &task.task_id,
                Node::Run,
                "started",
                None,
            )
            .await;

            match lifecycle::run_task(&cfg2, &task, &work).await {
                Ok(o) => {
                    publish_status(
                        &client2,
                        &cfg2.status_prefix,
                        &task.task_id,
                        Node::Done,
                        "ok",
                        o.pr_url.clone(),
                    )
                    .await;
                    tracing::info!(task = %task.task_id, pr = ?o.pr_url, note = %o.note, "task done");
                    let _ = msg.ack().await;
                }
                Err(e) => {
                    tracing::error!(task = %task.task_id, %e, "task failed");
                    publish_status(
                        &client2,
                        &cfg2.status_prefix,
                        &task.task_id,
                        Node::Error,
                        "failed",
                        Some(format!("{e:#}")),
                    )
                    .await;
                    let _ = msg.ack_with(AckKind::Nak(None)).await;
                }
            }

            // Disk cleanup: drop the task scratch regardless of outcome.
            let _ = std::fs::remove_dir_all(&work);
        });
    }

    Ok(())
}
