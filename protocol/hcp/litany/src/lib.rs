//! litany — Litany Wire frame framing + frame header codec (RFC 0003).
//!
//! WP3-S1. This crate implements the **wire-layer** framing that RFC 0002 §4.2 /
//! §6 (scope note) explicitly excludes from `hcpbin`: the byte-level **frame
//! record** delimitation (RFC 0003 §4.1–§4.5) and the **frame header** byte
//! encoding (RFC 0003 §4.4 / §4.4.1). It depends on `hcpbin` for the unsigned
//! LEB128 varint codec (RFC 0002 §6.1) — varints are NOT reimplemented here.
//!
//! ## Scope (RFC 0003)
//! Implemented here:
//! - §4.1  the frame record: `length || frame-bytes`, where
//!   `frame-bytes = header-bytes || body-bytes`. `length` counts `frame-bytes`
//!   only (not its own bytes); a `length` of `0` is illegal.
//! - §4.2  the `length` prefix is a minimal unsigned LEB128 varint (reusing
//!   `hcpbin::encode_uvarint`/`Reader::get_uvarint`); strict decode rejects a
//!   non-minimal/overlong length.
//! - §4.3  the `max_frame` guard: a `length` exceeding the receiver's advertised
//!   `max_frame` is a framing violation, rejected before the body is read.
//! - §4.4 / §4.4.1  the frame header (`kind`/`corr`/`stream`/`seq`/`end`) as an
//!   `hcpbin` record over the reserved `@0` tag space, canonical encode/decode.
//! - §4.5  strict/canonical decode: framing violations (overlong length, length
//!   over `max_frame`, length 0, truncated input, malformed header) are reported
//!   as a structured [`WireError`]. This codec does NOT resynchronise — a caller
//!   that gets a [`WireError`] aborts the connection (§4.5).
//!
//! Out of scope (owned by later sprints / other RFC 0003 sections):
//! - the preamble / handshake / `hcp.wire` schema (§5), chapters/streams
//!   lifecycle (§6), liveness (§7), flow control (§8), fault/`error` taxonomy
//!   (§9). This crate is the framing + header codec only.
//!
//! ## Frame header layout — interpretation note (RFC 0003 §4.4.1)
//! §4.4.1 fixes the header fields and their canonical encoding (ascending tag
//! order; `kind` LEB128; `corr` 16 raw bytes; `stream`/`seq` LEB128 if present;
//! `end` single `0x01` byte if true, omitted if false). Each present field is a
//! tag-prefixed `varint(tag) || value` exactly like an `hcpbin` record
//! (RFC 0002 §6.2): so `kind=0` is `00 00` (tag @0, then varint 0), `corr` is
//! `01 <16 bytes>` (tag @1, then raw), etc.
//!
//! ## Documented spec gaps (RFC 0003 §4.4 / §4.4.1)
//! Three points in RFC 0003 are ambiguous; this is what we implemented and why:
//!
//! 1. **Tag vs. value byte.** The two illustrative byte snippets in §4.4.1
//!    collapse a tag byte and a small value byte into one (`02 # tag @0,
//!    kind=2`), which is internally inconsistent with `02 <stream varint> #
//!    tag @2` in the same block. We follow the **normative decoder invariant**
//!    (steps 1–7) and the RFC 0002 §6.2 record model — the only reading under
//!    which "read the next tag to dispatch" is implementable: every present
//!    header field is `varint(tag) || value`.
//!
//! 2. **Header/body boundary.** §4.4 says the body's author tags are `>= @1`,
//!    while §4.4.1 step 6 says "any tag > @4 begins the frame body". The body is
//!    **opaque to the wire** (§4.1), so the header must be self-delimiting. We
//!    parse the header **positionally** per the decoder invariant: `kind`(@0)
//!    and `corr`(@1) are mandatory and in that order, then `stream`(@2),
//!    `seq`(@3), `end`(@4) are read **only if** the next tag is exactly the
//!    next-expected header tag, in that monotonic order; the first tag that is
//!    not the next expected header field is the start of the opaque body. A
//!    consequence (forced by the spec) is that the tag positions @2/@3/@4 right
//!    after `corr` are header-owned, so a body must not begin with bare @2/@3/@4
//!    there — consistent with §4.4.1 steps 3–6 treating those positions as
//!    header fields.
//!
//! 3. **`seq`/`end` without `stream`.** §4.4.1 step 5 is explicit: `@4` (end) is
//!    INVALID without `@2` (stream), and `@3` (seq) requires `stream`. We treat
//!    these as **framing violations** ([`WireError::MalformedHeader`]), not as a
//!    body start, exactly per the normative step 5.

