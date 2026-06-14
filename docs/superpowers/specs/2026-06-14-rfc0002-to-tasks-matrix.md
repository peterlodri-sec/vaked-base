# RFC 0002 → tasks traceability matrix (hcpbin codec)

- **Status:** Draft (planning artifact — the implementation work is future / dependency-blocked; this spec is the plan + traceability oracle, not code to merge now)
- **Created:** 2026-06-14
- **Track:** Protocol / WP3 (Litany wire)
- **Scope owner:** WP3 (HCP wire protocol), per [`docs/superpowers/plans/2026-06-14-wp3-kickoff.md`](../plans/2026-06-14-wp3-kickoff.md)
- **Subject crate:** [`protocol/hcp/hcpbin/`](../../../protocol/hcp/hcpbin)

## 1. Objective

Produce and maintain a **traceability matrix** that maps every `hcpbin`
encoding rule and worked example in **RFC 0002 §6** (plus the §5.1 scalar table
and §10/§10.1 worked frames) to:

1. a concrete codec function (existing or to-be-created) in
   [`protocol/hcp/hcpbin/src/lib.rs`](../../../protocol/hcp/hcpbin/src/lib.rs);
2. a concrete test (existing or to-be-created), with the RFC-derived **golden
   vector** that anchors it; and
3. a **status** in one of three buckets — done in WP3-S1, deferred (still
   hcpbin's job), or out-of-scope for the payload codec entirely.

The matrix is the single artifact a WP3 engineer reads to know what is encoded,
what is verified, what remains, and *where in the RFC* each obligation lives. It
also drives a **documentation-fix action** (§7): the WP3 kickoff plan (and, per
the task, issue #167) point at "RFC 0002 §4 / Appendix A" for the byte encoding
and golden vectors. That is stale: the byte encoding is in **§6**, the golden
vectors are the worked-example hex blocks (§6.1.1, §6.3.1, §6.6.1, §6.7.1, §10,
§10.1), and Appendix A is *codegen* examples, not byte vectors.

### 1.1 Why three status buckets (not two)

The naive "done vs deferred" split reproduces the very error this matrix flags.
The **frame header** (`kind`/`corr`/`stream`/`seq`/`end`) is encoded *under*
`hcpbin` canonicality but is **not** part of the `hcpbin` value codec: it
occupies the reserved `@0` space and is owned by the wire layer (RFC 0002 §4.2
and the §6 scope note: "the outer frame container … is the Litany Wire's
concern"; RFC 0003 §4.4 / §4.4.1 own the header's wire form). Folding the header
into "deferred hcpbin work" would repeat the §4-confusion. Hence:

- **DONE (WP3-S1)** — implemented and verified on M1.
- **DEFERRED (still hcpbin's job)** — belongs in this crate, not yet written.
- **OUT OF SCOPE (wire layer, RFC 0003)** — the frame header; tracked here only
  so the boundary is explicit and the matrix is exhaustive.

## 2. Inputs / oracles

| Oracle | Path / locator | Role |
|--------|----------------|------|
| RFC 0002 §5.1 scalar table | [`protocol/rfcs/0002-hcplang.md`](../../../protocol/rfcs/0002-hcplang.md) L317–331 | Canonical encoding per scalar type. |
| RFC 0002 §6.1 primitives + strict varint decode | §6.1 L451–471 | Varint (minimal encode / strict decode), float, length prefixes. |
| RFC 0002 §6.1.1 worked examples (primitives) | §6.1.1 L473–538 | Golden hex for u/i varints, bool, f32, string, bytes. |
| RFC 0002 §6.2 records/frames | §6.2 L540–569 | Ascending-tag-order field encoding, self-delimitation. |
| RFC 0002 §6.3 defaults/optionals/omission | §6.3 L571–620 | Canonical omission; implicit-default table; "no default → always emit". |
| RFC 0002 §6.3.1 worked examples (defaults) | §6.3.1 L622–669 | Golden hex for nested-record omission + optional aggregates. |
| RFC 0002 §6.4 scalar canonicalisation | §6.4 L671–697 | Bool strictness, NaN/`-0.0`, NFC pinned to Unicode 15.1.0. |
| RFC 0002 §6.5 hash + registry | §6.5 / §6.5.1 L699–736 | `varint(algo) varint(len) digest`; registry lengths; skip-unknown. |
| RFC 0002 §6.6 lists/maps | §6.6 L738–745 | Count-prefixed lists (order kept); maps sorted by encoded-key bytes. |
| RFC 0002 §6.6.1 worked examples (lists/maps) | §6.6.1 L825–866 | Golden hex for a list and a sorted map. |
| RFC 0002 §6.7 unions | §6.7 L747–772 | `varint(arm-tag) varint(byte-len) value`; skip/preserve unknown arms. |
| RFC 0002 §6.7.1 worked examples (unions/enums) | §6.7.1 L774–823 | Golden hex for known/unknown union arms and enum cases. |
| RFC 0002 §6.8 canonicality requirement | §6.8 L868–893 | Fixed-point + cross-impl byte agreement. |
| RFC 0002 §10 / §10.1 worked frames | §10 L1009–1117; §10.1 L1119–1160 | End-to-end golden frames (ToolCallRequest/Response, ToolEvent, map frame). |
| Example schema | [`protocol/hcplang/examples/hcp-core.hcplang`](../../../protocol/hcplang/examples/hcp-core.hcplang) | The concrete types the §10 vectors encode. |
| Existing codec | [`protocol/hcp/hcpbin/src/lib.rs`](../../../protocol/hcp/hcpbin/src/lib.rs) | What is already done (WP3-S1). |
| Existing golden tests | [`protocol/hcp/hcpbin/tests/golden.rs`](../../../protocol/hcp/hcpbin/tests/golden.rs) | Blind, RFC-derived golden suite (verified: `cargo test` → 50 passed). |

**Boundary oracle (out-of-scope rows):** RFC 0002 §4.2 (header reserved,
implicit), §6 scope note (L446–450), and RFC 0003 §4.4 / §4.4.1 (header wire
form: `kind` varint enum, `corr` 16-byte UUID, `stream`/`seq` optional varints,
`end` one byte).

## 3. File layout (paths to create / touch)

Create:

- `docs/superpowers/specs/2026-06-14-rfc0002-to-tasks-matrix.md` — **this file**
  (the matrix + plan).

Touch under WP3 execution (each is a deferred row's target, not created now):

- `protocol/hcp/hcpbin/src/lib.rs` — add the deferred encode/decode functions
  (string, f32/f64, uuid, timestamp, records, defaults, lists/maps, unions,
  enums). Removes the `TODO(WP3-S2)` block at L488–498.
- `protocol/hcp/hcpbin/tests/golden.rs` — extend with the §6.3.1 / §6.6.1 /
  §6.7.1 / §10 / §10.1 golden vectors.
- `protocol/hcp/hcpbin/Cargo.toml` — add the NFC normalisation dependency when
  the `string` row is taken (see §6, dependency D3 — crate not chosen here).

Cross-impl rows (§6.8) and the frame-header out-of-scope rows do **not** touch
this crate; they are pointers to the wire crate
(`protocol/hcp/litany/`, WP3-S3+) and to a future Zig codec, neither of which
exists yet.

## 4. The matrix

Status legend: **D** = done in WP3-S1 · **F** = deferred, still hcpbin's job ·
**X** = out of scope for the payload codec (wire layer).

Sprint column: per kickoff "Code home" (hcpbin = WP3-S1 + S2) and the lib.rs
note ("string … WP3-S2"), deferred hcpbin rows land in **S2**. (See §8 flag F2:
the kickoff *sprint table* row for S2 says "RFC 0003 frame layer", which
conflicts with the Code-home line — treated as a possibly-stale table row.)

### 4.1 Scalars & primitives (§5.1, §6.1, §6.4)

| RFC rule | Oracle | Codec fn (`hcpbin::`) | Test | Status | Sprint |
|----------|--------|-----------------------|------|--------|--------|
| Unsigned LEB128 varint, minimal | §6.1, §6.1.1 (`0,127,128,255,16384`) | `encode_uvarint` / `decode_uvarint`, `Writer::put_uvarint` / `Reader::get_uvarint` | `golden.rs::uvarint_encode_golden`, `uvarint_decode_golden`, `uvarint_round_trip_*` | **D** | S1 |
| Strict varint decode (reject non-minimal / overlong / width-overflow) | §6.1 "Strict varint decode" | `Reader::get_uvarint` (+ `get_uvarint_width`) | `golden.rs::uvarint_strict_reject_overlong_minimal_violation`, `uvarint_strict_reject_truncated`, `uvarint_strict_reject_trailing`, `uvarint_strict_reject_overflow_64bit` | **D** | S1 |
| Width-bound unsigned (`u8`..`u64`) | §5.1, §6.1 | `decode_*`/`Reader::get_u8..get_u64` | lib `tests::unsigned_width_overflow` | **D** | S1 |
| Signed zig-zag varint, sign-fill bound to width `k` (`i8`..`i64`) | §6.1, §6.1.1 (`i8(0,1,-1,127,-128)`, `i64(-1, MIN)`) | `encode_i8..i64` / `decode_i8..i64`, `Writer::put_ivarint_k` | `golden.rs::i8_encode_golden`, `i8_decode_golden`, `i64_encode_golden`, `i64_decode_golden`, `signed_round_trip_all_widths`, `signed_strict_reject_*` | **D** | S1 |
| `bool` = `0x00`/`0x01`, any other byte rejected | §6.1.1, §6.4 | `encode_bool` / `decode_bool`, `Writer::put_bool` / `Reader::get_bool` | `golden.rs::bool_encode_golden`, `bool_decode_golden`, `bool_strict_reject_non_canonical_byte`, `bool_strict_reject_truncated_and_trailing` | **D** | S1 |
| `bytes` length-prefixed (varint + raw) | §6.1, §6.1.1 (`[]→0x00`, `key→03 6b 65 79`) | `encode_bytes` / `decode_bytes`, `Writer::put_bytes` / `Reader::get_bytes` | `golden.rs::bytes_encode_golden`, `bytes_decode_golden`, `bytes_round_trip`, `bytes_strict_reject_*` | **D** | S1 |
| `f32`/`f64` little-endian IEEE-754 + NaN/`-0.0` canonicalisation | §5.1, §6.1, §6.4; oracle hex in §6.1.1 (`f32(0.0/1.0/NaN/-0.0)`) | **create** `encode_f32`/`decode_f32`, `encode_f64`/`decode_f64` (+ `Writer::put_f32`/`put_f64`, `Reader::get_f32`/`get_f64`) | **create** `f32_golden` (NaN→`00 00 c0 7f`, `-0.0`→`00 00 00 00`), `f64_golden`, `float_canonicalisation` | **F** | S2 |
| `string` UTF-8, length-prefixed, **NFC @ Unicode 15.1.0** | §5.1, §6.1, §6.4; oracle hex in §6.1.1 (`""→00`, `hi→02 68 69`, `café→05 …`) | **create** `encode_string`/`decode_string` (+ `Writer::put_string`/`Reader::get_string`) | **create** `string_golden`, `string_nfc_precompose` (decomposed `café` → precomposed bytes), `string_reject_non_nfc` (per §6.4 / open-q 7: decoder MAY reject non-NFC) | **F** | S2 |
| `timestamp` = `i64` ns, varint-encoded; **no implicit default** | §5.1, §6.3, §10.1 (ToolEvent `at`) | **create** `encode_timestamp`/`decode_timestamp` (thin over `i64` varint) | **create** `timestamp_golden` (`1718284800000000000` → its varint), `timestamp_always_emitted` (§6.3) | **F** | S2 |
| `uuid` = 16 opaque bytes, field order, no endianness | §5.1, §6.3, §10.1 (ToolEvent `id`, WatchControl `session`) | **create** `encode_uuid`/`decode_uuid` (16 raw bytes, no length prefix) | **create** `uuid_golden` (16 bytes verbatim), `uuid_always_emitted` (§6.3 no default) | **F** | S2 |

### 4.2 `hash` (§6.5, §6.5.1)

| RFC rule | Oracle | Codec fn | Test | Status | Sprint |
|----------|--------|----------|------|--------|--------|
| `hash` = `varint(algo) varint(len) digest`; known algo `len` MUST match registry | §6.5 (SHA-256=0x01/32, BLAKE3-256=0x02/32) | `encode_hash` / `decode_hash`, `Writer::put_hash` / `Reader::get_hash`, `Hash`, `known_hash_digest_len` | `golden.rs::hash_encode_golden_sha256`, `hash_decode_golden_sha256`, `hash_round_trip_known_algos`, `hash_strict_reject_known_algo_wrong_length`, `hash_strict_reject_truncated_digest`; lib `tests::hash_*` | **D** | S1 |
| Unknown algo-id self-delimiting via `len`, opaque round-trip | §6.5.1 (`0x11`–`0xFF` user range) | `decode_hash` / `get_hash` (no registry check on unknown) | `golden.rs::hash_unknown_algo_round_trips`; lib `tests::hash_unknown_algo_roundtrips_opaque`, `hash_self_delimiting` | **D** | S1 |

### 4.3 Aggregates, records, defaults (§6.2, §6.3, §6.6)

| RFC rule | Oracle | Codec fn | Test | Status | Sprint |
|----------|--------|----------|------|--------|--------|
| Record/frame: present fields in **ascending tag order**; reject out-of-order / duplicate tags | §6.2 rule 1; §6.3.1 | **create** `encode_record`/`decode_record` (tag-sorted emit; ordering/dup checks) | **create** `record_tag_order_golden` (§6.3.1 `Outer{...,z:1}`→`02 01`), `record_reject_out_of_order`, `record_reject_duplicate_tag` | **F** | S2 |
| Self-delimitation of nested record / string / bytes / hash / list / map / union (skip unknown nested) | §6.2 | (part of `decode_record`; skip-unknown-field helper) | **create** `record_skip_unknown_field` | **F** | S2 |
| Canonical omission: absent `T?` omitted; default-valued non-optional omitted; nested all-default record omitted | §6.3, §6.3.1 | (encode path of `encode_record` + per-type default test) | **create** `default_omission_golden` (§6.3.1 nested all-default → `02 01`; `x:1` case → `01 02 01 02 01`) | **F** | S2 |
| Implicit-default table (bool/int/float/str/bytes/list/map/enum/record) | §6.3 table | (default predicate per type used by `encode_record`) | **create** `implicit_default_table` | **F** | S2 |
| No implicit default → **always emit**: `union`, `hash`, `uuid`, `timestamp` | §6.3; §10 (`result` union always emitted) | (always-emit branch of `encode_record`) | **create** `always_emit_no_default_types` | **F** | S2 |
| Optional aggregate 3-state (`list<T>?` / `map<K,V>?`: absent vs present-empty vs non-empty) | §5.3 table; §6.3.1 | (optional-aggregate encode/decode) | **create** `optional_aggregate_three_state` (§6.3.1: `optional_attrs:[]`→`02 00`; absent→empty) | **F** | S2 |
| `list<T>` = `varint(count)` + elements in order | §6.6, §6.6.1 | **create** `encode_list`/`decode_list` (generic over element fn) | **create** `list_golden` (§6.6.1 `["a","bc"]`→`01 02 01 61 02 62 63`) | **F** | S2 |
| `map<K,V>` = `varint(count)` + pairs **sorted by encoded-key bytes**; reject dup keys | §6.6, §6.6.1 | **create** `encode_map`/`decode_map` (sort by `hcpbin(key)`) | **create** `map_sorted_key_golden` (§6.6.1 zebra/apple/banana → sorted), `map_reject_duplicate_key`, `map_decode_reject_unsorted` | **F** | S2 |

### 4.4 Unions & enums (§6.7, §6.7.1, §5.4)

| RFC rule | Oracle | Codec fn | Test | Status | Sprint |
|----------|--------|----------|------|--------|--------|
| Union = `varint(arm-tag) varint(byte-len) value`; length prefix on **every** arm | §6.7, §6.7.1 | **create** `encode_union`/`decode_union` | **create** `union_known_arm_golden` (§6.7.1 `text("hi")`→`01 03 02 68 69`; `binary([00,ff])`→`02 03 02 00 ff`) | **F** | S2 |
| Unknown arm: skip by `byte-len`, preserve raw, re-emit verbatim | §6.7, §6.7.1 (V2 arm @3) | (unknown-arm variant holding raw bytes) | **create** `union_unknown_arm_roundtrip` (§6.7.1 `03 05 01 02 03 04 05` byte-for-byte) | **F** | S2 |
| Known-arm `byte-len` mismatch → `malformed_frame` error (not appended to eventd) | §6.7 (refs RFC 0003 §9.2) | (validation in `decode_union`) | **create** `union_known_arm_len_mismatch_rejected` | **F** | S2 |
| Enum = varint case value; case 0 default; unknown case preserved as `unknown(N)` | §5.4, §6.7.1 | **create** `encode_enum`/`decode_enum` | **create** `enum_golden` (§6.7.1 `info→00`, `warn→01`), `enum_unknown_case_roundtrip` (`unknown(5)`→`05`) | **F** | S2 |

### 4.5 Canonicality + end-to-end (§6.8, §10, §10.1)

| RFC rule | Oracle | Codec fn | Test | Status | Sprint |
|----------|--------|----------|------|--------|--------|
| Fixed-point: `encode(decode(encode(v)))==encode(v)`; whole-value consume-all (trailing bytes rejected) | §6.8 | `decode_all` wrapper (`TrailingBytes`) over implemented types | covered for done types by every `*_round_trip*` + `*_reject_trailing` test in `golden.rs` | **D (for implemented types)** | S1 |
| Fixed-point over **all** types (records/unions/maps/string/float/uuid/timestamp) | §6.8 | (extend `decode_all` usage as rows above land) | **create** `fixed_point_all_types` | **F** | S2 |
| Cross-impl byte agreement (two conforming impls produce identical bytes) | §6.8 | n/a — needs a **second** implementation | **create** cross-impl vector check once a 2nd codec exists (e.g. Zig or BEAM) | **F** | S2+ (blocked, see §6 D4) |
| §10 worked frame: `ToolCallRequest{tool="fs.read", args=0x6b6579}` → `01 07 66 73 2e 72 65 61 64 02 03 6b 65 79` | §10 L1045–1054; schema `hcp-core.hcplang` | (composition of `encode_record` + `string`/`bytes`) | **create** `frame_toolcallrequest_golden` | **F** | S2 |
| §10 worked frame: `ToolCallResponse` relic-arm (`01 03 22 01 20 <32B>`) + default-severity omission | §10 L1060–1077 | (`encode_record` + union + hash) | **create** `frame_toolcallresponse_relic_golden`, `frame_response_default_severity_omitted` | **F** | S2 |
| §10.1 frames: response non-default severity, default-severity-omitted, ToolEvent (uuid+timestamp+enum+absent list), map-containing WatchControl | §10.1 L1081–1160 | (composition of the above) | **create** `frame_response_severity_err_golden`, `frame_toolevent_golden`, `frame_watchcontrol_map_golden` | **F** | S2 |

### 4.6 Out of scope for the payload codec (frame header — wire layer)

| Item | Why out of scope | Real home |
|------|------------------|-----------|
| Frame header `kind`/`corr`/`stream`/`seq`/`end` | Reserved `@0` space, supplied/validated by the wire layer; NOT an `hcpbin` declared-value type (§4.2; §6 scope note L446–450) | RFC 0003 §4.4 / §4.4.1; crate `protocol/hcp/litany/` (WP3-S3+) |
| Outer frame container: magic, **length-framing**, version negotiation | "the outer frame container … is the Litany Wire's concern" (§6 scope note) | RFC 0003 §4.2 (length prefix), §4.3 (max-frame guard) |
| Schema digest = `SHA-256(litanyfmt(schema))` | Schema-tooling concern, not a value-codec rule (it *uses* §6.5 hash encoding) | RFC 0002 §8; `litanyfmt` tooling |
| `@redact` projection / `litanydump` rendering | Presentation layer; value still encodes normally (§11) | §7 codegen + tooling, not the codec |

## 5. Algorithm / design (how a deferred row is taken)

Each deferred (**F**) row is a self-contained, TDD-shaped unit:

1. **Derive the golden vector blind from the RFC oracle cell.** Copy the exact
   hex from the cited worked-example block into a `tests/golden.rs` `const`
   table (the existing suite's pattern — see its header comment on adversarial
   independence: expectations come *only* from RFC 0002).
2. **Write the failing test first.** It will not compile until the codec
   function exists — that is the intended red state (mirrors the note atop
   `tests/golden.rs`).
3. **Implement the codec function** in `src/lib.rs`, matching the existing
   `Writer::put_*` / `Reader::get_*` plus free-function `encode_*`/`decode_*`
   (whole-value, consume-all via `decode_all`) shape. Reuse the primitive layer:
   records/lists/maps/unions are all compositions of varints + the existing
   length-prefix/`bytes` primitives.
4. **Enforce canonicality on the decode side** (§6.8): reject out-of-order /
   duplicate tags (§6.2), unsorted / duplicate map keys (§6.6), non-NFC strings
   (§6.4, per open-q 7), known-arm length mismatch (§6.7), and leftover bytes
   (`TrailingBytes`).
5. **Order of attack** (dependency-respecting): `string`, `f32/f64`, `uuid`,
   `timestamp` (leaf scalars) → `enum`, `list`, `map`, `union` (containers) →
   `record`/`frame` + defaults (§6.2/§6.3) → §10/§10.1 end-to-end frames →
   §6.8 all-types fixed-point. The §10 frames are the integration capstone; they
   pass only when every leaf below them is correct.

This design adds **no new abstractions** beyond the established Reader/Writer +
free-function pair; every row is a composition of primitives already in the
crate.

## 6. Dependencies on other sprints / external artifacts

- **D1 — RFC 0002 frozen.** Precondition for any row (kickoff pre-start gate,
  Jun 21). The §6 worked-example hex is the frozen oracle; a spec edit to those
  blocks invalidates affected golden rows.
- **D2 — WP3-S1 primitive layer (done).** All container rows compose over the
  varint / `bytes` / `bool` / `hash` primitives already in `src/lib.rs`.
- **D3 — NFC normalisation data, pinned to Unicode 15.1.0** (§6.4). The
  `string` row has a hard dependency on a normalisation source whose Unicode
  version is **15.1.0** — the version pin is part of the canonical encoding
  (a different table changes the bytes and breaks the `eventd` hash chain). A
  concrete crate is **not chosen here** (do not guess); selection must verify it
  exposes / can be pinned to Unicode 15.1.0 NFC data. Added to `Cargo.toml` when
  the row is taken.
- **D4 — second implementation** for the cross-impl byte-agreement row (§6.8).
  Blocked until a Zig or BEAM codec exists; no Zig `hcpbin` codec exists in the
  repo today (`find … -name '*.zig'` → none under `protocol/`). This is the only
  genuinely *cross-component* row.
- **D5 — wire crate** `protocol/hcp/litany/` (WP3-S3+) for the out-of-scope
  frame-header rows (RFC 0003). Not this crate's work; listed for boundary
  completeness only.
- **D6 — eventd** integration (WP3-S5) consumes canonical bytes; it depends on
  this matrix's §6.8 row, not vice-versa.

## 7. Documentation-fix action (stale §4 / Appendix-A references)

The byte-encoding home moved to §6 during RFC 0002's drafting, but the WP3
kickoff plan still points at §4 / Appendix A. **Fix
[`docs/superpowers/plans/2026-06-14-wp3-kickoff.md`](../plans/2026-06-14-wp3-kickoff.md)**
(exact lines, verified against the file):

| Kickoff line | Stale text | Correct reference |
|--------------|-----------|-------------------|
| L24 (sprint table, WP3-S1 deliverable) | "hcpbin varint + frame header + payload (RFC 0002 §4)" | Byte encoding is **§6**; "frame header" is **not** hcpbin's (RFC 0002 §4.2 → RFC 0003 §4.4); "payload" framing is the wire's outer container (RFC 0003 §4.2, §6 scope note). |
| L41 (First task) | "implement encode/decode per RFC 0002 §4: varint (LEB128), frame header (type, flags, length), payload framing" | Per **RFC 0002 §6** (§6.1 varints, §6.4 scalars, §6.5 hash, §6.2/§6.3 records, §6.6 lists/maps, §6.7 unions). The "frame header (type, flags, length)" shape is a **phantom** — the real header is `kind`/`corr`/`stream`/`seq`/`end`, owned by the wire layer (RFC 0003 §4.4). "payload framing" (outer container/length) is RFC 0003 §4.2. |
| L43 (First task) | "Golden vectors: derive from RFC 0002 Appendix A." | **Appendix A is *codegen* examples (Zig structs / Erlang records), not byte vectors.** Golden vectors are the worked-example hex blocks: **§6.1.1, §6.3.1, §6.6.1, §6.7.1, §10, §10.1**. (There is no "Appendix A" of byte vectors.) |
| L43 (First task) | "All tests pass on `dev-cx53`." | The hcpbin codec is a **pure, syscall-free** library; `cargo test` on macOS M1 is the full oracle (verified: 50 pass). dev-cx53 is **not** required for the codec layer — only the **≤10µs perf baseline** (kickoff L54, WP3-S6) genuinely needs the 8-core Linux box. |

**Issue #167 (per task instruction):** apply the same correction — repoint the
"RFC 0002 §4 / Appendix A" wording to "§6 + worked examples §6.1.1/§6.3.1/
§6.6.1/§6.7.1/§10". *Note on verifiability:* #167 could not be inspected from
this environment (`gh issue view 167` returned nothing; no `.github` match). The
verifiable artifact for the stale wording is the kickoff doc above; the #167 fix
mirrors it. Do not transcribe #167 text that cannot be read here.

This docs-fix is a **regression-style** action: the §6/§4 boundary is exactly
the three-bucket split in §1.1, so the matrix and the docs-fix are the same
correction expressed twice.

## 8. Open flags (non-blocking)

- **F1 — deferred-row sprint assignment is itself ambiguous in the kickoff.**
  "Code home" (kickoff L13: `protocol/hcp/hcpbin/` = WP3-S1, S2) and `src/lib.rs`
  ("string … WP3-S2") put hcpbin completion in **S2**; the kickoff *sprint table*
  L25 labels S2 "Frame layer (RFC 0003)". This matrix follows the Code-home /
  lib.rs reading (hcpbin completion = S2) and flags the table row as
  possibly-stale; resolve when WP3 sprints are re-baselined.
- **F2 — `string` row carries a non-code dependency** (D3: pinned Unicode 15.1.0
  NFC data). Without the version pin the determinism / eventd-chain property
  (§6.4, §9) breaks. Name the source explicitly at row time; do not assume the
  default Unicode version of whatever crate is chosen.

## 9. Test plan — local M1 vs dev-cx53 / Linux

**On macOS M1 (full oracle for correctness):**

- `cd protocol/hcp/hcpbin && cargo test` runs the lib unit tests + the blind
  golden suite (`tests/golden.rs`) + the integration golden suite. **Verified
  now: 50 passed, 3 suites.** This is the complete oracle for **every D row and
  every F row** — the codec is pure (no syscalls, no I/O, no namespaces), so
  there is *nothing* in the value-codec layer that requires Linux.
- Each F row is "done" when its `cargo test` golden + round-trip + strict-reject
  assertions pass on M1, byte-for-byte against the cited RFC hex.
- Zig note: there is **no** Zig `hcpbin` codec in the repo. If/when one is added
  for the cross-impl row (§6.8, D4), it will likewise be a pure codec; the
  `zig build -Dtarget=x86_64-linux` *compile-only* constraint in the environment
  applies to the **namespace daemons**, not to a pure codec — a Zig codec would
  build and unit-test on M1 directly. The cross-impl row's only real requirement
  is "a second conforming implementation exists", not "Linux".

**Requires dev-cx53 / Linux (not correctness):**

- **Perf baseline only** — kickoff success criterion ≤10µs/frame
  encode/decode on the 8-core box (kickoff L54), latency-vs-grpc/cbor (WP3-S6).
  This is a benchmark, not a conformance gate, and is the *sole* dev-cx53
  dependency for this work. (dev-cx53 is off-limits for 6h per the task; this
  does not block authoring or any correctness row.)

## 10. Acceptance criteria

This **planning artifact** is accepted when:

1. **Coverage.** Every §6 subsection (§6.1–§6.8) and §5.1 scalar **and** every
   worked-example block (§6.1.1, §6.3.1, §6.6.1, §6.7.1, §10, §10.1) maps to a
   row in §4, with an oracle cell, a codec fn (existing or named-to-create), a
   test (existing or named-to-create), and a status bucket.
2. **Three-bucket integrity.** The frame header appears only under **§4.6
   (out of scope)** — never as a "deferred hcpbin" row — preserving the §4.2 / §6
   boundary (§1.1).
3. **Done rows are verifiable now.** Every **D** row cites an existing test
   function that passes under `cargo test` on M1 (`50 passed` reproduces).
4. **Deferred rows are actionable.** Every **F** row names the target codec fn,
   the golden hex source, the test to create, and a sprint, with no undecided
   dependency left unnamed (D3/D4 called out).
5. **Docs-fix logged.** §7 lists the exact stale kickoff lines (L24, L41, L43)
   with their §6 / worked-example replacements, and records the #167 correction
   plus its verifiability caveat.

Downstream (WP3-S2 execution, out of this artifact's scope) is "done" when all
**F** correctness rows flip to **D** under M1 `cargo test`, and the perf row is
green on dev-cx53 (WP3-S6).