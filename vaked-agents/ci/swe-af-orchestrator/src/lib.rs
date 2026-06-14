//! swe-af fan-out batch orchestrator library.
//!
//! Drains a NATS JetStream work-queue and runs the existing `vaked-swe-af` agent
//! (plan -> code -> publish) per task inside disk/cgroup-bounded scratch, opening
//! one draft PR per task with eventd audit and live `swe.af.status.*` events.

pub mod config;
pub mod disk;
pub mod eventd;
pub mod lifecycle;
pub mod nats;
pub mod status;
pub mod task;
