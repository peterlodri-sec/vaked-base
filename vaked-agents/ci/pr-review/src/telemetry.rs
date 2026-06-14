//! Tracing → self-hosted Langfuse, via the shared `vaked-telemetry` crate, plus
//! pr-review-specific per-run trace-link helpers.

use opentelemetry::trace::TraceContextExt as _;
use opentelemetry_sdk::trace::SdkTracerProvider;
use tracing_opentelemetry::OpenTelemetrySpanExt as _;

use crate::config::env_first;

/// Wires the OTLP/HTTP exporter to self-hosted Langfuse via the shared
/// `vaked-telemetry` crate; returns the provider so the caller can flush spans
/// before this short-lived process exits.
pub(crate) fn setup_tracing() -> Option<SdkTracerProvider> {
    vaked_telemetry::setup_tracing("vaked-ci-reviewer", "vaked-pr-review")
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
