//! Golden-vector + round-trip suite for the Litany Wire framing/header codec.
//!
//! Every expectation is HAND-AUTHORED from RFC 0003 (`protocol/rfcs/0003-litany-wire.md`):
//! - §4.1   frame record = `length || header-bytes || body`; length counts
//!          `frame-bytes` only; length 0 illegal.
//! - §4.2   length is a minimal unsigned LEB128 varint (RFC 0002 §6.1).
//! - §4.3   length > max_frame is a framing violation, rejected before the body.
//! - §4.4.1 header tags @0..=@4: kind(varint 0-4), corr(16 raw), stream(varint?),
//!          seq(varint?), end(0x01 if true / omitted). Each present field is
//!          `varint(tag) || value` (the §4.4.1 decoder-invariant / RFC 0002 §6.2
//!          record model — see the lib.rs interpretation note).
//! - §4.5   strict decode: overlong/non-minimal length, length 0, truncation,
//!          malformed header are framing violations (WireError).
//!
//! Varint byte boundaries exercised: 127/128 (1->2 bytes) and 16383/16384
//! (2->3 bytes), matching RFC 0002 §6.1.1's worked examples reused by §4.2.

use litany::{
    decode_frame, decode_header, encode_frame, encode_header, FrameKind, Header, WireError,
    MAX_FRAME_DEFAULT,
};

/// A fixed 16-byte correlation id used across vectors (RFC 0003 §4.4.1: corr is
/// 16 raw bytes in big-endian order). Distinct bytes so a byte-swap would show.
const CORR: [u8; 16] = [
    0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff,
];

// ---------------------------------------------------------------------------
// Header golden vectors (RFC 0003 §4.4.1)
// ---------------------------------------------------------------------------

#[test]
fn header_single_shot_request_golden() {
    // §4.4.1 "single-shot request" example: only kind(@0) + corr(@1).
    //   @0 kind: 00 (tag) 00 (request)
    //   @1 corr: 01 (tag) <16 bytes>
    let header = Header::single_shot(FrameKind::Request, CORR);
    let mut expected = vec![0x00, 0x00, 0x01];
    expected.extend_from_slice(&CORR);
    assert_eq!(
        encode_header(&header),
        expected,
        "single-shot request header"
    );
    assert_eq!(
        decode_header(&expected).unwrap(),
        header,
        "decode single-shot header"
    );
}

#[test]
fn header_kind_values_golden() {
    // §4.4.1 tag @0: kind enum 0..=4. Each is one varint byte after tag 00.
    let cases = [
        (FrameKind::Request, 0x00u8),
        (FrameKind::Response, 0x01),
        (FrameKind::Event, 0x02),
        (FrameKind::Control, 0x03),
        (FrameKind::Error, 0x04),
    ];
    for (kind, kind_byte) in cases {
        let header = Header::single_shot(kind, CORR);
        let mut expected = vec![0x00, kind_byte, 0x01];
        expected.extend_from_slice(&CORR);
        assert_eq!(
            encode_header(&header),
            expected,
            "kind {kind:?} header bytes"
        );
    }
}

#[test]
fn header_multiframe_event_golden() {
    // §4.4.1 "multi-frame event with seq" example: kind(@0)=event, corr(@1),
    // stream(@2)=1, seq(@3)=1, end(@4)=true.
    //   00 02            @0 kind=2 (event)
    //   01 <16 corr>     @1 corr
    //   02 01            @2 stream=1
    //   03 01            @3 seq=1
    //   04 01            @4 end=true
    let header = Header {
        kind: FrameKind::Event,
        corr: CORR,
        stream: Some(1),
        seq: Some(1),
        end: true,
    };
    let mut expected = vec![0x00, 0x02, 0x01];
    expected.extend_from_slice(&CORR);
    expected.extend_from_slice(&[0x02, 0x01, 0x03, 0x01, 0x04, 0x01]);
    assert_eq!(encode_header(&header), expected, "multi-frame event header");
    assert_eq!(
        decode_header(&expected).unwrap(),
        header,
        "decode multi-frame header"
    );
}

