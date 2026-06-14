//! Integration golden / round-trip / strict-reject tests for the hcpbin
//! AGGREGATE layer (RFC 0002 §6.2, §6.6, §6.7, §5.4, §6.8).
//!
//! These exercise only the crate's public surface, with vectors derived from
//! the RFC worked examples (§6.1.1, §6.6.1, §6.7.1, §10, §10.1).
//!
//! Two RFC worked-example byte strings contradict the normative §6 rules; this
//! suite follows the normative rule (and the task spec), documented inline:
//!   - §6.3.1's nested-record vector omits the byte-len prefix that §6.2
//!     mandates for nested records; nested records are checked by round-trip and
//!     the §6.8 fixed point rather than against those bytes.
//!   - §6.6.1's stated map order (apple, banana, zebra) sorts by key *content*;
//!     §6.6 (normative) sorts by *encoded*-key bytes (length prefix included),
//!     which yields apple, zebra, banana. See `map_sorted_by_encoded_key_bytes`.

use hcpbin::{
    decode_enum, decode_list, decode_map, decode_union, encode_enum, encode_list, encode_map,
    encode_union, DecodeError, Reader, RecordReader, RecordWriter, Writer,
};

// ---------------------------------------------------------------------------
// §6.2 records: ascending-tag golden + reject out-of-order / duplicate
// ---------------------------------------------------------------------------

#[test]
fn record_ascending_tag_golden() {
    // §10: ToolCallRequest{ tool = "fs.read", args = 0x6b6579 }, body only.
    let mut w = Writer::new();
    let mut rec = RecordWriter::new(&mut w);
    rec.field(1).put_string("fs.read");
    rec.field(2).put_bytes(&[0x6b, 0x65, 0x79]);
    let bytes = w.into_bytes();
    assert_eq!(
        bytes,
        vec![0x01, 0x07, 0x66, 0x73, 0x2e, 0x72, 0x65, 0x61, 0x64, 0x02, 0x03, 0x6b, 0x65, 0x79]
    );

    // Decode it back through RecordReader.
    let mut r = Reader::new(&bytes);
    let mut rr = RecordReader::new(&mut r);
    assert_eq!(rr.next_field().unwrap(), Some(1));
    assert_eq!(rr.reader().get_string().unwrap(), "fs.read");
    assert_eq!(rr.next_field().unwrap(), Some(2));
    assert_eq!(rr.reader().get_bytes().unwrap(), &[0x6b, 0x65, 0x79]);
    assert_eq!(rr.next_field().unwrap(), None);
}

#[test]
fn record_decode_rejects_out_of_order_tags() {
    // tag @2 (bool) then tag @1 (bool): descending -> rejected (§6.2).
    let bytes = [0x02, 0x01, 0x01, 0x01];
    let mut r = Reader::new(&bytes);
    let mut rr = RecordReader::new(&mut r);
    assert_eq!(rr.next_field().unwrap(), Some(2));
    let _ = rr.reader().get_bool().unwrap();
    assert_eq!(
        rr.next_field(),
        Err(DecodeError::NonAscendingTag { previous: 2, found: 1 })
    );
}

#[test]
fn record_decode_rejects_duplicate_tags() {
    // tag @1 twice -> rejected (§6.2).
    let bytes = [0x01, 0x01, 0x01, 0x00];
    let mut r = Reader::new(&bytes);
    let mut rr = RecordReader::new(&mut r);
    assert_eq!(rr.next_field().unwrap(), Some(1));
    let _ = rr.reader().get_bool().unwrap();
    assert_eq!(rr.next_field(), Err(DecodeError::DuplicateTag(1)));
}

#[test]
fn nested_record_byte_len_framed_roundtrip() {
    // §6.2 mandates byte-len framing for a nested record (unlike §6.3.1's buggy
    // unframed vector). Outer{ @1 = Inner{ @1 = "a" }, @2 = u32(7) }.
    let mut w = Writer::new();
    let mut outer = RecordWriter::new(&mut w);
    outer.field_record(1, |inner| {
        inner.field(1).put_string("a");
    });
    outer.field(2).put_uvarint(7);
    let bytes = w.into_bytes();

    // Outer @1: tag=01, framed-len=03, body=[01 01 61]; Outer @2: tag=02, u32(7)=07.
    assert_eq!(bytes, vec![0x01, 0x03, 0x01, 0x01, 0x61, 0x02, 0x07]);

    // Decode: nested field is a framed slice fed to a sub-RecordReader.
    let mut r = Reader::new(&bytes);
    let mut rr = RecordReader::new(&mut r);
    assert_eq!(rr.next_field().unwrap(), Some(1));
    let inner_bytes = rr.reader().get_framed().unwrap();
    {
        let mut ir = Reader::new(inner_bytes);
        let mut irr = RecordReader::new(&mut ir);
        assert_eq!(irr.next_field().unwrap(), Some(1));
        assert_eq!(irr.reader().get_string().unwrap(), "a");
        assert_eq!(irr.next_field().unwrap(), None);
    }
    assert_eq!(rr.next_field().unwrap(), Some(2));
    assert_eq!(rr.reader().get_u32().unwrap(), 7);
    assert_eq!(rr.next_field().unwrap(), None);
}