use hcpbin::{DecodeError, Reader, RecordWriter, Writer};

/// RFC 0003 §5.3 `max_frame` floor: every peer MUST accept at least 64 KiB of
/// `frame-bytes`.
pub const MAX_FRAME_FLOOR: u64 = 65_536;

/// RFC 0003 §5.3 default advertised `max_frame` (1 MiB) for a peer with no
/// reason to choose otherwise.
pub const MAX_FRAME_DEFAULT: u64 = 1_048_576;

/// Frame class — the `kind` header field (RFC 0003 §4.4.1, tag @0, `u8` 0–4).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FrameKind {
    /// 0 = request.
    Request,
    /// 1 = response.
    Response,
    /// 2 = event.
    Event,
    /// 3 = control.
    Control,
    /// 4 = error.
    Error,
}

impl FrameKind {
    fn to_u8(self) -> u8 {
        match self {
            FrameKind::Request => 0,
            FrameKind::Response => 1,
            FrameKind::Event => 2,
            FrameKind::Control => 3,
            FrameKind::Error => 4,
        }
    }

    fn from_u64(v: u64) -> Result<Self, WireError> {
        match v {
            0 => Ok(FrameKind::Request),
            1 => Ok(FrameKind::Response),
            2 => Ok(FrameKind::Event),
            3 => Ok(FrameKind::Control),
            4 => Ok(FrameKind::Error),
            other => Err(WireError::InvalidKind(other)),
        }
    }
}

/// The frame header (RFC 0003 §4.4.1). Supplied and validated by the wire layer.
///
/// `stream`/`seq`/`end` are optional and omitted from the encoding when absent
/// (or, for `end`, when false) per RFC 0002 §6.2 default-omission. §4.4.1's
/// decoder invariant constrains their presence: `end` (@4) is only valid when
/// `stream` (@2) is present, and `seq` (@3) requires `stream` as well.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Header {
    /// Frame class (tag @0).
    pub kind: FrameKind,
    /// Correlation id: 16 raw bytes, RFC 4122 big-endian (tag @1).
    pub corr: [u8; 16],
    /// Multi-frame stream id (tag @2); present only on chunked exchanges.
    pub stream: Option<u64>,
    /// Per-stream monotonic sequence number (tag @3); requires `stream`.
    pub seq: Option<u64>,
    /// Terminal-frame flag (tag @4); requires `stream`. Default false.
    pub end: bool,
}

impl Header {
    /// A single-shot header (no `stream`/`seq`/`end`) of the given class.
    pub fn single_shot(kind: FrameKind, corr: [u8; 16]) -> Self {
        Header {
            kind,
            corr,
            stream: None,
            seq: None,
            end: false,
        }
    }
}

/// Header tag numbers (RFC 0003 §4.4.1).
const TAG_KIND: u64 = 0;
const TAG_CORR: u64 = 1;
const TAG_STREAM: u64 = 2;
const TAG_SEQ: u64 = 3;
const TAG_END: u64 = 4;

