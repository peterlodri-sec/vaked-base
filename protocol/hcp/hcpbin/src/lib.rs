//! hcpbin — canonical binary codec for HCP values (RFC 0002 §6).
//!
//! WP3-S1 foundation. This module implements the primitive layer of the
//! `hcpbin` value encoding (RFC 0002 §6.1, §6.4, §6.5): unsigned/signed
//! varints, `bool`, `bytes`, and `hash`. The encoding is *canonical* — for a
//! given value there is exactly one valid byte string (§6.8) — so decoders
//! reject any non-canonical form (non-minimal/overlong varints, out-of-range
//! bool bytes, width overflow).
//!
//! ## Scope (RFC 0002)
//! Implemented here:
//! - §6.1  unsigned LEB128 varint (minimal encode, strict decode)
//! - §6.1  signed zig-zag varint with width-bound `k` (i8/i16/i32/i64)
//! - §6.1  `bytes` (varint length prefix + raw bytes)
//! - §6.4  `bool` (0x00/0x01 only)
//! - §6.5  `hash` (`varint(algo) varint(len) digest`, self-delimiting)
//! - §6.4  `string` (NFC-normalised against pinned Unicode 15.1.0, length-prefixed UTF-8)
//! - §6.4  `f32` / `f64` (little-endian IEEE-754, NaN/signed-zero canonicalised)
//! - §5.1  `uuid` (16 raw bytes), `timestamp` (`i64`-ns zig-zag varint)
//!
//! ### String normalisation pin (§6.4)
//! `string` encoding NFC-normalises against **Unicode 15.1.0**, which is pinned
//! via the `unicode-normalization = "=0.1.23"` dependency — that crate version's
//! `UNICODE_VERSION` constant is `(15, 1, 0)`. The pin is part of the canonical
//! encoding (changing it is a protocol-version bump, §6.4). On decode, UTF-8 is
//! validated but NOT re-normalised: per §6.4 a decoder MAY assume NFC, so the
//! bytes round-trip as received (encode-time normalisation, §11 Open-Q7).
//!
//! Out of scope (left as TODO, owned by later sprints):
//! - records / frames / unions / maps / enums (§6.2, §6.6, §6.7).
//! - the frame header (kind/corr/stream/seq/end) — that lives in the WIRE
//!   layer (RFC 0003), explicitly NOT in hcpbin (RFC 0002 §4.2, §6 scope note).
//!
//! ## API note (change from the stub)
//! The previous stub exposed frame-level `encode(&[u8]) -> Vec<u8>` /
//! `decode(&[u8]) -> Result<Vec<u8>, DecodeError>` free functions and a
//! `DecodeError(String)` newtype. Those were placeholders for a wire-frame
//! codec that hcpbin does not own (see §4.2 / §6 scope note). They had no
//! callers anywhere in the workspace, so they are replaced by the typed
//! `Reader`/`Writer` API and a structured `DecodeError` enum below.

use core::fmt;

use unicode_normalization::UnicodeNormalization;

/// Maximum number of LEB128 groups in a 64-bit varint: ceil(64 / 7) = 10.
const MAX_VARINT_LEN: usize = 10;

/// Errors produced while decoding `hcpbin` values.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DecodeError {
    /// The input ended before a value was fully read.
    UnexpectedEof,
    /// A varint used more than 10 bytes for a 64-bit value (§6.1).
    Overlong,
    /// A multi-byte varint had an elidable trailing zero group (§6.1).
    NonMinimal,
    /// A decoded value did not fit the declared integer width (§6.1).
    WidthOverflow,
    /// A `bool` byte was something other than `0x00` or `0x01` (§6.4).
    InvalidBool(u8),
    /// A `hash` with a known `algo-id` declared a digest length that does not
    /// match the registry length for that algorithm (§6.5).
    HashLengthMismatch { algo: u64, expected: usize, found: u64 },
    /// A length/count prefix exceeded what could be addressed on this platform
    /// (a `varint` length larger than `usize`).
    LengthOverflow,
    /// A whole-value decode left unconsumed bytes after the value (§6.8: a
    /// canonical value occupies exactly its bytes).
    TrailingBytes,
    /// A `string`'s length-prefixed bytes were not valid UTF-8 (§6.4).
    InvalidUtf8,
}

impl fmt::Display for DecodeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            DecodeError::UnexpectedEof => write!(f, "unexpected end of input"),
            DecodeError::Overlong => write!(f, "overlong varint (>10 bytes)"),
            DecodeError::NonMinimal => write!(f, "non-minimal varint encoding"),
            DecodeError::WidthOverflow => write!(f, "value exceeds declared integer width"),
            DecodeError::InvalidBool(b) => write!(f, "invalid bool byte 0x{b:02x}"),
            DecodeError::HashLengthMismatch { algo, expected, found } => write!(
                f,
                "hash algo 0x{algo:02x} expects {expected}-byte digest, found {found}"
            ),
            DecodeError::LengthOverflow => write!(f, "length prefix exceeds usize"),
            DecodeError::TrailingBytes => write!(f, "trailing bytes after value"),
            DecodeError::InvalidUtf8 => write!(f, "string is not valid UTF-8"),
        }
    }
}

impl std::error::Error for DecodeError {}