#[test]
fn header_stream_seq_varint_boundaries() {
    // §4.2/§4.4.1: stream and seq are LEB128 varints; cross the 127->128 and
    // 16383->16384 byte boundaries (RFC 0002 §6.1.1).
    //   128   -> 0x80 0x01
    //   16384 -> 0x80 0x80 0x01
    let header = Header {
        kind: FrameKind::Response,
        corr: CORR,
        stream: Some(128),
        seq: Some(16384),
        end: false,
    };
    let mut expected = vec![0x00, 0x01, 0x01];
    expected.extend_from_slice(&CORR);
    expected.extend_from_slice(&[
        0x02, 0x80, 0x01, // @2 stream=128
        0x03, 0x80, 0x80, 0x01, // @3 seq=16384
    ]);
    assert_eq!(encode_header(&header), expected, "varint-boundary header");
    assert_eq!(decode_header(&expected).unwrap(), header);
}

// ---------------------------------------------------------------------------
// Frame record golden vectors (RFC 0003 §4.1)
// ---------------------------------------------------------------------------

#[test]
fn frame_empty_body_golden() {
    // §4.1: header(19 bytes for single-shot request) + empty body.
    // header = 00 00 01 <16 corr> = 19 bytes; length = 19 = 0x13.
    let header = Header::single_shot(FrameKind::Request, CORR);
    let mut expected = vec![0x13, 0x00, 0x00, 0x01];
    expected.extend_from_slice(&CORR);
    let encoded = encode_frame(&header, &[], MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(encoded, expected, "empty-body frame record");

    let (h, body, consumed) = decode_frame(&encoded, MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(h, header);
    assert!(body.is_empty());
    assert_eq!(consumed, encoded.len());
}

#[test]
fn frame_small_body_golden() {
    // §4.6 worked framing example body: ToolCallRequest body bytes
    //   01 07 66 73 2e 72 65 61 64   @1 string len 7 "fs.read"
    //   02 03 6b 65 79               @2 bytes len 3 0x6b 0x65 0x79
    // body = 14 bytes. header(single-shot request) = 19 bytes. total = 33 = 0x21.
    let body: &[u8] = &[
        0x01, 0x07, 0x66, 0x73, 0x2e, 0x72, 0x65, 0x61, 0x64, // @1 "fs.read"
        0x02, 0x03, 0x6b, 0x65, 0x79, // @2 0x6b6579
    ];
    let header = Header::single_shot(FrameKind::Request, CORR);
    let mut expected = vec![0x21, 0x00, 0x00, 0x01];
    expected.extend_from_slice(&CORR);
    expected.extend_from_slice(body);
    let encoded = encode_frame(&header, body, MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(encoded, expected, "small-body frame record (§4.6)");

    let (h, decoded_body, consumed) = decode_frame(&encoded, MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(h, header);
    assert_eq!(decoded_body, body);
    assert_eq!(consumed, encoded.len());
}

#[test]
fn frame_length_varint_boundary_127_128() {
    // §4.2: the length prefix itself crosses the 1->2 byte varint boundary.
    // Choose a body so that frame_len = header(19) + body = 127, then 128.
    let header = Header::single_shot(FrameKind::Request, CORR);
    let header_len = encode_header(&header).len();
    assert_eq!(header_len, 19);

    // frame_len = 127 -> single-byte length 0x7f
    let body_127 = vec![0xabu8; 127 - header_len];
    let enc_127 = encode_frame(&header, &body_127, MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(enc_127[0], 0x7f, "length 127 is single byte 0x7f");
    let (_, b, _) = decode_frame(&enc_127, MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(b, body_127);

    // frame_len = 128 -> two-byte length 0x80 0x01
    let body_128 = vec![0xabu8; 128 - header_len];
    let enc_128 = encode_frame(&header, &body_128, MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(&enc_128[0..2], &[0x80, 0x01], "length 128 is 0x80 0x01");
    let (_, b, _) = decode_frame(&enc_128, MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(b, body_128);
}

#[test]
fn frame_length_varint_boundary_16383_16384() {
    // §4.2: the length prefix crosses the 2->3 byte varint boundary.
    let header = Header::single_shot(FrameKind::Request, CORR);
    let header_len = encode_header(&header).len();

    // frame_len = 16383 -> two-byte 0xff 0x7f
    let body = vec![0x5au8; 16383 - header_len];
    let enc = encode_frame(&header, &body, MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(&enc[0..2], &[0xff, 0x7f], "length 16383 is 0xff 0x7f");
    let (_, b, _) = decode_frame(&enc, MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(b.len(), body.len());

    // frame_len = 16384 -> three-byte 0x80 0x80 0x01
    let body = vec![0x5au8; 16384 - header_len];
    let enc = encode_frame(&header, &body, MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(
        &enc[0..3],
        &[0x80, 0x80, 0x01],
        "length 16384 is 0x80 0x80 0x01"
    );
    let (_, b, _) = decode_frame(&enc, MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(b.len(), body.len());
}

// ---------------------------------------------------------------------------
// Round-trip across frame classes and stream shapes
// ---------------------------------------------------------------------------

#[test]
fn round_trip_all_kinds_and_shapes() {
    let bodies: &[&[u8]] = &[&[], &[0x00], &[0xde, 0xad, 0xbe, 0xef]];
    let kinds = [
        FrameKind::Request,
        FrameKind::Response,
        FrameKind::Event,
        FrameKind::Control,
        FrameKind::Error,
    ];
    let shapes = [
        (None, None, false),
        (Some(0), None, false),
        (Some(2), Some(0), false),
        (Some(4), Some(7), true),
        (Some(u64::MAX), Some(u64::MAX), true),
    ];
    for kind in kinds {
        for &(stream, seq, end) in &shapes {
            for body in bodies {
                let header = Header {
                    kind,
                    corr: CORR,
                    stream,
                    seq,
                    end,
                };
                let enc = encode_frame(&header, body, MAX_FRAME_DEFAULT).unwrap();
                let (h, b, consumed) = decode_frame(&enc, MAX_FRAME_DEFAULT).unwrap();
                assert_eq!(h, header, "header round-trip {header:?}");
                assert_eq!(&b[..], *body, "body round-trip");
                assert_eq!(consumed, enc.len());
            }
        }
    }
}

#[test]
fn back_to_back_records_decode_in_sequence() {
    // §4.1: records are written back-to-back with no padding; the next length
    // begins at the octet after the previous frame-bytes.
    let h1 = Header::single_shot(FrameKind::Request, CORR);
    let h2 = Header::single_shot(FrameKind::Response, CORR);
    let b1: &[u8] = &[0x01, 0x02];
    // b2's first byte must not be a header tag @2/@3/@4: those positions right
    // after corr are header-owned (lib.rs note #2), so an opaque body must not
    // begin with bare 0x02/0x03/0x04. 0x42 is a body tag @0x42 (> @4).
    let b2: &[u8] = &[0x42];
    let mut stream = encode_frame(&h1, b1, MAX_FRAME_DEFAULT).unwrap();
    stream.extend_from_slice(&encode_frame(&h2, b2, MAX_FRAME_DEFAULT).unwrap());

    let (dh1, db1, c1) = decode_frame(&stream, MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(dh1, h1);
    assert_eq!(db1, b1);
    let (dh2, db2, c2) = decode_frame(&stream[c1..], MAX_FRAME_DEFAULT).unwrap();
    assert_eq!(dh2, h2);
    assert_eq!(db2, b2);
    assert_eq!(c1 + c2, stream.len());
}

// ---------------------------------------------------------------------------
// Strict / canonical decode rejections (RFC 0003 §4.5)
// ---------------------------------------------------------------------------

#[test]
fn reject_zero_length() {
    // §4.1: a length of 0 is illegal (every frame has a non-empty header).
    assert_eq!(
        decode_frame(&[0x00], MAX_FRAME_DEFAULT),
        Err(WireError::ZeroLength)
    );
}

#[test]
fn reject_length_over_max_frame() {
    // §4.3: a length exceeding the receiver's max_frame is a framing violation,
    // rejected before the body is read. max_frame=10, length=200 (0xc8 0x01).
    let input = [0xc8, 0x01, 0xaa, 0xbb];
    assert_eq!(
        decode_frame(&input, 10),
        Err(WireError::FrameTooLarge {
            length: 200,
            max_frame: 10
        })
    );
}

#[test]
fn reject_non_minimal_length() {
    // §4.2: a non-minimal (overlong) length varint is a framing violation.
    // 0x80 0x00 is a non-minimal encoding of 0 (and 0 is also illegal length).
    // Use 0x81 0x00 = non-minimal encoding of 1.
    let input = [0x81, 0x00, 0xaa];
    match decode_frame(&input, MAX_FRAME_DEFAULT) {
        Err(WireError::Hcpbin(_)) => {}
        other => panic!("expected Hcpbin(NonMinimal), got {other:?}"),
    }
}

#[test]
fn reject_truncated_record() {
    // §4.5: EOF mid-record. length says 19 but only a few body bytes present.
    let header = Header::single_shot(FrameKind::Request, CORR);
    let full = encode_frame(&header, &[], MAX_FRAME_DEFAULT).unwrap();
    let truncated = &full[..full.len() - 5];
    assert_eq!(
        decode_frame(truncated, MAX_FRAME_DEFAULT),
        Err(WireError::Truncated)
    );
}

#[test]
fn reject_invalid_kind() {
    // §4.4.1 step 1: kind must be 0..=4. Build a header record with kind=5.
    // length=19, then 00 05 (tag@0 kind=5) 01 <16 corr>.
    let mut input = vec![0x13, 0x00, 0x05, 0x01];
    input.extend_from_slice(&CORR);
    assert_eq!(
        decode_frame(&input, MAX_FRAME_DEFAULT),
        Err(WireError::InvalidKind(5))
    );
}

#[test]
fn reject_missing_kind() {
    // §4.4.1: kind(@0) is required. A header starting at @1 (corr only) is malformed.
    // length=17, then 01 <16 corr> (no @0).
    let mut input = vec![0x11, 0x01];
    input.extend_from_slice(&CORR);
    match decode_frame(&input, MAX_FRAME_DEFAULT) {
        Err(WireError::MalformedHeader(_)) => {}
        other => panic!("expected MalformedHeader, got {other:?}"),
    }
}

#[test]
fn reject_end_without_stream() {
    // §4.4.1 decoder invariant step 5: @4 (end) is INVALID if @2 (stream) is absent.
    // header: 00 00 (kind=req) 01 <corr> 04 01 (end without stream). len = 21 = 0x15.
    let mut input = vec![0x15, 0x00, 0x00, 0x01];
    input.extend_from_slice(&CORR);
    input.extend_from_slice(&[0x04, 0x01]);
    match decode_frame(&input, MAX_FRAME_DEFAULT) {
        Err(WireError::MalformedHeader(_)) => {}
        other => panic!("expected MalformedHeader (end without stream), got {other:?}"),
    }
}

#[test]
fn reject_non_ascending_header_tags() {
    // §4.4.1 / RFC 0002 §6.2: header fields MUST be in strictly ascending tag
    // order. corr(@1) before kind(@0) is a malformed header surfaced via hcpbin.
    // header: 01 <corr> 00 00 -> @1 then @0 (descending). len = 19 = 0x13.
    let mut input = vec![0x13, 0x01];
    input.extend_from_slice(&CORR);
    input.extend_from_slice(&[0x00, 0x00]);
    // hcpbin's RecordReader rejects the descending tag (NonAscendingTag).
    match decode_frame(&input, MAX_FRAME_DEFAULT) {
        Err(WireError::Hcpbin(_)) | Err(WireError::MalformedHeader(_)) => {}
        other => panic!("expected a header-order rejection, got {other:?}"),
    }
}
