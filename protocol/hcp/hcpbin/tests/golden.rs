//! Independent golden-vector + round-trip test suite for the hcpbin codec (WP3-S1).
//!
//! These tests are written BLIND to the implementation (adversarial independence):
//! every expectation is derived ONLY from RFC 0002 (`protocol/rfcs/0002-hcplang.md`),
//! specifically §6.1 (primitives / strict varint decode), §6.1.1 (worked examples:
//! primitive types), and §6.5 (`hash` encoding).
//!
//! They assume the public API surface documented at the bottom of this file. Until
//! `hcpbin` exposes that surface, this file will NOT compile — that is expected
//! under adversarial independence; the implementation must be aligned to these names.

use hcpbin::{
    decode_bool, decode_bytes, decode_hash, decode_i16, decode_i32, decode_i64, decode_i8,
    decode_uvarint, encode_bool, encode_bytes, encode_hash, encode_i16, encode_i32, encode_i64,
    encode_i8, encode_uvarint,
};

// ---------------------------------------------------------------------------
// Unsigned varints (LEB128, minimal) — RFC §6.1.1
//   0     -> 0x00
//   127   -> 0x7f
//   128   -> 0x80 0x01
//   255   -> 0xff 0x01
//   16384 -> 0x80 0x80 0x01
// ---------------------------------------------------------------------------

const UVARINT_VECTORS: &[(u64, &[u8])] = &[
    (0, &[0x00]),
    (127, &[0x7f]),
    (128, &[0x80, 0x01]),
    (255, &[0xff, 0x01]),
    (16384, &[0x80, 0x80, 0x01]),
];

#[test]
fn uvarint_encode_golden() {
    for &(v, bytes) in UVARINT_VECTORS {
        assert_eq!(encode_uvarint(v), bytes, "encode_uvarint({v})");
    }
}

#[test]
fn uvarint_decode_golden() {
    for &(v, bytes) in UVARINT_VECTORS {
        assert_eq!(
            decode_uvarint(bytes).expect("decode_uvarint of canonical bytes"),
            v,
            "decode_uvarint({bytes:02x?})"
        );
    }
}

#[test]
fn uvarint_round_trip_decode_encode() {
    // decode(encode(v)) == v across single/multi-byte boundaries.
    for v in [0u64, 1, 127, 128, 255, 256, 16383, 16384, 16385, u32::MAX as u64, u64::MAX] {
        let enc = encode_uvarint(v);
        let dec = decode_uvarint(&enc).expect("round-trip decode");
        assert_eq!(dec, v, "decode(encode({v}))");
    }
}

#[test]
fn uvarint_round_trip_encode_decode_golden_bytes() {
    // encode(decode(bytes)) == bytes for canonical inputs.
    for &(_, bytes) in UVARINT_VECTORS {
        let v = decode_uvarint(bytes).expect("decode canonical");
        assert_eq!(encode_uvarint(v), bytes, "encode(decode({bytes:02x?}))");
    }
}

// ---------------------------------------------------------------------------
// Signed varints (zig-zag + LEB128), per declared width — RFC §6.1.1
//   i8(0)    -> 0x00
//   i8(1)    -> 0x02
//   i8(-1)   -> 0x01
//   i8(127)  -> 0xfe 0x01
//   i8(-128) -> 0xff 0x01
//   i64(-1)  -> 0x01
//   i64(-9223372036854775808) -> 0xff*9 0x01 (10 bytes, canonical)
// ---------------------------------------------------------------------------

#[test]
fn i8_encode_golden() {
    assert_eq!(encode_i8(0), &[0x00]);
    assert_eq!(encode_i8(1), &[0x02]);
    assert_eq!(encode_i8(-1), &[0x01]);
    assert_eq!(encode_i8(127), &[0xfe, 0x01]);
    assert_eq!(encode_i8(-128), &[0xff, 0x01]);
}

#[test]
fn i8_decode_golden() {
    assert_eq!(decode_i8(&[0x00]).unwrap(), 0);
    assert_eq!(decode_i8(&[0x02]).unwrap(), 1);
    assert_eq!(decode_i8(&[0x01]).unwrap(), -1);
    assert_eq!(decode_i8(&[0xfe, 0x01]).unwrap(), 127);
    assert_eq!(decode_i8(&[0xff, 0x01]).unwrap(), -128);
}

#[test]
fn i64_encode_golden() {
    assert_eq!(encode_i64(-1), &[0x01]);
    // i64::MIN: zig-zag(-9223372036854775808) = u64::MAX -> 9x0xff then 0x01.
    assert_eq!(
        encode_i64(i64::MIN),
        &[0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x01]
    );
}

#[test]
fn i64_decode_golden() {
    assert_eq!(decode_i64(&[0x01]).unwrap(), -1);
    assert_eq!(
        decode_i64(&[0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x01]).unwrap(),
        i64::MIN
    );
}