/// A `hash` value: algorithm id, plus the raw digest bytes (§6.5).
///
/// The on-wire `len` is implicit in `digest.len()`. The digest is kept as
/// opaque bytes so that unknown (future) `algo-id`s round-trip byte-for-byte.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Hash {
    /// Algorithm id (§6.5.1). Known: `0x01` = SHA-256, `0x02` = BLAKE3-256.
    pub algo: u64,
    /// Raw digest bytes.
    pub digest: Vec<u8>,
}

/// Registry digest length for a known `algo-id`, or `None` if unknown (§6.5).
fn known_hash_digest_len(algo: u64) -> Option<usize> {
    match algo {
        0x01 => Some(32), // SHA-256
        0x02 => Some(32), // BLAKE3-256
        _ => None,
    }
}

/// A bounds-checked write cursor over a growable byte buffer.
#[derive(Debug, Default)]
pub struct Writer {
    buf: Vec<u8>,
}

impl Writer {
    /// Create an empty writer.
    pub fn new() -> Self {
        Writer { buf: Vec::new() }
    }

    /// Consume the writer and return the encoded bytes.
    pub fn into_bytes(self) -> Vec<u8> {
        self.buf
    }

    /// Borrow the bytes written so far.
    pub fn as_bytes(&self) -> &[u8] {
        &self.buf
    }

    /// Append raw bytes verbatim.
    pub fn put_raw(&mut self, bytes: &[u8]) {
        self.buf.extend_from_slice(bytes);
    }

    /// Encode an unsigned 64-bit integer as a minimal LEB128 varint (§6.1).
    pub fn put_uvarint(&mut self, mut value: u64) {
        loop {
            let group = (value & 0x7f) as u8;
            value >>= 7;
            if value == 0 {
                self.buf.push(group);
                break;
            }
            self.buf.push(group | 0x80);
        }
    }

    /// Encode a signed integer of declared width `k` bits as a zig-zag varint
    /// (§6.1). `value` is the full `i64`; `k` selects the sign-fill shift.
    fn put_ivarint_k(&mut self, value: i64, k: u32) {
        // (n << 1) ^ (n >> (k-1)), with the left shift done unsigned so it
        // wraps at the type max instead of panicking in debug builds.
        let zigzag = ((value as u64) << 1) ^ ((value >> (k - 1)) as u64);
        self.put_uvarint(zigzag);
    }

    /// Encode an `i8` (§6.1, `k=8`).
    pub fn put_i8(&mut self, value: i8) {
        self.put_ivarint_k(value as i64, 8);
    }

    /// Encode an `i16` (§6.1, `k=16`).
    pub fn put_i16(&mut self, value: i16) {
        self.put_ivarint_k(value as i64, 16);
    }

    /// Encode an `i32` (§6.1, `k=32`).
    pub fn put_i32(&mut self, value: i32) {
        self.put_ivarint_k(value as i64, 32);
    }

    /// Encode an `i64` (§6.1, `k=64`).
    pub fn put_i64(&mut self, value: i64) {
        self.put_ivarint_k(value, 64);
    }

    /// Encode a `bool` as a single byte `0x00`/`0x01` (§6.4).
    pub fn put_bool(&mut self, value: bool) {
        self.buf.push(value as u8);
    }

    /// Encode `bytes`: `varint(len)` followed by the raw bytes (§6.1).
    pub fn put_bytes(&mut self, bytes: &[u8]) {
        self.put_uvarint(bytes.len() as u64);
        self.buf.extend_from_slice(bytes);
    }

    /// Encode a `hash`: `varint(algo) varint(len) digest` (§6.5).
    pub fn put_hash(&mut self, hash: &Hash) {
        self.put_uvarint(hash.algo);
        self.put_uvarint(hash.digest.len() as u64);
        self.buf.extend_from_slice(&hash.digest);
    }

    /// Encode a `string`: NFC-normalise (pinned Unicode 15.1.0, §6.4), then emit
    /// `varint(byte-len)` followed by the normalised UTF-8 bytes (§5.1, §6.1.1).
    pub fn put_string(&mut self, value: &str) {
        let normalised: String = value.nfc().collect();
        self.put_uvarint(normalised.len() as u64);
        self.buf.extend_from_slice(normalised.as_bytes());
    }

    /// Encode an `f32` as little-endian IEEE-754, canonicalising NaN to the quiet
    /// pattern `0x7FC00000` and `-0.0` to `+0.0` (§6.4).
    pub fn put_f32(&mut self, value: f32) {
        let canonical = if value.is_nan() {
            f32::from_bits(0x7FC0_0000)
        } else if value == 0.0 {
            // Collapses both +0.0 and -0.0 (they compare equal) to +0.0.
            0.0
        } else {
            value
        };
        self.buf.extend_from_slice(&canonical.to_le_bytes());
    }

    /// Encode an `f64` as little-endian IEEE-754, canonicalising NaN to the quiet
    /// pattern `0x7FF8000000000000` and `-0.0` to `+0.0` (§6.4).
    pub fn put_f64(&mut self, value: f64) {
        let canonical = if value.is_nan() {
            f64::from_bits(0x7FF8_0000_0000_0000)
        } else if value == 0.0 {
            0.0
        } else {
            value
        };
        self.buf.extend_from_slice(&canonical.to_le_bytes());
    }

    /// Encode a `uuid` as 16 raw bytes, with no endianness applied (§5.1).
    pub fn put_uuid(&mut self, value: &[u8; 16]) {
        self.buf.extend_from_slice(value);
    }

    /// Encode a `timestamp` (`i64` nanoseconds since the Unix epoch) as a zig-zag
    /// varint (§5.1, `k=64`).
    pub fn put_timestamp(&mut self, nanos: i64) {
        self.put_i64(nanos);
    }
}