/// Errors produced while framing/deframing on the Litany Wire (RFC 0003 §4.5).
///
/// Every variant is a **framing violation**: the receiver could not establish a
/// trustworthy record envelope or header, so the connection MUST be aborted
/// (§4.5 — no mid-stream resync). Variants mirror `hcpbin`'s `DecodeError` style
/// (an exhaustive, comparable enum) and wrap it via [`WireError::Hcpbin`] for
/// errors surfaced by the underlying varint/record codec.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WireError {
    /// A `length` prefix of `0` (§4.1: every frame has a non-empty header).
    ZeroLength,
    /// A `length` greater than the advertised `max_frame` (§4.3); rejected
    /// before the body is read.
    FrameTooLarge { length: u64, max_frame: u64 },
    /// The input ended before the full frame record (`length` octets of
    /// `frame-bytes`) was available (§4.5: truncated record / mid-record EOF).
    Truncated,
    /// A `kind` value outside 0–4 (§4.4.1 decoder invariant step 1).
    InvalidKind(u64),
    /// A required header field was missing or fields were out of order (§4.4.1):
    /// e.g. `kind`/`corr` absent, `end`/`seq` without `stream`, or a non-ascending
    /// header tag.
    MalformedHeader(&'static str),
    /// A `corr` field whose value was not exactly 16 bytes (§4.4.1).
    BadCorrLen(usize),
    /// An error surfaced by the underlying `hcpbin` codec (non-minimal/overlong
    /// length varint, malformed varint header field, etc.) — §4.2 / §4.4.
    Hcpbin(DecodeError),
}

impl core::fmt::Display for WireError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            WireError::ZeroLength => write!(f, "frame length of 0 is illegal"),
            WireError::FrameTooLarge { length, max_frame } => {
                write!(f, "frame length {length} exceeds max_frame {max_frame}")
            }
            WireError::Truncated => write!(f, "truncated frame record"),
            WireError::InvalidKind(v) => write!(f, "invalid frame kind {v} (must be 0..=4)"),
            WireError::MalformedHeader(why) => write!(f, "malformed frame header: {why}"),
            WireError::BadCorrLen(n) => write!(f, "corr must be 16 bytes, found {n}"),
            WireError::Hcpbin(e) => write!(f, "hcpbin codec error: {e}"),
        }
    }
}

impl std::error::Error for WireError {}

impl From<DecodeError> for WireError {
    fn from(e: DecodeError) -> Self {
        WireError::Hcpbin(e)
    }
}

/// Encode a frame header into its canonical `hcpbin` record bytes (§4.4.1).
///
/// Fields are emitted in ascending tag order, optional fields omitted when
/// absent / false. Panics on a logically-impossible header (`seq` or `end` set
/// without `stream`) — that is an encoder bug, not attacker input (§4.4.1's
/// wire-layer guarantees say the wire never constructs such a header).
pub fn encode_header(header: &Header) -> Vec<u8> {
    assert!(
        !(header.seq.is_some() && header.stream.is_none()),
        "seq present without stream (RFC 0003 §4.4.1)"
    );
    assert!(
        !(header.end && header.stream.is_none()),
        "end set without stream (RFC 0003 §4.4.1)"
    );

    let mut w = Writer::new();
    let mut rec = RecordWriter::new(&mut w);

    // @0 kind: LEB128 varint of the u8 value.
    rec.field(TAG_KIND)
        .put_uvarint(u64::from(header.kind.to_u8()));
    // @1 corr: 16 raw bytes, not length-prefixed.
    rec.field(TAG_CORR).put_raw(&header.corr);
    // @2 stream: LEB128 varint if present.
    if let Some(stream) = header.stream {
        rec.field(TAG_STREAM).put_uvarint(stream);
    }
    // @3 seq: LEB128 varint if present.
    if let Some(seq) = header.seq {
        rec.field(TAG_SEQ).put_uvarint(seq);
    }
    // @4 end: single 0x01 byte if true; omitted if false.
    if header.end {
        rec.field(TAG_END).put_raw(&[0x01]);
    }

    w.into_bytes()
}