// ---------------------------------------------------------------------------
// §6.6 lists
// ---------------------------------------------------------------------------

#[test]
fn list_golden_a_bc() {
    // §6.6.1: list<string> ["a", "bc"] (the field body, without the @1 tag) is
    // count=2 then "a" then "bc": 02 01 61 02 62 63.
    let items = ["a", "bc"];
    let bytes = encode_list(&items, |w, s| w.put_string(s));
    assert_eq!(bytes, vec![0x02, 0x01, 0x61, 0x02, 0x62, 0x63]);

    let decoded = decode_list(&bytes, |r| r.get_string()).unwrap();
    assert_eq!(decoded, vec!["a".to_string(), "bc".to_string()]);
}

#[test]
fn list_preserves_order() {
    // List order is significant (§6.6): reversing the input changes the bytes.
    let a = encode_list(&["a", "bc"], |w, s| w.put_string(s));
    let b = encode_list(&["bc", "a"], |w, s| w.put_string(s));
    assert_ne!(a, b);
}

// ---------------------------------------------------------------------------
// §6.6 maps: sorted-by-encoded-key + reject unsorted / duplicate
// ---------------------------------------------------------------------------

#[test]
fn map_sorted_unambiguous_golden() {
    // §10.1 WatchControl filters {"path":"/tmp", "mode":"watch"}: equal-length
    // keys, so content order == encoded-key order: "mode" < "path".
    // Insertion order here is path-first to prove the encoder sorts.
    let entries = [("path", "/tmp"), ("mode", "watch")];
    let bytes = encode_map(&entries, |w, k| w.put_string(k), |w, v| w.put_string(v));

    // count=2, then "mode"->"watch", then "path"->"/tmp".
    let mut expected = vec![0x02];
    expected.extend_from_slice(&[0x04, b'm', b'o', b'd', b'e']);
    expected.extend_from_slice(&[0x05, b'w', b'a', b't', b'c', b'h']);
    expected.extend_from_slice(&[0x04, b'p', b'a', b't', b'h']);
    expected.extend_from_slice(&[0x04, b'/', b't', b'm', b'p']);
    assert_eq!(bytes, expected);

    let decoded = decode_map(&bytes, |r| r.get_string(), |r| r.get_string()).unwrap();
    assert_eq!(
        decoded,
        vec![
            ("mode".to_string(), "watch".to_string()),
            ("path".to_string(), "/tmp".to_string()),
        ]
    );
}

#[test]
fn map_sorted_by_encoded_key_bytes() {
    // §6.6.1 input {"zebra","apple","banana"} -> values "1","2","3".
    // §6.6 sorts by ENCODED-key bytes (length prefix included), NOT content:
    //   apple  = 05 61 ...   (len 5)
    //   zebra  = 05 7a ...   (len 5)
    //   banana = 06 62 ...   (len 6)
    // Both len-5 keys precede the len-6 key, so the canonical order is
    // apple, zebra, banana -- which differs from §6.6.1's stated
    // apple, banana, zebra (that ignores the length prefix). We follow §6.6.
    let entries = [("zebra", "1"), ("apple", "2"), ("banana", "3")];
    let bytes = encode_map(&entries, |w, k| w.put_string(k), |w, v| w.put_string(v));
    let decoded = decode_map(&bytes, |r| r.get_string(), |r| r.get_string()).unwrap();
    assert_eq!(
        decoded,
        vec![
            ("apple".to_string(), "2".to_string()),
            ("zebra".to_string(), "1".to_string()),
            ("banana".to_string(), "3".to_string()),
        ]
    );
}

#[test]
fn map_decode_rejects_unsorted_keys() {
    // Hand-built: count=2, then "path" then "mode" (descending encoded-key).
    let mut bad = vec![0x02];
    bad.extend_from_slice(&[0x04, b'p', b'a', b't', b'h']);
    bad.extend_from_slice(&[0x04, b'/', b't', b'm', b'p']);
    bad.extend_from_slice(&[0x04, b'm', b'o', b'd', b'e']);
    bad.extend_from_slice(&[0x05, b'w', b'a', b't', b'c', b'h']);
    assert_eq!(
        decode_map(&bad, |r| r.get_string(), |r| r.get_string()),
        Err(DecodeError::UnsortedMapKey)
    );
}

#[test]
fn map_decode_rejects_duplicate_keys() {
    // count=2, "k"->"a", "k"->"b": identical keys -> duplicate (§6.6).
    let mut dup = vec![0x02];
    dup.extend_from_slice(&[0x01, b'k']);
    dup.extend_from_slice(&[0x01, b'a']);
    dup.extend_from_slice(&[0x01, b'k']);
    dup.extend_from_slice(&[0x01, b'b']);
    assert_eq!(
        decode_map(&dup, |r| r.get_string(), |r| r.get_string()),
        Err(DecodeError::DuplicateMapKey)
    );
}