/// A bounds-checked read cursor over a borrowed byte slice.
#[derive(Debug, Clone)]
pub struct Reader<'a> {
    buf: &'a [u8],
    pos: usize,
}

impl<'a> Reader<'a> {
    /// Create a reader positioned at the start of `buf`.
    pub fn new(buf: &'a [u8]) -> Self {
        Reader { buf, pos: 0 }
    }

    /// Current read offset.
    pub fn position(&self) -> usize {
        self.pos
    }

    /// Number of unread bytes remaining.
    pub fn remaining(&self) -> usize {
        self.buf.len() - self.pos
    }

    /// True once the whole input has been consumed.
    pub fn is_empty(&self) -> bool {
        self.pos >= self.buf.len()
    }

    /// Read exactly `n` raw bytes, advancing the cursor.
    pub fn get_raw(&mut self, n: usize) -> Result<&'a [u8], DecodeError> {
        let end = self.pos.checked_add(n).ok_or(DecodeError::LengthOverflow)?;
        if end > self.buf.len() {
            return Err(DecodeError::UnexpectedEof);
        }
        let out = &self.buf[self.pos..end];
        self.pos = end;
        Ok(out)
    }

    /// Decode an unsigned LEB128 varint into a `u64`, enforcing minimal /
    /// non-overlong encoding (§6.1).
    pub fn get_uvarint(&mut self) -> Result<u64, DecodeError> {
        let mut result: u64 = 0;
        let mut shift: u32 = 0;
        let mut group_count: usize = 0;

        loop {
            if self.pos >= self.buf.len() {
                return Err(DecodeError::UnexpectedEof);
            }
            let byte = self.buf[self.pos];
            self.pos += 1;
            group_count += 1;

            if group_count > MAX_VARINT_LEN {
                return Err(DecodeError::Overlong);
            }

            let payload = (byte & 0x7f) as u64;

            // The 10th byte may only contribute bit 63: a 7-bit group with any
            // bit above bit 0 set would overflow u64.
            if group_count == MAX_VARINT_LEN && payload > 1 {
                return Err(DecodeError::WidthOverflow);
            }

            result |= payload << shift;

            if byte & 0x80 == 0 {
                // Final group. A multi-byte varint whose last group is zero
                // could have been encoded shorter, so it is non-minimal.
                // (A single 0x00 byte legitimately encodes the value 0.)
                if group_count > 1 && payload == 0 {
                    return Err(DecodeError::NonMinimal);
                }
                return Ok(result);
            }

            shift += 7;
        }
    }

    /// Decode an unsigned varint that must fit `bits` (8/16/32/64).
    fn get_uvarint_width(&mut self, bits: u32) -> Result<u64, DecodeError> {
        let value = self.get_uvarint()?;
        if bits < 64 && value > (u64::MAX >> (64 - bits)) {
            return Err(DecodeError::WidthOverflow);
        }
        Ok(value)
    }

    /// Decode a `u8` (§6.1).
    pub fn get_u8(&mut self) -> Result<u8, DecodeError> {
        Ok(self.get_uvarint_width(8)? as u8)
    }

    /// Decode a `u16` (§6.1).
    pub fn get_u16(&mut self) -> Result<u16, DecodeError> {
        Ok(self.get_uvarint_width(16)? as u16)
    }

    /// Decode a `u32` (§6.1).
    pub fn get_u32(&mut self) -> Result<u32, DecodeError> {
        Ok(self.get_uvarint_width(32)? as u32)
    }

    /// Decode a `u64` (§6.1).
    pub fn get_u64(&mut self) -> Result<u64, DecodeError> {
        self.get_uvarint()
    }

    /// Decode a zig-zag signed varint of declared width `bits` (8/16/32/64),
    /// rejecting values that exceed that width (§6.1).
    fn get_ivarint_width(&mut self, bits: u32) -> Result<i64, DecodeError> {
        // The zig-zag mapping of a width-`k` signed value occupies exactly `k`
        // unsigned bits, so bound the raw varint to that width first.
        let zigzag = self.get_uvarint_width(bits)?;
        // Un-zigzag: (z >> 1) ^ -(z & 1).
        Ok(((zigzag >> 1) as i64) ^ -((zigzag & 1) as i64))
    }

    /// Decode an `i8` (§6.1, `k=8`).
    pub fn get_i8(&mut self) -> Result<i8, DecodeError> {
        Ok(self.get_ivarint_width(8)? as i8)
    }

    /// Decode an `i16` (§6.1, `k=16`).
    pub fn get_i16(&mut self) -> Result<i16, DecodeError> {
        Ok(self.get_ivarint_width(16)? as i16)
    }

    /// Decode an `i32` (§6.1, `k=32`).
    pub fn get_i32(&mut self) -> Result<i32, DecodeError> {
        Ok(self.get_ivarint_width(32)? as i32)
    }

    /// Decode an `i64` (§6.1, `k=64`).
    pub fn get_i64(&mut self) -> Result<i64, DecodeError> {
        self.get_ivarint_width(64)
    }

    /// Decode a `bool`, rejecting any byte other than `0x00`/`0x01` (§6.4).
    pub fn get_bool(&mut self) -> Result<bool, DecodeError> {
        let byte = *self.get_raw(1)?.first().expect("get_raw(1) yields one byte");
        match byte {
            0x00 => Ok(false),
            0x01 => Ok(true),
            other => Err(DecodeError::InvalidBool(other)),
        }
    }

    /// Decode `bytes`: `varint(len)` then `len` raw bytes (§6.1).
    pub fn get_bytes(&mut self) -> Result<&'a [u8], DecodeError> {
        let len = self.get_uvarint()?;
        let len = usize::try_from(len).map_err(|_| DecodeError::LengthOverflow)?;
        self.get_raw(len)
    }

    /// Decode a `hash`: `varint(algo) varint(len) digest` (§6.5).
    ///
    /// For a known `algo-id`, `len` MUST equal the registry digest length;
    /// unknown algorithms round-trip with their declared `len`.
    pub fn get_hash(&mut self) -> Result<Hash, DecodeError> {
        let algo = self.get_uvarint()?;
        let len = self.get_uvarint()?;
        if let Some(expected) = known_hash_digest_len(algo) {
            if len != expected as u64 {
                return Err(DecodeError::HashLengthMismatch { algo, expected, found: len });
            }
        }
        let len = usize::try_from(len).map_err(|_| DecodeError::LengthOverflow)?;
        let digest = self.get_raw(len)?.to_vec();
        Ok(Hash { algo, digest })
    }

    /// Decode a `string`: `varint(byte-len)` then `len` UTF-8 bytes (§5.1,
    /// §6.1.1). UTF-8 is validated; invalid sequences are rejected. Per §6.4 the
    /// decoder MAY assume NFC, so the bytes are returned as-is without
    /// re-normalisation (see the module/`notes` posture statement).
    pub fn get_string(&mut self) -> Result<String, DecodeError> {
        let len = self.get_uvarint()?;
        let len = usize::try_from(len).map_err(|_| DecodeError::LengthOverflow)?;
        let bytes = self.get_raw(len)?;
        core::str::from_utf8(bytes)
            .map(str::to_owned)
            .map_err(|_| DecodeError::InvalidUtf8)
    }

    /// Decode an `f32` from 4 little-endian IEEE-754 bytes (§5.1, §6.4). Bits are
    /// read as-is; canonicalisation is an encode-time operation.
    pub fn get_f32(&mut self) -> Result<f32, DecodeError> {
        let bytes = self.get_raw(4)?;
        Ok(f32::from_le_bytes(bytes.try_into().expect("get_raw(4) yields four bytes")))
    }

    /// Decode an `f64` from 8 little-endian IEEE-754 bytes (§5.1, §6.4). Bits are
    /// read as-is; canonicalisation is an encode-time operation.
    pub fn get_f64(&mut self) -> Result<f64, DecodeError> {
        let bytes = self.get_raw(8)?;
        Ok(f64::from_le_bytes(bytes.try_into().expect("get_raw(8) yields eight bytes")))
    }

    /// Decode a `uuid`: 16 raw bytes, no endianness applied (§5.1).
    pub fn get_uuid(&mut self) -> Result<[u8; 16], DecodeError> {
        let bytes = self.get_raw(16)?;
        Ok(bytes.try_into().expect("get_raw(16) yields sixteen bytes"))
    }

    /// Decode a `timestamp` (`i64` nanoseconds) from a zig-zag varint (§5.1).
    pub fn get_timestamp(&mut self) -> Result<i64, DecodeError> {
        self.get_i64()
    }
}