/// Decode a frame header from the front of `frame_bytes`, returning the header
/// and the number of bytes it consumed (the body begins at that offset).
///
/// The header is parsed **positionally** per the §4.4.1 decoder invariant, NOT
/// as a single ascending record spanning the body. This is required because the
/// **body restarts its own tag space at `@1`** (§4.4: header is "prepended ahead
/// of the body's author tags (`>= @1`)"; §4.4.1 step 6: "any tag > @4 begins the
/// frame body (@1+ tags)"). So a single `hcpbin::RecordReader` over header+body
/// would wrongly reject a body `@1` that follows a header `@2` as a non-ascending
/// tag. Instead: read `kind`(@0) then `corr`(@1) (both mandatory), then the
/// optional `stream`(@2)/`seq`(@3)/`end`(@4) **in order**; the first tag that is
/// not the next expected header tag is the start of the body.
fn decode_header_prefix(frame_bytes: &[u8]) -> Result<(Header, usize), WireError> {
    let mut reader = Reader::new(frame_bytes);

    // @0 kind (mandatory).
    let tag = read_tag(&mut reader)?.ok_or(WireError::MalformedHeader("kind (@0) missing"))?;
    if tag != TAG_KIND {
        return Err(WireError::MalformedHeader(
            "first header tag must be kind (@0)",
        ));
    }
    let kind = FrameKind::from_u64(reader.get_uvarint()?)?;

    // @1 corr (mandatory).
    let tag = read_tag(&mut reader)?.ok_or(WireError::MalformedHeader("corr (@1) missing"))?;
    if tag != TAG_CORR {
        return Err(WireError::MalformedHeader(
            "second header tag must be corr (@1)",
        ));
    }
    let raw = reader.get_raw(16)?;
    let mut corr = [0u8; 16];
    corr.copy_from_slice(raw);

    // Optional @2 stream, @3 seq, @4 end — strictly in order. Header tags @2/@3/@4
    // are single-byte varints, so detect the next field by **peeking one byte**
    // (never decoding a full varint): the body is opaque (§4.1) and may begin with
    // a byte whose continuation bit is set, which a full `get_uvarint` would read
    // forward into the body. The first byte that is not the next-expected header
    // tag (or EOF) begins the body.
    let mut stream: Option<u64> = None;
    let mut seq: Option<u64> = None;
    let mut end = false;
    let mut body_offset;

    loop {
        let before = reader.position();
        if before >= frame_bytes.len() {
            // Header consumed all of frame_bytes; no body.
            body_offset = frame_bytes.len();
            break;
        }
        match frame_bytes[before] {
            t if u64::from(t) == TAG_STREAM && stream.is_none() => {
                reader.get_raw(1)?; // consume the tag byte
                stream = Some(reader.get_uvarint()?);
            }
            t if u64::from(t) == TAG_SEQ && stream.is_some() && seq.is_none() && !end => {
                reader.get_raw(1)?;
                seq = Some(reader.get_uvarint()?);
            }
            t if u64::from(t) == TAG_END && stream.is_some() && !end => {
                reader.get_raw(1)?;
                let byte = reader.get_raw(1)?;
                match byte[0] {
                    0x01 => end = true,
                    // 0x00 is the omittable default — non-canonical when present.
                    other => return Err(WireError::Hcpbin(DecodeError::InvalidBool(other))),
                }
            }
            t if u64::from(t) == TAG_SEQ => {
                // @3 without @2, or after @4: malformed header (not a body start,
                // because a body tag would restart at @1, never reusing @3 here).
                return Err(WireError::MalformedHeader(
                    "seq (@3) requires stream and precedes end",
                ));
            }
            t if u64::from(t) == TAG_END => {
                return Err(WireError::MalformedHeader(
                    "end (@4) requires stream and appears once",
                ));
            }
            _ => {
                // Any other byte begins the opaque body (a body @1+ tag, or a
                // header tag out of the expected order). Leave it for the body.
                body_offset = before;
                break;
            }
        }
    }

    Ok((
        Header {
            kind,
            corr,
            stream,
            seq,
            end,
        },
        body_offset,
    ))
}

