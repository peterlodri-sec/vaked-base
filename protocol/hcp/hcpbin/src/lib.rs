//! hcpbin — binary codec for HCP (RFC 0002).
//!
//! Stub. Implementation starts WP3-S1 (Jun 24 2026).
//! See protocol/rfcs/0002-hcplang.md §4 for the wire format.

/// Encode a HCP frame to bytes. (stub)
pub fn encode(_frame: &[u8]) -> Vec<u8> {
    unimplemented!("WP3-S1: implement per RFC 0002 §4")
}

/// Decode a HCP frame from bytes. (stub)
pub fn decode(_bytes: &[u8]) -> Result<Vec<u8>, DecodeError> {
    unimplemented!("WP3-S1: implement per RFC 0002 §4")
}

#[derive(Debug)]
pub struct DecodeError(pub String);
