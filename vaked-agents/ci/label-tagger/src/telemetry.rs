//! Tracing → self-hosted Langfuse, via the shared `vaked-telemetry` crate
//! (single source of truth for the LANGFUSE_* env resolution).

use opentelemetry_sdk::trace::SdkTracerProvider;

pub(crate) fn setup_tracing() -> Option<SdkTracerProvider> {
    vaked_telemetry::setup_tracing("vaked-label-tagger", "vaked-label-tagger")
}