/// Read one record-field tag varint (RFC 0002 §6.2 tag prefix) from `reader`,
/// returning `None` at end of input. A malformed tag varint surfaces as a
/// framing violation via [`WireError::Hcpbin`].
fn read_tag(reader: &mut Reader<'_>) -> Result<Option<u64>, WireError> {
    if reader.is_empty() {
        return Ok(None);
    }
    Ok(Some(reader.get_uvarint()?))
}

/// Decode just a frame header from a buffer that is exactly the header bytes
/// (no body). Useful for tests and for the header round-trip. Rejects trailing
/// bytes beyond the header (any tag > @4 would be a body, which is an error
/// here because this entry point asserts "header only").
pub fn decode_header(header_bytes: &[u8]) -> Result<Header, WireError> {
    let (header, consumed) = decode_header_prefix(header_bytes)?;
    if consumed != header_bytes.len() {
        return Err(WireError::MalformedHeader(
            "trailing bytes after header-only input",
        ));
    }
    Ok(header)
}

/// Encode a complete frame record: `varint(length) || header-bytes || body`
/// (RFC 0003 §4.1). `length` counts `frame-bytes` (header + body) only.
///
/// `max_frame` is the receiver's advertised maximum (§4.3); the encoder refuses
/// to produce a record larger than it so a sender never violates the guard.
pub fn encode_frame(header: &Header, body: &[u8], max_frame: u64) -> Result<Vec<u8>, WireError> {
    let header_bytes = encode_header(header);
    let frame_len = header_bytes.len() + body.len();
    let frame_len_u64 = frame_len as u64;
    if frame_len_u64 > max_frame {
        return Err(WireError::FrameTooLarge {
            length: frame_len_u64,
            max_frame,
        });
    }
    // frame_len is always >= 1 (the header is never empty), so it never trips the
    // zero-length rule on the decode side.
    let mut out = hcpbin::encode_uvarint(frame_len_u64);
    out.extend_from_slice(&header_bytes);
    out.extend_from_slice(body);
    Ok(out)
}

/// Decode one frame record from the front of `input`, returning the parsed
/// header, the body bytes, and the number of input bytes the whole record
/// consumed (so a caller can advance to the next record).
///
/// Strict / canonical (§4.2, §4.3, §4.5):
/// - non-minimal/overlong `length` varint -> [`WireError::Hcpbin`]
///   ([`DecodeError::NonMinimal`]/[`DecodeError::Overlong`]).
/// - `length` of 0 -> [`WireError::ZeroLength`].
/// - `length` > `max_frame` -> [`WireError::FrameTooLarge`], **before** the body
///   is read (§4.3).
/// - truncated record (fewer than `length` octets after the prefix) ->
///   [`WireError::Truncated`].
/// - malformed header -> the matching [`WireError`].
pub fn decode_frame(input: &[u8], max_frame: u64) -> Result<(Header, Vec<u8>, usize), WireError> {
    let mut reader = Reader::new(input);
    // §4.2: minimal LEB128 length; hcpbin's get_uvarint enforces minimality.
    let length = reader.get_uvarint()?;
    if length == 0 {
        return Err(WireError::ZeroLength);
    }
    // §4.3: reject an over-large length WITHOUT reading the body.
    if length > max_frame {
        return Err(WireError::FrameTooLarge { length, max_frame });
    }
    let prefix_len = reader.position();
    let frame_len =
        usize::try_from(length).map_err(|_| WireError::FrameTooLarge { length, max_frame })?;
    // §4.5: need exactly `frame_len` octets of frame-bytes available.
    if reader.remaining() < frame_len {
        return Err(WireError::Truncated);
    }
    let frame_bytes = reader.get_raw(frame_len)?;

    let (header, body_offset) = decode_header_prefix(frame_bytes)?;
    let body = frame_bytes[body_offset..].to_vec();
    let consumed = prefix_len + frame_len;
    Ok((header, body, consumed))
}
