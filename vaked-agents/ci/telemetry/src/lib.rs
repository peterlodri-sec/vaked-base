//! Shared Langfuse OTLP/HTTP tracing setup for the vaked CI agents.
//!
//! Single source of truth for the Langfuse env resolution. This logic used to be
//! copy-pasted into provost / label-tagger / pr-review and drifted: provost and
//! label-tagger were stuck on the legacy `LANGFUSE_URL` / `LANGFUSE_API_KEY`
//! names, which don't exist in the `ci` environment, so their tracing silently
//! no-op'd. Everyone now calls [`setup_tracing`].

use std::collections::HashMap;
use std::io::IsTerminal as _;

use base64::Engine as _;
use base64::engine::general_purpose::STANDARD as BASE64;
use opentelemetry::trace::TracerProvider as _;
use opentelemetry_otlp::{WithExportConfig, WithHttpConfig};
use opentelemetry_sdk::trace::SdkTracerProvider;
use tracing::info;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;

/// First non-empty value among `keys`.
fn env_first(keys: &[&str]) -> Option<String> {
    for k in keys {
        if let Ok(v) = std::env::var(k) {
            if !v.is_empty() {
                return Some(v);
            }
        }
    }
    None
}

/// Wire the OTLP/HTTP exporter to self-hosted Langfuse and install the global
/// tracer provider + a `tracing` subscriber. Returns the provider so the caller
/// can `.shutdown()` to flush spans before a short-lived process exits.
///
/// The stderr fmt subscriber is **always** installed (CI visibility even without
/// Langfuse). ANSI color is disabled when stderr is not a TTY or `NO_COLOR` is set.
/// Returns `None` (OTLP off) when no Langfuse base URL is configured.
///
/// - Base URL: `LANGFUSE_HOST` → `LANGFUSE_BASE_URL` → legacy `LANGFUSE_URL`.
/// - Auth: legacy `LANGFUSE_API_KEY` (a ready-made Basic token) else the Basic
///   token built from the standard `LANGFUSE_PUBLIC_KEY` : `LANGFUSE_SECRET_KEY`
///   pair (the keys that actually live in the `ci` environment).
pub fn setup_tracing(service_name: &str, tracer_name: &str) -> Option<SdkTracerProvider> {
    let use_ansi = std::io::stderr().is_terminal() && std::env::var("NO_COLOR").is_err();
    let filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info"));
    let fmt_layer = tracing_subscriber::fmt::layer()
        .with_writer(std::io::stderr)
        .with_ansi(use_ansi);

    let Some(base) = env_first(&["LANGFUSE_HOST", "LANGFUSE_BASE_URL", "LANGFUSE_URL"]) else {
        // No Langfuse configured — still install stderr fmt subscriber for CI visibility.
        tracing_subscriber::registry()
            .with(filter)
            .with(fmt_layer)
            .try_init()
            .ok();
        return None;
    };

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
            // Exporter init failed — fall back to fmt-only subscriber.
            eprintln!("vaked-telemetry: Langfuse exporter init failed, OTLP off: {e}");
            tracing_subscriber::registry()
                .with(filter)
                .with(fmt_layer)
                .try_init()
                .ok();
            return None;
        }
    };

    let resource = opentelemetry_sdk::Resource::builder_empty()
        .with_attributes([opentelemetry::KeyValue::new(
            "service.name",
            service_name.to_string(),
        )])
        .build();
    let provider = SdkTracerProvider::builder()
        .with_batch_exporter(exporter)
        .with_resource(resource)
        .build();

    let tracer = provider.tracer(tracer_name.to_string());
    tracing_subscriber::registry()
        .with(filter)
        .with(fmt_layer)
        .with(tracing_opentelemetry::layer().with_tracer(tracer))
        .try_init()
        .ok();
    opentelemetry::global::set_tracer_provider(provider.clone());
    info!(langfuse.endpoint = %endpoint, service = service_name, "Langfuse tracing enabled");
    Some(provider)
}