#[test]
fn signed_round_trip_all_widths() {
    // decode(encode(v)) == v. Bytes are not hand-computed here (zig-zag errors are
    // easy); correctness is checked structurally via round-trip, with golden
    // byte-exactness covered by the *_encode_golden tests above.
    for v in [i8::MIN, -100, -1, 0, 1, 100, i8::MAX] {
        assert_eq!(decode_i8(&encode_i8(v)).unwrap(), v, "i8 {v}");
    }
    for v in [i16::MIN, -1000, -1, 0, 1, 1000, i16::MAX] {
        assert_eq!(decode_i16(&encode_i16(v)).unwrap(), v, "i16 {v}");
    }
    for v in [i32::MIN, -100_000, -1, 0, 1, 100_000, i32::MAX] {
        assert_eq!(decode_i32(&encode_i32(v)).unwrap(), v, "i32 {v}");
    }
    for v in [i64::MIN, -1, 0, 1, i64::MAX] {
        assert_eq!(decode_i64(&encode_i64(v)).unwrap(), v, "i64 {v}");
    }
}

// ---------------------------------------------------------------------------
// Bool — RFC §6.1.1
//   false -> 0x00 (only valid)
//   true  -> 0x01 (only valid)
//   any other byte (e.g. 0x02) rejected as malformed.
// ---------------------------------------------------------------------------

#[test]
fn bool_encode_golden() {
    assert_eq!(encode_bool(false), &[0x00]);
    assert_eq!(encode_bool(true), &[0x01]);
}

#[test]
fn bool_decode_golden() {
    assert_eq!(decode_bool(&[0x00]).unwrap(), false);
    assert_eq!(decode_bool(&[0x01]).unwrap(), true);
}

#[test]
fn bool_round_trip() {
    for v in [false, true] {
        assert_eq!(decode_bool(&encode_bool(v)).unwrap(), v);
    }
}

#[test]
fn bool_strict_reject_non_canonical_byte() {
    // 0x02 is explicitly called out as malformed in §6.1.1.
    assert!(decode_bool(&[0x02]).is_err(), "bool 0x02 must be rejected");
    assert!(decode_bool(&[0xff]).is_err(), "bool 0xff must be rejected");
}

#[test]
fn bool_strict_reject_truncated_and_trailing() {
    assert!(decode_bool(&[]).is_err(), "empty bool input must be rejected");
    // Consume-all decode: a valid bool byte followed by junk is not a clean decode.
    assert!(
        decode_bool(&[0x01, 0x00]).is_err(),
        "trailing bytes after bool must be rejected"
    );
}

// ---------------------------------------------------------------------------
// Bytes (length-prefixed varint count + raw bytes) — RFC §6.1.1
//   []                 -> 0x00
//   [0x6b,0x65,0x79]   -> 0x03 0x6b 0x65 0x79
// ---------------------------------------------------------------------------

#[test]
fn bytes_encode_golden() {
    assert_eq!(encode_bytes(&[]), &[0x00]);
    assert_eq!(encode_bytes(&[0x6b, 0x65, 0x79]), &[0x03, 0x6b, 0x65, 0x79]);
}

#[test]
fn bytes_decode_golden() {
    assert_eq!(decode_bytes(&[0x00]).unwrap(), Vec::<u8>::new());
    assert_eq!(
        decode_bytes(&[0x03, 0x6b, 0x65, 0x79]).unwrap(),
        vec![0x6b, 0x65, 0x79]
    );
}

#[test]
fn bytes_round_trip() {
    for v in [
        vec![],
        vec![0x00],
        vec![0x6b, 0x65, 0x79],
        (0u16..300).map(|x| x as u8).collect::<Vec<u8>>(), // forces a 2-byte length prefix
    ] {
        let enc = encode_bytes(&v);
        assert_eq!(decode_bytes(&enc).unwrap(), v, "bytes len {}", v.len());
    }
}

#[test]
fn bytes_strict_reject_truncated_payload() {
    // Length prefix claims 3 bytes but only 2 are present.
    assert!(
        decode_bytes(&[0x03, 0x6b, 0x65]).is_err(),
        "bytes with short payload must be rejected"
    );
    // Length prefix claims 1 byte, none present.
    assert!(decode_bytes(&[0x01]).is_err(), "bytes missing payload must be rejected");
}

#[test]
fn bytes_strict_reject_trailing() {
    // Consume-all: extra byte after a complete value.
    assert!(
        decode_bytes(&[0x00, 0xaa]).is_err(),
        "trailing byte after empty bytes must be rejected"
    );
}

#[test]
fn bytes_strict_reject_overlong_length_prefix() {
    // count=3 encoded non-minimally as 0x83 0x00, payload "key".
    assert!(
        decode_bytes(&[0x83, 0x00, 0x6b, 0x65, 0x79]).is_err(),
        "overlong length prefix must be rejected"
    );
}

// ---------------------------------------------------------------------------
// hash: varint(algo-id) varint(len) digest-bytes — RFC §6.5
//   algo-id 0x01 = SHA-256, digest length 32
//   algo-id 0x02 = BLAKE3-256, digest length 32
//   For a KNOWN algo-id, len MUST equal the registry length (mismatch = error).
//   Unknown algo-id: self-delimiting via len; accepted and preserved for round-trip.
// ---------------------------------------------------------------------------