// ---------------------------------------------------------------------------
// Free-function API (the surface fixed by `tests/golden.rs`).
//
// Each `decode_*` is a *whole-value* decode: it reads exactly one value and
// errors with `TrailingBytes` if any input remains, so a canonical encoding is
// the unique consume-all decode of its bytes (§6.8). These are thin wrappers
// over `Reader`/`Writer`.
// ---------------------------------------------------------------------------

/// Decode exactly one value from `bytes`, rejecting any leftover input.
fn decode_all<T, F>(bytes: &[u8], f: F) -> Result<T, DecodeError>
where
    F: FnOnce(&mut Reader<'_>) -> Result<T, DecodeError>,
{
    let mut r = Reader::new(bytes);
    let value = f(&mut r)?;
    if !r.is_empty() {
        return Err(DecodeError::TrailingBytes);
    }
    Ok(value)
}

/// Encode an unsigned 64-bit integer as a minimal LEB128 varint (§6.1).
pub fn encode_uvarint(value: u64) -> Vec<u8> {
    let mut w = Writer::new();
    w.put_uvarint(value);
    w.into_bytes()
}

/// Decode a minimal LEB128 varint (§6.1).
pub fn decode_uvarint(bytes: &[u8]) -> Result<u64, DecodeError> {
    decode_all(bytes, |r| r.get_uvarint())
}

/// Encode an `i8` (§6.1, `k=8`).
pub fn encode_i8(value: i8) -> Vec<u8> {
    let mut w = Writer::new();
    w.put_i8(value);
    w.into_bytes()
}

/// Decode an `i8` (§6.1, `k=8`).
pub fn decode_i8(bytes: &[u8]) -> Result<i8, DecodeError> {
    decode_all(bytes, |r| r.get_i8())
}

/// Encode an `i16` (§6.1, `k=16`).
pub fn encode_i16(value: i16) -> Vec<u8> {
    let mut w = Writer::new();
    w.put_i16(value);
    w.into_bytes()
}

/// Decode an `i16` (§6.1, `k=16`).
pub fn decode_i16(bytes: &[u8]) -> Result<i16, DecodeError> {
    decode_all(bytes, |r| r.get_i16())
}

/// Encode an `i32` (§6.1, `k=32`).
pub fn encode_i32(value: i32) -> Vec<u8> {
    let mut w = Writer::new();
    w.put_i32(value);
    w.into_bytes()
}

/// Decode an `i32` (§6.1, `k=32`).
pub fn decode_i32(bytes: &[u8]) -> Result<i32, DecodeError> {
    decode_all(bytes, |r| r.get_i32())
}

/// Encode an `i64` (§6.1, `k=64`).
pub fn encode_i64(value: i64) -> Vec<u8> {
    let mut w = Writer::new();
    w.put_i64(value);
    w.into_bytes()
}

/// Decode an `i64` (§6.1, `k=64`).
pub fn decode_i64(bytes: &[u8]) -> Result<i64, DecodeError> {
    decode_all(bytes, |r| r.get_i64())
}

/// Encode a `bool` as a single byte `0x00`/`0x01` (§6.4).
pub fn encode_bool(value: bool) -> Vec<u8> {
    let mut w = Writer::new();
    w.put_bool(value);
    w.into_bytes()
}

/// Decode a `bool`, rejecting any byte other than `0x00`/`0x01` (§6.4).
pub fn decode_bool(bytes: &[u8]) -> Result<bool, DecodeError> {
    decode_all(bytes, |r| r.get_bool())
}

/// Encode `bytes`: `varint(len)` followed by the raw bytes (§6.1).
pub fn encode_bytes(bytes: &[u8]) -> Vec<u8> {
    let mut w = Writer::new();
    w.put_bytes(bytes);
    w.into_bytes()
}

/// Decode `bytes`: `varint(len)` then `len` raw bytes (§6.1).
pub fn decode_bytes(bytes: &[u8]) -> Result<Vec<u8>, DecodeError> {
    decode_all(bytes, |r| r.get_bytes().map(<[u8]>::to_vec))
}

/// Encode a `hash`: `varint(algo) varint(len) digest` (§6.5).
pub fn encode_hash(algo: u8, digest: &[u8]) -> Vec<u8> {
    let mut w = Writer::new();
    w.put_hash(&Hash { algo: algo as u64, digest: digest.to_vec() });
    w.into_bytes()
}

/// Decode a `hash` into `(algo, digest)` (§6.5). For a known `algo-id`, `len`
/// MUST equal the registry digest length; unknown algorithms round-trip.
pub fn decode_hash(bytes: &[u8]) -> Result<(u8, Vec<u8>), DecodeError> {
    let hash = decode_all(bytes, |r| r.get_hash())?;
    let algo = u8::try_from(hash.algo).map_err(|_| DecodeError::WidthOverflow)?;
    Ok((algo, hash.digest))
}

/// Encode a `string`: NFC-normalise to pinned Unicode 15.1.0, then
/// `varint(byte-len)` + UTF-8 bytes (§5.1, §6.4).
pub fn encode_string(value: &str) -> Vec<u8> {
    let mut w = Writer::new();
    w.put_string(value);
    w.into_bytes()
}

/// Decode a `string`: `varint(byte-len)` then validated UTF-8 (§5.1, §6.4).
pub fn decode_string(bytes: &[u8]) -> Result<String, DecodeError> {
    decode_all(bytes, |r| r.get_string())
}

/// Encode an `f32` as canonical little-endian IEEE-754 (§5.1, §6.4).
pub fn encode_f32(value: f32) -> Vec<u8> {
    let mut w = Writer::new();
    w.put_f32(value);
    w.into_bytes()
}

/// Decode an `f32` from 4 little-endian IEEE-754 bytes (§5.1, §6.4).
pub fn decode_f32(bytes: &[u8]) -> Result<f32, DecodeError> {
    decode_all(bytes, |r| r.get_f32())
}

/// Encode an `f64` as canonical little-endian IEEE-754 (§5.1, §6.4).
pub fn encode_f64(value: f64) -> Vec<u8> {
    let mut w = Writer::new();
    w.put_f64(value);
    w.into_bytes()
}

/// Decode an `f64` from 8 little-endian IEEE-754 bytes (§5.1, §6.4).
pub fn decode_f64(bytes: &[u8]) -> Result<f64, DecodeError> {
    decode_all(bytes, |r| r.get_f64())
}

/// Encode a `uuid` as 16 raw bytes, no endianness applied (§5.1).
pub fn encode_uuid(value: &[u8; 16]) -> Vec<u8> {
    let mut w = Writer::new();
    w.put_uuid(value);
    w.into_bytes()
}

/// Decode a `uuid`: exactly 16 raw bytes (§5.1).
pub fn decode_uuid(bytes: &[u8]) -> Result<[u8; 16], DecodeError> {
    decode_all(bytes, |r| r.get_uuid())
}

/// Encode a `timestamp` (`i64` nanoseconds) as a zig-zag varint (§5.1).
pub fn encode_timestamp(nanos: i64) -> Vec<u8> {
    let mut w = Writer::new();
    w.put_timestamp(nanos);
    w.into_bytes()
}

/// Decode a `timestamp` (`i64` nanoseconds) from a zig-zag varint (§5.1).
pub fn decode_timestamp(bytes: &[u8]) -> Result<i64, DecodeError> {
    decode_all(bytes, |r| r.get_timestamp())
}

// TODO: records/frames (§6.2), defaults/optionals (§6.3), lists/maps (§6.6),
// unions/enums (§6.7).
//
// TODO: the frame header (kind/corr/stream/seq/end) is the WIRE layer's
// concern (RFC 0003), NOT hcpbin (RFC 0002 §4.2 / §6 scope note).

#[cfg(test)]
mod tests {
    use super::*;

    fn enc<F: FnOnce(&mut Writer)>(f: F) -> Vec<u8> {
        let mut w = Writer::new();
        f(&mut w);
        w.into_bytes()
    }

    // ---- §6.1.1 unsigned varint golden vectors ----

    #[test]
    fn uvarint_golden() {
        assert_eq!(enc(|w| w.put_uvarint(0)), vec![0x00]);
        assert_eq!(enc(|w| w.put_uvarint(127)), vec![0x7f]);
        assert_eq!(enc(|w| w.put_uvarint(128)), vec![0x80, 0x01]);
        assert_eq!(enc(|w| w.put_uvarint(255)), vec![0xff, 0x01]);
        assert_eq!(enc(|w| w.put_uvarint(16384)), vec![0x80, 0x80, 0x01]);
    }

    #[test]
    fn uvarint_decode_golden() {
        assert_eq!(Reader::new(&[0x00]).get_uvarint().unwrap(), 0);
        assert_eq!(Reader::new(&[0x7f]).get_uvarint().unwrap(), 127);
        assert_eq!(Reader::new(&[0x80, 0x01]).get_uvarint().unwrap(), 128);
        assert_eq!(Reader::new(&[0xff, 0x01]).get_uvarint().unwrap(), 255);
        assert_eq!(Reader::new(&[0x80, 0x80, 0x01]).get_uvarint().unwrap(), 16384);
    }

    #[test]
    fn uvarint_rejects_non_minimal() {
        // 16384 non-minimally encoded (RFC 0002 §6.1.1 explicit counterexample).
        assert_eq!(
            Reader::new(&[0x80, 0x80, 0x00]).get_uvarint(),
            Err(DecodeError::NonMinimal)
        );
        assert_eq!(Reader::new(&[0x80, 0x00]).get_uvarint(), Err(DecodeError::NonMinimal));
        assert_eq!(Reader::new(&[0x81, 0x00]).get_uvarint(), Err(DecodeError::NonMinimal));
        // A lone 0x00 is the legitimate minimal encoding of 0.
        assert_eq!(Reader::new(&[0x00]).get_uvarint().unwrap(), 0);
    }

    #[test]
    fn uvarint_rejects_overlong_and_overflow() {
        // 11 groups, all continuation -> overlong.
        let overlong = [0x80u8; 11];
        assert_eq!(Reader::new(&overlong).get_uvarint(), Err(DecodeError::Overlong));
        // 10th group with bit >0 set -> exceeds u64.
        let overflow = [0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x02];
        assert_eq!(Reader::new(&overflow).get_uvarint(), Err(DecodeError::WidthOverflow));
    }

    #[test]
    fn uvarint_rejects_truncated() {
        assert_eq!(Reader::new(&[0x80]).get_uvarint(), Err(DecodeError::UnexpectedEof));
    }

    #[test]
    fn u64_max_roundtrips() {
        let bytes = enc(|w| w.put_uvarint(u64::MAX));
        assert_eq!(bytes.len(), 10);
        assert_eq!(Reader::new(&bytes).get_uvarint().unwrap(), u64::MAX);
    }

    // ---- width-bound unsigned ----

    #[test]
    fn unsigned_width_overflow() {
        let bytes = enc(|w| w.put_uvarint(256));
        assert_eq!(Reader::new(&bytes).get_u8(), Err(DecodeError::WidthOverflow));
        assert_eq!(Reader::new(&enc(|w| w.put_uvarint(255))).get_u8().unwrap(), 255);
        let bytes = enc(|w| w.put_uvarint(65536));
        assert_eq!(Reader::new(&bytes).get_u16(), Err(DecodeError::WidthOverflow));
    }

    // ---- §6.1.1 signed varint golden vectors ----

    #[test]
    fn i8_golden() {
        assert_eq!(enc(|w| w.put_i8(0)), vec![0x00]);
        assert_eq!(enc(|w| w.put_i8(1)), vec![0x02]);
        assert_eq!(enc(|w| w.put_i8(-1)), vec![0x01]);
        assert_eq!(enc(|w| w.put_i8(127)), vec![0xfe, 0x01]);
        assert_eq!(enc(|w| w.put_i8(-128)), vec![0xff, 0x01]);
    }

    #[test]
    fn i64_golden() {
        assert_eq!(enc(|w| w.put_i64(-1)), vec![0x01]);
        assert_eq!(
            enc(|w| w.put_i64(i64::MIN)),
            vec![0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x01]
        );
    }

    #[test]
    fn signed_roundtrip_all_widths() {
        for v in [i8::MIN, -1, 0, 1, i8::MAX] {
            let b = enc(|w| w.put_i8(v));
            assert_eq!(Reader::new(&b).get_i8().unwrap(), v);
        }
        for v in [i16::MIN, -1, 0, 1, i16::MAX] {
            let b = enc(|w| w.put_i16(v));
            assert_eq!(Reader::new(&b).get_i16().unwrap(), v);
        }
        for v in [i32::MIN, -1, 0, 1, i32::MAX] {
            let b = enc(|w| w.put_i32(v));
            assert_eq!(Reader::new(&b).get_i32().unwrap(), v);
        }
        for v in [i64::MIN, -1, 0, 1, i64::MAX] {
            let b = enc(|w| w.put_i64(v));
            assert_eq!(Reader::new(&b).get_i64().unwrap(), v);
        }
    }

    #[test]
    fn signed_width_overflow() {
        // 128 zig-zags to 256, which does not fit i8's 8-bit zig-zag space.
        let bytes = enc(|w| w.put_uvarint(256));
        assert_eq!(Reader::new(&bytes).get_i8(), Err(DecodeError::WidthOverflow));
    }

    // ---- §6.4 bool ----

    #[test]
    fn bool_golden_and_strict() {
        assert_eq!(enc(|w| w.put_bool(false)), vec![0x00]);
        assert_eq!(enc(|w| w.put_bool(true)), vec![0x01]);
        assert!(!Reader::new(&[0x00]).get_bool().unwrap());
        assert!(Reader::new(&[0x01]).get_bool().unwrap());
        assert_eq!(Reader::new(&[0x02]).get_bool(), Err(DecodeError::InvalidBool(0x02)));
        assert_eq!(Reader::new(&[0xff]).get_bool(), Err(DecodeError::InvalidBool(0xff)));
        assert_eq!(Reader::new(&[]).get_bool(), Err(DecodeError::UnexpectedEof));
    }

    // ---- §6.1.1 bytes ----

    #[test]
    fn bytes_golden() {
        assert_eq!(enc(|w| w.put_bytes(&[])), vec![0x00]);
        assert_eq!(enc(|w| w.put_bytes(&[0x6b, 0x65, 0x79])), vec![0x03, 0x6b, 0x65, 0x79]);
    }

    #[test]
    fn bytes_roundtrip_and_eof() {
        let b = enc(|w| w.put_bytes(b"hello"));
        assert_eq!(Reader::new(&b).get_bytes().unwrap(), b"hello");
        // Declares len=3 but only 1 byte follows.
        assert_eq!(Reader::new(&[0x03, 0xaa]).get_bytes(), Err(DecodeError::UnexpectedEof));
    }

    // ---- §6.5 hash ----

    #[test]
    fn hash_roundtrip_known() {
        let h = Hash { algo: 0x01, digest: vec![0xab; 32] };
        let b = enc(|w| w.put_hash(&h));
        // varint(1) varint(32) + 32 bytes
        assert_eq!(b[0], 0x01);
        assert_eq!(b[1], 32);
        assert_eq!(b.len(), 2 + 32);
        assert_eq!(Reader::new(&b).get_hash().unwrap(), h);
    }

    #[test]
    fn hash_known_length_mismatch_rejected() {
        // algo 0x01 (SHA-256) with a 16-byte digest declared.
        let mut bytes = vec![0x01, 16];
        bytes.extend(std::iter::repeat(0u8).take(16));
        assert_eq!(
            Reader::new(&bytes).get_hash(),
            Err(DecodeError::HashLengthMismatch { algo: 0x01, expected: 32, found: 16 })
        );
    }

    #[test]
    fn hash_unknown_algo_roundtrips_opaque() {
        let h = Hash { algo: 0x42, digest: vec![1, 2, 3, 4, 5] };
        let b = enc(|w| w.put_hash(&h));
        assert_eq!(Reader::new(&b).get_hash().unwrap(), h);
    }

    #[test]
    fn hash_self_delimiting() {
        // A hash followed by a trailing bool must leave the bool readable.
        let mut w = Writer::new();
        w.put_hash(&Hash { algo: 0x02, digest: vec![0x11; 32] });
        w.put_bool(true);
        let b = w.into_bytes();
        let mut r = Reader::new(&b);
        assert_eq!(r.get_hash().unwrap().algo, 0x02);
        assert!(r.get_bool().unwrap());
        assert!(r.is_empty());
    }

    // ---- §6.1.1 / §6.4 string ----

    #[test]
    fn string_golden() {
        assert_eq!(enc(|w| w.put_string("")), vec![0x00]);
        assert_eq!(enc(|w| w.put_string("hi")), vec![0x02, 0x68, 0x69]);
        // "café" precomposed é -> varint(5) + UTF-8 bytes.
        assert_eq!(
            enc(|w| w.put_string("caf\u{00e9}")),
            vec![0x05, 0x63, 0x61, 0x66, 0xc3, 0xa9]
        );
    }

    #[test]
    fn string_nfc_normalises_on_encode() {
        // Decomposed "cafe\u{0301}" (e + combining acute) must encode identically
        // to precomposed "caf\u{00e9}" after NFC (§6.4, pinned Unicode 15.1.0).
        let decomposed = enc(|w| w.put_string("cafe\u{0301}"));
        let precomposed = enc(|w| w.put_string("caf\u{00e9}"));
        assert_eq!(decomposed, precomposed);
        assert_eq!(decomposed, vec![0x05, 0x63, 0x61, 0x66, 0xc3, 0xa9]);
    }

    #[test]
    fn string_pinned_unicode_version_is_15_1_0() {
        // The canonical encoding pins Unicode 15.1.0 (§6.4); the crate constant
        // is the guard that the pin has not drifted.
        assert_eq!(unicode_normalization::UNICODE_VERSION, (15, 1, 0));
    }

    #[test]
    fn string_roundtrip_and_errors() {
        let b = enc(|w| w.put_string("hello \u{1f600}")); // multi-byte content
        assert_eq!(Reader::new(&b).get_string().unwrap(), "hello \u{1f600}");
        // Declares len=3 but only 1 byte present.
        assert_eq!(Reader::new(&[0x03, 0x61]).get_string(), Err(DecodeError::UnexpectedEof));
        // len=1 then an invalid UTF-8 lead byte.
        assert_eq!(Reader::new(&[0x01, 0xff]).get_string(), Err(DecodeError::InvalidUtf8));
    }

    // ---- §6.1.1 / §6.4 floats ----

    #[test]
    fn f32_golden() {
        assert_eq!(enc(|w| w.put_f32(0.0)), vec![0x00, 0x00, 0x00, 0x00]);
        assert_eq!(enc(|w| w.put_f32(1.0)), vec![0x00, 0x00, 0x80, 0x3f]);
        // Canonical quiet NaN, regardless of input NaN variant.
        assert_eq!(enc(|w| w.put_f32(f32::NAN)), vec![0x00, 0x00, 0xc0, 0x7f]);
        assert_eq!(
            enc(|w| w.put_f32(f32::from_bits(0x7f80_0001))), // a signalling NaN
            vec![0x00, 0x00, 0xc0, 0x7f]
        );
        // -0.0 canonicalises to +0.0.
        assert_eq!(enc(|w| w.put_f32(-0.0)), vec![0x00, 0x00, 0x00, 0x00]);
    }

    #[test]
    fn f64_golden() {
        assert_eq!(enc(|w| w.put_f64(0.0)), vec![0; 8]);
        assert_eq!(
            enc(|w| w.put_f64(1.0)),
            vec![0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf0, 0x3f]
        );
        // Canonical quiet NaN 0x7FF8000000000000 little-endian.
        assert_eq!(
            enc(|w| w.put_f64(f64::NAN)),
            vec![0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf8, 0x7f]
        );
        assert_eq!(enc(|w| w.put_f64(-0.0)), vec![0; 8]);
    }

    #[test]
    fn float_roundtrip() {
        for v in [0.0f32, 1.0, -1.0, f32::MIN, f32::MAX, 12.5] {
            assert_eq!(Reader::new(&enc(|w| w.put_f32(v))).get_f32().unwrap(), v);
        }
        for v in [0.0f64, 1.0, -1.0, f64::MIN, f64::MAX, 1234.5] {
            assert_eq!(Reader::new(&enc(|w| w.put_f64(v))).get_f64().unwrap(), v);
        }
        // Canonicalised NaN survives as a quiet-NaN bit pattern on decode.
        let b = enc(|w| w.put_f32(f32::NAN));
        assert_eq!(Reader::new(&b).get_f32().unwrap().to_bits(), 0x7fc0_0000);
        // Truncated float.
        assert_eq!(Reader::new(&[0x00, 0x00]).get_f32(), Err(DecodeError::UnexpectedEof));
    }

    // ---- §5.1 uuid ----

    #[test]
    fn uuid_raw_16_bytes_no_endianness() {
        let id: [u8; 16] = [
            0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef, 0xfe, 0xdc, 0xba, 0x98, 0x76, 0x54,
            0x32, 0x10,
        ];
        let b = enc(|w| w.put_uuid(&id));
        assert_eq!(b, id.to_vec()); // bytes emitted in field order, verbatim
        assert_eq!(Reader::new(&b).get_uuid().unwrap(), id);
        // 15 bytes is not a uuid.
        assert_eq!(Reader::new(&id[..15]).get_uuid(), Err(DecodeError::UnexpectedEof));
    }

    // ---- §5.1 timestamp ----

    #[test]
    fn timestamp_zigzag_i64() {
        // timestamp is an i64-ns zig-zag varint: matches put_i64 byte-for-byte.
        let t: i64 = 1_718_284_800_000_000_000; // from §10 worked example
        assert_eq!(enc(|w| w.put_timestamp(t)), enc(|w| w.put_i64(t)));
        assert_eq!(Reader::new(&enc(|w| w.put_timestamp(t))).get_timestamp().unwrap(), t);
        // Epoch and a negative (pre-epoch) instant round-trip.
        for v in [0i64, -1, t, i64::MIN, i64::MAX] {
            assert_eq!(Reader::new(&enc(|w| w.put_timestamp(v))).get_timestamp().unwrap(), v);
        }
    }

    // ---- free-function whole-value decode (trailing-byte rejection) ----

    #[test]
    fn free_fns_reject_trailing_bytes() {
        assert_eq!(decode_string(&[0x00, 0xaa]), Err(DecodeError::TrailingBytes));
        assert_eq!(
            decode_f32(&[0x00, 0x00, 0x00, 0x00, 0xaa]),
            Err(DecodeError::TrailingBytes)
        );
        let mut uuid_plus = vec![0u8; 16];
        uuid_plus.push(0xaa);
        assert_eq!(decode_uuid(&uuid_plus), Err(DecodeError::TrailingBytes));
    }

    #[test]
    fn free_fns_roundtrip() {
        assert_eq!(decode_string(&encode_string("round trip")).unwrap(), "round trip");
        assert_eq!(decode_f32(&encode_f32(2.5)).unwrap(), 2.5);
        assert_eq!(decode_f64(&encode_f64(2.5)).unwrap(), 2.5);
        let id = [7u8; 16];
        assert_eq!(decode_uuid(&encode_uuid(&id)).unwrap(), id);
        assert_eq!(decode_timestamp(&encode_timestamp(42)).unwrap(), 42);
    }
}