// ---------------------------------------------------------------------------
// §6.7 unions: known-arm golden + unknown-arm byte-for-byte preservation
// ---------------------------------------------------------------------------

#[test]
fn union_known_arm_text_hi_golden() {
    // §6.7.1: Payload.text("hi") -> 01 03 02 68 69
    // (arm-tag 1, byte-len 3, then string "hi" = 02 68 69).
    let bytes = encode_union(1, |w| w.put_string("hi"));
    assert_eq!(bytes, vec![0x01, 0x03, 0x02, 0x68, 0x69]);

    // Decode: arm tag + raw value bytes; the caller decodes the value.
    let (arm, value) = decode_union(&bytes).unwrap();
    assert_eq!(arm, 1);
    assert_eq!(value, vec![0x02, 0x68, 0x69]);
    assert_eq!(Reader::new(&value).get_string().unwrap(), "hi");
}

#[test]
fn union_unknown_arm_preserved_byte_for_byte() {
    // §6.7.1: V2 arm @3, byte-len 5, raw value 01 02 03 04 05.
    let original = vec![0x03, 0x05, 0x01, 0x02, 0x03, 0x04, 0x05];

    let (arm, value) = decode_union(&original).unwrap();
    assert_eq!(arm, 3);
    assert_eq!(value, vec![0x01, 0x02, 0x03, 0x04, 0x05]);

    // Re-emit the unknown arm verbatim via put_union_raw -> identical bytes.
    let mut w = Writer::new();
    w.put_union_raw(arm, &value);
    assert_eq!(w.into_bytes(), original);
}

// ---------------------------------------------------------------------------
// §5.4 enums: known value + unknown-case preservation
// ---------------------------------------------------------------------------

#[test]
fn enum_known_and_unknown_case() {
    // §6.7.1: info=0 -> 00, warn=1 -> 01.
    assert_eq!(encode_enum(0), vec![0x00]);
    assert_eq!(encode_enum(1), vec![0x01]);
    assert_eq!(decode_enum(&[0x00]).unwrap(), 0);
    assert_eq!(decode_enum(&[0x01]).unwrap(), 1);

    // unknown(5): decode preserves the value, re-encode is byte-identical (05).
    let unknown = decode_enum(&[0x05]).unwrap();
    assert_eq!(unknown, 5);
    assert_eq!(encode_enum(unknown), vec![0x05]);
}

// ---------------------------------------------------------------------------
// §6.8 canonicality: encode(decode(encode(v))) == encode(v) fixed point
// ---------------------------------------------------------------------------

#[test]
fn fixed_point_list() {
    let v = ["a", "bc", "def"];
    let once = encode_list(&v, |w, s| w.put_string(s));
    let decoded = decode_list(&once, |r| r.get_string()).unwrap();
    let twice = encode_list(&decoded, |w, s| w.put_string(s.as_str()));
    assert_eq!(once, twice);
}

#[test]
fn fixed_point_map() {
    let entries = [("zebra", "1"), ("apple", "2"), ("banana", "3")];
    let once = encode_map(&entries, |w, k| w.put_string(k), |w, v| w.put_string(v));
    let decoded = decode_map(&once, |r| r.get_string(), |r| r.get_string()).unwrap();
    let twice = encode_map(
        &decoded,
        |w, k| w.put_string(k.as_str()),
        |w, v| w.put_string(v.as_str()),
    );
    assert_eq!(once, twice);
}

#[test]
fn fixed_point_union_unknown_arm() {
    let once = vec![0x03, 0x05, 0x01, 0x02, 0x03, 0x04, 0x05];
    let (arm, value) = decode_union(&once).unwrap();
    let mut w = Writer::new();
    w.put_union_raw(arm, &value);
    assert_eq!(w.into_bytes(), once);
}

#[test]
fn fixed_point_record() {
    // Build, decode, rebuild a flat record; bytes must be a fixed point (§6.8).
    let build = || {
        let mut w = Writer::new();
        let mut rec = RecordWriter::new(&mut w);
        rec.field(1).put_string("fs.read");
        rec.field(2).put_bytes(&[0x6b, 0x65, 0x79]);
        w.into_bytes()
    };
    let once = build();

    let mut r = Reader::new(&once);
    let mut rr = RecordReader::new(&mut r);
    assert_eq!(rr.next_field().unwrap(), Some(1));
    let tool = rr.reader().get_string().unwrap();
    assert_eq!(rr.next_field().unwrap(), Some(2));
    let args = rr.reader().get_bytes().unwrap().to_vec();
    assert_eq!(rr.next_field().unwrap(), None);

    let mut w2 = Writer::new();
    let mut rec2 = RecordWriter::new(&mut w2);
    rec2.field(1).put_string(&tool);
    rec2.field(2).put_bytes(&args);
    assert_eq!(w2.into_bytes(), once);
}