#[test]
fn hash_encode_golden_sha256() {
    let digest = [0xab_u8; 32];
    let mut expected = vec![0x01, 0x20]; // algo-id=1, len=32 (0x20)
    expected.extend_from_slice(&digest);
    assert_eq!(encode_hash(0x01, &digest), expected);
}

#[test]
fn hash_decode_golden_sha256() {
    let digest = [0xab_u8; 32];
    let mut input = vec![0x01, 0x20];
    input.extend_from_slice(&digest);
    let (algo, got) = decode_hash(&input).unwrap();
    assert_eq!(algo, 0x01);
    assert_eq!(got, digest.to_vec());
}

#[test]
fn hash_round_trip_known_algos() {
    for algo in [0x01_u8, 0x02] {
        let digest = [0x5a_u8; 32];
        let enc = encode_hash(algo, &digest);
        let (a, d) = decode_hash(&enc).unwrap();
        assert_eq!(a, algo);
        assert_eq!(d, digest.to_vec());
    }
}

#[test]
fn hash_strict_reject_known_algo_wrong_length() {
    // §6.5: for a known algo-id, len MUST equal the registry digest length.
    // SHA-256 (0x01) with len=16 is a protocol error.
    let mut input = vec![0x01, 0x10]; // algo=1, len=16
    input.extend_from_slice(&[0xab; 16]);
    assert!(
        decode_hash(&input).is_err(),
        "known algo-id with non-registry digest length must be rejected"
    );
}

#[test]
fn hash_unknown_algo_round_trips() {
    // §6.5/§6.5.1: unknown algo-id (0x11 user range) is self-delimiting via len
    // and the opaque digest survives byte-for-byte round-trip.
    let digest = vec![0xde, 0xad, 0xbe, 0xef];
    let mut input = vec![0x11, 0x04];
    input.extend_from_slice(&digest);
    let (algo, got) = decode_hash(&input).expect("unknown algo accepted via len prefix");
    assert_eq!(algo, 0x11);
    assert_eq!(got, digest);
}

#[test]
fn hash_strict_reject_truncated_digest() {
    // len claims 32 but only 4 digest bytes present.
    let mut input = vec![0x01, 0x20];
    input.extend_from_slice(&[0xab; 4]);
    assert!(
        decode_hash(&input).is_err(),
        "hash with short digest must be rejected"
    );
}

// ---------------------------------------------------------------------------
// Cross-cutting STRICT varint decode rejection — RFC §6.1 ("Strict varint decode")
// ---------------------------------------------------------------------------

#[test]
fn uvarint_strict_reject_overlong_minimal_violation() {
    // 0x80 0x00 decodes to 0 but is non-minimal (the value 0 is canonically 0x00).
    assert!(
        decode_uvarint(&[0x80, 0x00]).is_err(),
        "overlong varint 0x80 0x00 must be rejected"
    );
    // 0x81 0x00 decodes to 1 but is non-minimal (canonical is 0x01).
    assert!(
        decode_uvarint(&[0x81, 0x00]).is_err(),
        "overlong varint 0x81 0x00 must be rejected"
    );
}

#[test]
fn uvarint_strict_reject_truncated() {
    // Continuation bit set but stream ends.
    assert!(decode_uvarint(&[0x80]).is_err(), "truncated varint must be rejected");
    assert!(
        decode_uvarint(&[0x80, 0x80]).is_err(),
        "truncated multi-byte varint must be rejected"
    );
    assert!(decode_uvarint(&[]).is_err(), "empty varint input must be rejected");
}

#[test]
fn uvarint_strict_reject_trailing() {
    // Consume-all: a complete 0x00 followed by junk is not a clean decode.
    assert!(
        decode_uvarint(&[0x00, 0x00]).is_err(),
        "trailing byte after complete varint must be rejected"
    );
}

#[test]
fn uvarint_strict_reject_overflow_64bit() {
    // §6.1: more than 10 bytes for a 64-bit value, or a magnitude exceeding 64 bits.
    // 11 continuation bytes can never be a canonical u64.
    let eleven = [0x80_u8, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x01];
    assert!(
        decode_uvarint(&eleven).is_err(),
        "varint exceeding 64-bit width must be rejected"
    );
}

#[test]
fn signed_strict_reject_overlong() {
    // Strict varint rules apply under the zig-zag layer too: 0x80 0x00 is non-minimal.
    assert!(decode_i8(&[0x80, 0x00]).is_err(), "overlong i8 varint must be rejected");
    assert!(decode_i64(&[0x80, 0x00]).is_err(), "overlong i64 varint must be rejected");
}

#[test]
fn signed_strict_reject_truncated() {
    assert!(decode_i8(&[0x80]).is_err(), "truncated i8 varint must be rejected");
    assert!(decode_i64(&[]).is_err(), "empty i64 input must be rejected");
}
