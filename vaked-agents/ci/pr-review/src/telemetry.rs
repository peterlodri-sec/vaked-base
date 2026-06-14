//! Tracing → self-hosted Langfuse (OTLP/HTTP) + per-run trace-link helpers.

use std::collections::HashMap;

use base64::Engine as _;
use base64::engine::general_purpose::STANDARD as BASE64;
use opentelemetry::trace::{TraceContextExt as _, TracerProvider as _};
use opentelemetry_otlp::{WithExportConfig, WithHttpConfig};
use opentelemetry_sdk::trace::SdkTracerProvider;
use tracing::info;
use tracing_opentelemetry::OpenTelemetrySpanExt as _;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;

use crate::config::env_first;

/// Wires the OTLP/HTTP exporter to self-hosted Langfuse; returns the provider so
/// the caller can flush spans before this short-lived process exits.
pub(crate) fn setup_tracing() -> Option<SdkTracerProvider> {
    // Base URL: prefer the Langfuse-SDK-standard LANGFUSE_HOST (matches ralph + the
    // `ci` environment secrets), then LANGFUSE_BASE_URL, then the legacy LANGFUSE_URL.
    let base = env_first(&["LANGFUSE_HOST", "LANGFUSE_BASE_URL", "LANGFUSE_URL"])?;

    // Auth: the legacy LANGFUSE_API_KEY is the ready-made Basic token (base64 of
    // `public:secret`); otherwise build it from the standard public/secret key pair
    // (the keys that actually live in the `ci` environment).
    let token = env_first(&["LANGFUSE_API_KEY"]).or_else(|| {
        match (
            env_first(&["LANGFUSE_PUBLIC_KEY"]),
            env_first(&["LANGFUSE_SECRET_KEY"]),
        ) {
            (Some(pk), Some(sk)) => Some(BASE64.encode(format!("{pk}:{sk}"))),
            _ => None,
        }
    });

    let endpoint = format!("{}/api/public/otel/v1/traces", base.trim_end_matches('/'));
    let mut headers = HashMap::new();
    if let Some(token) = token {
        headers.insert("Authorization".to_string(), format!("Basic {token}"));
    }

    let exporter = match opentelemetry_otlp::SpanExporter::builder()
        .with_http()
        .with_endpoint(&endpoint)
        .with_headers(headers)
        .build()
    {
        Ok(e) => e,
        Err(e) => {
            eprintln!("pr-review: Langfuse exporter init failed, tracing off: {e}");
            return None;
        }
    };

    let resource = opentelemetry_sdk::Resource::builder_empty()
        .with_attributes([opentelemetry::KeyValue::new(
            "service.name",
            "vaked-ci-reviewer",
        )])
        .build();
    let provider = SdkTracerProvider::builder()
        .with_batch_exporter(exporter)
        .with_resource(resource)
        .build();

    let tracer = provider.tracer("vaked-pr-review");
    let filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info"));
    tracing_subscriber::registry()
        .with(filter)
        .with(tracing_subscriber::fmt::layer().with_writer(std::io::stderr))
        .with(tracing_opentelemetry::layer().with_tracer(tracer))
        .try_init()
        .ok();
    opentelemetry::global::set_tracer_provider(provider.clone());
    info!(langfuse.endpoint = %endpoint, "Langfuse tracing enabled");
    Some(provider)
}

/// Canonical PR web URL (honours `GITHUB_SERVER_URL` for GHE), used as the
/// `langfuse.trace.metadata.pr_url` link back from a trace to the pull request.
pub(crate) fn pr_html_url(repo: &str, pr: u64) -> String {
    let server = env_first(&["GITHUB_SERVER_URL"]).unwrap_or_else(|| "https://github.com".into());
    format!("{}/{}/pull/{}", server.trim_end_matches('/'), repo, pr)
}

/// Record the review `mode` both as a plain span field (readable CI logs) and as
/// filterable Langfuse trace metadata.
pub(crate) fn record_mode(span: &tracing::Span, mode: &str) {
    span.record("mode", mode);
    span.record("langfuse.trace.metadata.mode", mode);
}

/// Build the `{host}/project/{id}/traces/{trace_id}` deep-link for the current span,
/// so the posted review comment can link back to its Langfuse trace. `None` unless
/// `LANGFUSE_PROJECT_ID` and a Langfuse base URL are both set and tracing is active.
pub(crate) fn langfuse_trace_url(span: &tracing::Span) -> Option<String> {
    let base = env_first(&["LANGFUSE_HOST", "LANGFUSE_BASE_URL", "LANGFUSE_URL"])?;
    let project = env_first(&["LANGFUSE_PROJECT_ID"])?;
    let ctx = span.context();
    let sc = ctx.span().span_context().clone();
    if !sc.is_valid() {
        return None;
    }
    Some(format!(
        "{}/project/{}/traces/{}",
        base.trim_end_matches('/'),
        project,
        sc.trace_id()
    ))
}
