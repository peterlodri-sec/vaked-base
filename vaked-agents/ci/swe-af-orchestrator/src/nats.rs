//! NATS JetStream: connect, ensure the work-queue stream + durable pull consumer.

use anyhow::{Result, anyhow};
use async_nats::jetstream::{
    self,
    consumer::{AckPolicy, PullConsumer, pull},
    stream::{Config as StreamCfg, RetentionPolicy},
};

/// A work-queue stream: each message is delivered to exactly one consumer and
/// removed once acked.
pub fn stream_config(name: &str, subject: &str) -> StreamCfg {
    StreamCfg {
        name: name.to_string(),
        subjects: vec![subject.to_string()],
        retention: RetentionPolicy::WorkQueue,
        ..Default::default()
    }
}

pub async fn connect(url: &str, creds: Option<&str>) -> Result<async_nats::Client> {
    match creds {
        Some(path) => async_nats::ConnectOptions::with_credentials_file(path)
            .await
            .map_err(|e| anyhow!("nats creds {path}: {e}"))?
            .connect(url)
            .await
            .map_err(|e| anyhow!("nats connect {url}: {e}")),
        None => async_nats::connect(url)
            .await
            .map_err(|e| anyhow!("nats connect {url}: {e}")),
    }
}

/// Idempotently ensure the stream and a durable explicit-ack pull consumer
/// (the only valid ack policy for pull/work-queue), with bounded redelivery.
pub async fn ensure_consumer(
    js: &jetstream::Context,
    stream: &str,
    subject: &str,
    durable: &str,
) -> Result<PullConsumer> {
    let s = js
        .get_or_create_stream(stream_config(stream, subject))
        .await
        .map_err(|e| anyhow!("get_or_create_stream: {e}"))?;
    let c = s
        .get_or_create_consumer(
            durable,
            pull::Config {
                durable_name: Some(durable.to_string()),
                ack_policy: AckPolicy::Explicit,
                ack_wait: std::time::Duration::from_secs(3600),
                max_deliver: 3,
                ..Default::default()
            },
        )
        .await
        .map_err(|e| anyhow!("get_or_create_consumer: {e}"))?;
    Ok(c)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stream_cfg_is_workqueue() {
        let c = stream_config("SWE_AF_TASKS", "swe.af.tasks");
        assert_eq!(c.name, "SWE_AF_TASKS");
        assert_eq!(c.subjects, vec!["swe.af.tasks".to_string()]);
        assert!(matches!(c.retention, RetentionPolicy::WorkQueue));
    }
}
