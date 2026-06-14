# hcpbin aggregate-value codec — implementation plan (spec)

## Status

Spec (2026-06-14). Planning artifact for the **aggregate layer of the `hcpbin`
codec** (records/frames, unions, lists/maps, enums) in the WP3 HCP wire-protocol
epic ([`docs/superpowers/plans/2026-06-14-wp3-kickoff.md`](../plans/2026-06-14-wp3-kickoff.md)).

This is the layer the WP3-S1 `hcpbin` crate explicitly defers — see the in-code
TODOs at [`protocol/hcp/hcpbin/src/lib.rs`](../../../protocol/hcp/hcpbin/src/lib.rs)
lines 494-498 ("records/frames (§6.2), defaults/optionals (§6.3), lists/maps
(§6.6), unions/enums (§6.7)"). It sits **above** WP3-S1 (primitives: varint,
signed varint, bool, bytes, hash — landed) and **below** WP3-S2 (the RFC 0003
frame/wire layer, which carries an `hcpbin` body and prepends the frame header).
The work is dependency-blocked on a small scalar-completion gap (§7) and is not
codeable in full today; the deliverable here is the implementation-ready plan.

> **Correction to the kickoff / issue #167 wording.** The kickoff (line 43) and
> issue #167 cite "RFC 0002 §4 / Appendix A" for the byte encoding and golden
> vectors. That is **stale**. The canonical sources this spec cites are:
> - byte encoding of values → **RFC 0002 §6** ([`protocol/rfcs/0002-hcplang.md`](../../../protocol/rfcs/0002-hcplang.md), "hcpbin encoding rules"), with the type system in **§5**;
> - the frame header (`kind`/`corr`/`stream`/`seq`/`end`) → the **WIRE layer, RFC 0003**, explicitly **NOT** `hcpbin` (RFC 0002 §4.2 + §6 scope note; mirrored in [`protocol/hcp/hcpbin/src/lib.rs`](../../../protocol/hcp/hcpbin/src/lib.rs) lines 22-23, 497-498);
> - golden vectors → RFC 0002 worked examples **§6.1.1, §6.3.1, §6.6.1, §6.7.1, §10** — there is **no Appendix A in RFC 0002** (the only `Appendix A` in the RFC set is RFC 0003 Appendix A, the `hcp.wire` control schema).

## 1. Objective

Extend `hcpbin` from a primitive-scalar codec to a **complete canonical
value codec** for every `.hcplang` type that appears in a frame/record *body*:

1. **Records and frames** (RFC 0002 §6.2): present fields emitted in strictly
   ascending tag order; nested records framed by `varint(byte-len)`; out-of-order
   and duplicate tags rejected on decode.
2. **Default omission** (RFC 0002 §6.3, §6.3.1), including the subtle
   **all-default nested record** rule (a non-optional record-typed field whose
   value equals "every field at its default" MUST be omitted) and the
   three-state `T?`/`list<T>?`/`map<K,V>?` distinction (§5.3 table).
3. **Unions** (RFC 0002 §6.7): `varint(arm-tag) varint(byte-len) value`, length
   prefix on **every** arm; **unknown arms preserved** byte-for-byte and re-emitted
   verbatim.
4. **Lists and maps** (RFC 0002 §6.6): lists in element order (significant); maps
   sorted by **canonical key order** with insertion-order independence and
   duplicate-key rejection.
5. **Enums** (RFC 0002 §5.4): integer-valued cases, case `0` is the default and
   participates in omission; **unknown cases preserved** and re-emitted verbatim.

The single normative success property is RFC 0002 §6.8: `encode` is uniquely
determined by the value and the schema, and `encode(decode(encode(v))) ==
encode(v)` is a fixed point. This is what `eventd`'s hash chain (§9) and
`litanyreplay` depend on.

**Explicitly OUT of scope** (do not implement here): the frame header
(RFC 0003); transport/framing/handshake/credit (RFC 0003); Zig/BEAM codegen
(RFC 0002 §7 — this layer is the *runtime value codec* that generated code will
call into, not the code generator); `service`/method binding (no wire encoding);
authority/`preceptord` (RFC 0002 §8-§9). Schema-language **parsing** (the
`.hcplang` front-end / `litanyfmt`) is also out of scope — this layer consumes a
type descriptor (§4.1), it does not parse `.hcplang` source.

## 2. Inputs / oracles

No oracle invents bytes the RFC does not give. Every positive expectation is a
worked-example byte string from RFC 0002; every negative expectation is a
spec-cited rejection rule.

| Oracle | Source of truth | What it proves |
|--------|-----------------|----------------|
| **Round-trip fixed point** | RFC 0002 §6.8: `encode(decode(encode(v))) == encode(v)` | Canonicality of aggregate bodies |
| **Records / default omission golden** | RFC 0002 §6.3.1 (nested all-default omit; optional-present `02 00`; `tags:["a","b"]` → `01 02 01 61 01 62`) | Field ordering + omit/emit exactly per §6.3 |
| **List golden** | RFC 0002 §6.6.1 (`tags:["a","bc"]` → `01 02 01 61 02 62 63`) | Element-count prefix + order preservation |
| **Map golden** | RFC 0002 §6.6.1 (`{zebra,apple,banana}` → `01 03 05 61 70 70 6c 65 01 32 06 62 61 6e 61 6e 61 01 33 05 7a 65 62 72 61 01 31`) | Key sort + insertion-order independence (**see §4.4 — this vector disambiguates the §6.6/§6.6.1 contradiction**) |
| **Union golden** | RFC 0002 §6.7.1 (`Payload.text("hi")` → `01 03 02 68 69`; `Payload.binary([00,FF])` → `02 03 02 00 ff`; unknown arm @3 → `03 05 01 02 03 04 05` round-trips verbatim) | Arm `tag/len/value` + unknown-arm preservation |
| **Enum golden** | RFC 0002 §6.7.1 (`info`→`00`, `warn`→`01`, unknown(5)→`05` round-trips) | Case value + unknown-case preservation |
| **Whole-frame golden** | RFC 0002 §10 / §10.1 (`ToolCallRequest{tool="fs.read",args=0x6b6579}` → `01 07 66 73 2e 72 65 61 64 02 03 6b 65 79`; `ToolCallResponse` text/binary/relic variants) | End-to-end record + union + hash composition |
| **Rejection rules (negative)** | RFC 0002 §6.2 rule 1 (out-of-order / duplicate tags), §6.6 (duplicate map keys), §6.1 (overlong/non-minimal length prefixes — inherited from S1) | Every malformed aggregate fails as a typed `DecodeError` |
| **Existing adversarial-independence suite** | ``protocol/hcp/hcpbin/tests/golden.rs`` (`../../../protocol/hcp/hcpbin/tests/golden.rs`) — "written BLIND to the implementation" | This spec extends that discipline to aggregates |

## 3. File layout (paths to create)

The crate `protocol/hcp/hcpbin/` exists and is **standalone** (no Cargo
workspace; verified 2026-06-14). New modules are added under `src/`; new test
files mirror the `golden.rs` blind convention.

```
protocol/hcp/hcpbin/
  src/
    lib.rs            # EXISTS — primitives. Add `pub mod` lines + re-exports.   [EDIT]
    value.rs          # dynamic `Value` model + `Type` descriptor (§4.1)         [NEW]
    schema.rs         # RecordDesc / UnionDesc / EnumDesc / FieldDesc (§4.1)     [NEW]
    record.rs         # §6.2 record/frame encode+decode; §6.3 default omission   [NEW]
    union.rs          # §6.7 union encode+decode; unknown-arm preservation       [NEW]
    collection.rs     # §6.6 list + map encode+decode; key-sort + dedup          [NEW]
    enum_.rs          # §5.4 enum encode+decode; unknown-case preservation       [NEW]
    scalar.rs         # §6.4 string(NFC)/f32/f64; uuid/timestamp (§7 dep gate)   [NEW]
  tests/
    golden.rs         # EXISTS — primitives. Untouched.
    golden_aggregate.rs   # BLIND golden vectors: §6.3.1/§6.6.1/§6.7.1/§10       [NEW]
    fixed_point.rs        # proptest: ∀ typed v: encode(decode(encode(v)))==enc  [NEW]
    rejection_aggregate.rs # negative table: dup/out-of-order tag, dup map key   [NEW]
```

The aggregate golden vectors SHOULD also be emitted as language-agnostic
`.hex` data files under `tests/spec/golden/hcpbin_aggregate/` (mirroring the
WP3-S7 plan, [`docs/superpowers/specs/2026-06-14-wp3-s7.md`](2026-06-14-wp3-s7.md)
§3) so the future Zig codegen target (RFC 0002 §7) and the Python spec harness
([`tests/spec/run_all.py`](../../../tests/spec/run_all.py)) validate the same
corpus. That cross-impl `.hex` emission is a stretch goal here and the hard
deliverable of the differential test in WP3-S7.

## 4. Algorithm / design

### 4.1 The type descriptor is the spine (decode is schema-driven)

**Bare scalars are NOT self-delimiting inside a record body.** RFC 0002 §6.2
frames only `string`/`bytes`/`list`/`map`/`hash`/nested-record/union with a
length or count prefix; `u8..u64`/`i8..i64`/`bool`/`f32`/`f64`/`timestamp`/`uuid`
carry no prefix. Therefore a decoder reading tag `@N` **must already know the
declared type of `@N`** to know how many bytes to consume. The codec is
consequently **schema-driven**: it takes a type descriptor and a value, not just
bytes.

Two cooperating models (`value.rs`, `schema.rs`):

```rust
// value.rs — the dynamic value the codec encodes/decodes.
pub enum Value {
    Bool(bool),
    U64(u64), I64(i64),         // width carried by the Type descriptor
    F32(f32), F64(f64),
    Str(String),               // NFC-normalised on encode (§6.4) — see §7 dep
    Bytes(Vec<u8>),
    Timestamp(i64),            // ns since epoch; no implicit default (§6.3)
    Hash(Hash),                // reuse the existing S1 `Hash` (§6.5)
    Uuid([u8; 16]),
    List(Vec<Value>),
    Map(Vec<(Value, Value)>),  // entries; sorted on encode (§4.4)
    Record(Vec<(u32, Value)>), // (tag, value) present fields only
    Enum(i64),                 // raw case value; unknown preserved as-is (§5.4)
    Union(UnionValue),
}
pub enum UnionValue {
    Known { tag: u32, value: Box<Value> },
    Unknown { tag: u32, raw: Vec<u8> },  // re-emitted verbatim (§6.7)
}

// schema.rs — the descriptor that makes scalars self-delimiting on decode.
pub enum Type {
    Bool, U8, U16, U32, U64, I8, I16, I32, I64, F32, F64,
    Str, Bytes, Timestamp, Hash, Uuid,
    List(Box<Type>),
    Map(Box<Type> /*key*/, Box<Type> /*val*/),
    Record(RecordDesc),
    Enum(EnumDesc),
    Union(UnionDesc),
    Optional(Box<Type>),       // §5.3 — no double-apply (validated at build)
}
pub struct FieldDesc { pub tag: u32, pub ty: Type, pub default: Option<Value> }
pub struct RecordDesc { pub fields: Vec<FieldDesc> } // by ascending tag
pub struct UnionDesc  { pub arms: Vec<(u32, Type)> }
pub struct EnumDesc   { /* known case values, for surfacing unknown(N) */ }
```

A `Value` is always paired with a `&Type` at the public entry points:
`encode_value(&Value, &Type) -> Vec<u8>` and `decode_value(&[u8], &Type) ->
Result<Value, DecodeError>` (the latter a whole-value `decode_all`, §6.8,
reusing the S1 `TrailingBytes` discipline). This dynamic model lets the §6.8
fixed-point proptest run **without** a full codegen pipeline; RFC 0002 §7
Zig/BEAM codegen later targets these same encode/decode routines.

### 4.2 Records and frames (§6.2) — encode

Frame bodies and record bodies use the **same encoding** (RFC 0002 §4.1:
a frame body *is* a record body; the header is RFC 0003's, out of scope). Encode
`Record(fields)` against a `RecordDesc`:

1. For each `FieldDesc` in **ascending tag order** (the descriptor is pre-sorted;
   §6.2 rule 1): look up the field value.
2. Decide omit vs emit per §4.3.
3. If emit: write `put_uvarint(tag)` then the value's encoding (§4.3 covers the
   length-prefix for record/union/list/map/string/bytes/hash; bare scalars write
   their fixed/varint form directly).

There is **no body-level terminator**; the body ends when bytes run out. A
*nested* record field is self-delimited by its own `varint(byte-len)` (§4.5).

### 4.3 Default omission (§6.3, §6.3.1) — three asymmetries to nail

Omission is **field-level only** — never omit a list element or a map value (an
all-default record used as an element/value is emitted in full with a `len=0`
body). Per field:

- **Optional `T?`, absent** → OMIT (no tag).
- **Optional `T?`, present** (even present-but-default, e.g. `list<T>?` with
  count 0, or an all-default `R?`) → EMIT `tag + value`. Presence is information
  (§6.3; §5.3 three-state table). For `list<T>?`/`map<K,V>?` present-empty this is
  the §6.3.1 `02 00` vector.
- **Non-optional, value == default** → OMIT. The default is the declared `= …`
  literal, else the implicit default from the §6.3 table (`bool`→false,
  ints→0, floats→+0.0, string/bytes→empty, list/map→empty, enum→case 0,
  record→all-fields-at-their-own-default).
- **Non-optional `union`/`hash`/`uuid`/`timestamp`** → **NO implicit default,
  ALWAYS emit** (§6.3; this is why the §10 `result: ToolResult` union is always
  on the wire). To express "absent" for these, the schema must make the field
  `T?`.

**All-default nested record (§6.3, §6.3.1) — the clean mechanism.** Encode the
inner record body to a **scratch buffer** (§4.5). If the scratch is **empty**,
the record is all-default → OMIT the field. Otherwise emit `tag +
varint(scratch.len()) + scratch`. "Omit iff inner body is empty" *naturally
subsumes* the recursive all-default rule: an inner all-default record's body is
itself empty, so the test composes without special-casing. Validates against
§6.3.1: `Outer{inner:Inner{0,0}, z:1}` → `02 01` (inner omitted); `Outer{
inner:Inner{1,0}, z:1}` → `01 02 01 02 01` (inner emitted, its `y=0` omitted).

**Decode symmetry.** A decoder treats "tag absent" and (for non-optional fields)
"the default value" identically: missing fields are filled from the descriptor's
default (declared or implicit, recursively for records). Decoders MUST NOT accept
an explicitly-emitted default for a non-optional field if that would admit two
encodings — but since canonical encoders never emit it, the conformance guard is
the fixed-point property (§6.8): re-encoding any decoded value must omit it.

### 4.4 Lists and maps (§6.6) — and the map-ordering contradiction (RESOLVED)

- **List:** `put_uvarint(count)` then each element's encoding **in list order**
  (order significant, preserved). Decode reads `count` elements of the element
  `Type`.
- **Map:** `put_uvarint(count)` then `key value` pairs **sorted by canonical key
  order**; duplicate keys are a `DecodeError` on decode and a precondition
  violation on encode.

> **Map-key ordering — the #1 trap; RFC 0002 contradicts itself.** §6.6 prose
> says "sorted by the canonical byte ordering of the **encoded** key
> (lexicographic over the key's `hcpbin` bytes)." But the §6.6.1 worked vector
> sorts `"banana"` (UTF-8 length 6 → length-prefix `0x06`) **before** `"zebra"`
> (length 5 → `0x05`). A sort over *length-prefixed encoded* bytes would put
> `zebra` (`05 7a…`) before `banana` (`06 62…`) and **fail the RFC's own golden
> vector**. The governing rule is therefore **§5.3** ("`K` MUST be a scalar with
> a total canonical order"): sort by the key's **canonical value order**, not its
> encoded bytes —
> - `string` / `bytes`: lexicographic over the **raw content** bytes (no length
>   prefix in the comparison). This makes `apple < banana < zebra` and matches
>   §6.6.1 exactly.
> - sized integers (`u8..u64`, `i8..i64`): **numeric** order.
>
> **Working decision (flagged as open):** §5.3/§6.6.1 govern over §6.6's loose
> "encoded bytes" wording. Integer-key order has **no worked example in the RFC**,
> so numeric order is a *stated working decision*. Discriminating test: keys
> `{255u32, 256u32}` → numeric ⇒ `255` first; varint-encoded-byte order would put
> `256` first (`0x80 0x02` < `0xff 0x01`). This contradiction is surfaced as
> **Open question OQ-1 (§7.1)** and mirrors how WP3-S7 surfaced the header-tag
> incoherence ([`tools/rfc-incoherence-hunter`](../../../tools/rfc-incoherence-hunter/)).

### 4.5 Length-prefix helper: encode-to-measure (the one real Writer extension)

Nested records (§6.2/§4.3) and union arms (§6.7/§4.6) both need
`varint(byte-len)` of an inner encoding. Add one helper to `Writer`:

```rust
/// Encode `f` into a scratch buffer, then emit varint(len) + scratch.
/// Used for nested records (§6.2), union arms (§6.7).
pub fn put_length_prefixed<F: FnOnce(&mut Writer)>(&mut self, f: F) {
    let mut scratch = Writer::new();
    f(&mut scratch);
    let body = scratch.into_bytes();
    self.put_uvarint(body.len() as u64);
    self.put_raw(&body);
}
```

For the all-default nested-record test (§4.3) the caller inspects the scratch
length *before* committing the tag, so the nested-record path uses the scratch
form directly (encode body → if empty, drop the field; else `put_uvarint(tag)`,
`put_uvarint(len)`, `put_raw`). Scratch-then-measure is preferred over backpatch
for clarity; backpatch is a valid optimization left to implementation.

### 4.6 Unions (§6.7) and enums (§5.4) — unknown preservation

**Union encode.** `put_uvarint(arm_tag)` then `put_length_prefixed(arm value)`
(§4.5). For `UnionValue::Unknown{tag, raw}` write `put_uvarint(tag)`,
`put_uvarint(raw.len())`, `put_raw(&raw)` — re-emitting verbatim. Validates
§6.7.1: `Payload.text("hi")` → `01 03 02 68 69`.

**Union decode.** Read `arm_tag`, read `byte_len`, slice `byte_len` bytes. If
`arm_tag` is in `UnionDesc.arms`: decode the slice as that arm's `Type`; the
slice MUST be fully consumed (a known-arm `byte_len` mismatch is a `DecodeError`
— RFC 0002 §6.7, surfaced upstream by RFC 0003 §9.2 as `malformed_frame`, out of
scope here). If `arm_tag` is unknown: store `Unknown{tag, raw: slice.to_vec()}`
and continue (§6.7 forward-compat). Validates §6.7.1: unknown arm `03 05 01 02 03
04 05` round-trips byte-for-byte.

**Enum encode/decode.** An enum value is a plain `put_uvarint(case)` /
`get_uvarint` of its integer value (§5.4); an enum is identical on the wire to a
sized unsigned varint. Decode does **not** reject unknown case values: it stores
the raw integer (`Value::Enum(n)`) and the `EnumDesc` lets a higher layer surface
it as `"unknown(N)"`. Re-encoding writes the same varint → verbatim round-trip
(§6.7.1: `unknown(5)` → `05`). Case `0` is the default and participates in
omission (§4.3, §5.4).

### 4.7 Unknown record tags — explicitly OUT of scope (open question)

A decoder meeting an **unknown record tag** cannot skip it: §6.2 scalars are not
self-delimiting (§4.1), so without the field's declared type the value length is
unknowable. This layer is **schema-driven and rejects unknown/out-of-order/
duplicate record tags** as `DecodeError` (§6.2 rule 1). This is a real tension
with RFC 0002 Appendix A's illustrative `skipUnknownField(tag)` Zig sketch (lines
1341-1342), which implies generic record-tag skipping. The contradiction is
surfaced as **OQ-2 (§7.1)**; resolving it (e.g. a wire-type nibble on every field
à la protobuf, which RFC 0002 §6.2 deliberately does *not* have) is an RFC-level
decision, not this layer's job. Forward-compat for records is instead achieved by
the §8 "tags are forever / add optional fields" discipline — old peers using an
old descriptor simply never see the new tags from a new peer that sends them.

## 5. Test plan — M1-local vs `dev-cx53`/Linux

Toolchain verified on this host (2026-06-14): `cargo 1.95.0`, `rustc 1.95.0`,
`zig 0.16.0`, `arch = arm64`. The existing S1 suite passes (`cargo test -p
hcpbin` → 50 passed). `dev-cx53` is OFF-LIMITS for the current 6h autoresearch
window; nothing below depends on it.

### 5.1 Runs fully on M1 (aarch64-darwin) — the whole layer

This layer is **pure body-codec logic** — no perf gate, no wire, no transport,
no syscalls — so verification is essentially **100% M1-local**.

| Check | Command | Why M1 is sufficient |
|-------|---------|----------------------|
| Aggregate golden vectors (§4.2-§4.6) | `cargo test -p hcpbin --test golden_aggregate` | Byte-exact assertions transcribed from RFC §6.3.1/§6.6.1/§6.7.1/§10; arch-independent |
| Round-trip fixed point (§6.8) | `cargo test -p hcpbin --test fixed_point` | proptest over scalars→records→unions→list/map→enums; deterministic given a seed |
| Rejection table (§4.2, §4.4) | `cargo test -p hcpbin --test rejection_aggregate` | Out-of-order/dup tag, dup map key, known-arm len mismatch — typed `DecodeError` |
| Map-ordering disambiguation (§4.4) | included in `golden_aggregate` + `fixed_point` | The §6.6.1 string vector + the `{255,256}` integer vector pin OQ-1's working decision |
| Existing S1 suite (no regression) | `cargo test -p hcpbin` | Aggregates build on landed primitives |

### 5.2 Inherited / out-of-scope items that touch Linux

| Check | Status | Why |
|-------|--------|-----|
| `zig build -Dtarget=x86_64-linux` (compile-only) | Out of scope here; inherited gate | RFC 0002 §7 Zig codegen targets this layer **later**; compile-only check belongs to the codegen sprint, not the value codec. Compiles on M1; namespace syscalls run only on Linux. |
| `≤10µs/frame` perf gate (kickoff line 54) | Out of scope | Perf is WP3-S6's baseline + WP3-S7's gate; an absolute µs threshold is arch-specific (aarch64 ≠ x86_64) and meaningless here. No perf claims in this spec. |
| Long fuzz campaign / soak | Out of scope | WP3-S7 hardening; this spec delivers correctness + the proptest fixed point that S7's fuzzers seed from. |

### 5.3 CI wiring

M1-local checks (§5.1) run in the dev shell pre-PR and must all pass. The `.hex`
golden files (§3 stretch goal) are shared with `tests/spec/run_all.py` so the
future Zig path validates the same corpus. No `dev-cx53` lane is required for
this layer to land.

## 6. Acceptance criteria

Done when **all** hold (all M1-local):

1. **Aggregate golden vectors** match the RFC byte-for-byte: at minimum the
   §6.3.1 nested-all-default-omit (`02 01`) and emit (`01 02 01 02 01`) cases, the
   §6.3.1 present-empty optional (`02 00`), the §6.6.1 list (`01 02 01 61 02 62
   63`) and map (`apple<banana<zebra`) vectors, the §6.7.1 union known-arm
   (`01 03 02 68 69`) / unknown-arm (`03 05 01 02 03 04 05`) / enum
   (`00`/`01`/unknown `05`) vectors, and the §10 whole-frame `ToolCallRequest`
   (`01 07 66 73 2e 72 65 61 64 02 03 6b 65 79`).
2. **Round-trip fixed point** (RFC 0002 §6.8) passes via proptest with a fixed
   case budget for every supported type, **including** unknown union arms and
   unknown enum cases (round-trip verbatim) and scrambled-insertion-order maps
   (insertion-order-independent, canonically sorted).
3. **Negative table** complete — at least one byte vector each for: out-of-order
   record tag (§6.2), duplicate record tag (§6.2), duplicate map key (§6.6),
   known union-arm `byte_len` mismatch (§6.7) — each asserting a typed
   `DecodeError`.
4. **Default-omission asymmetries** (§4.3) each have an explicit assertion:
   non-optional all-default record omitted; present optional all-default record /
   present-empty optional aggregate emitted; non-optional
   union/hash/uuid/timestamp always emitted.
5. **Map-ordering decision** (§4.4 / OQ-1) is enforced by the §6.6.1 string vector
   **and** the `{255,256}` integer vector, with the §6.6-vs-§6.6.1 contradiction
   documented in-code and in §7.1.
6. **No regression** in the S1 suite (`cargo test -p hcpbin` green).
7. Every new test file **cites the RFC § it enforces** and is written blind to
   the implementation, matching the convention of
   ``protocol/hcp/hcpbin/tests/golden.rs`` (`../../../protocol/hcp/hcpbin/tests/golden.rs`).

## 7. Dependencies on other sprints

| Depends on | What this layer needs from it |
|------------|-------------------------------|
| **WP3-S1** (landed) | `Writer`/`Reader`/`Hash`/`DecodeError` + varint/signed/bool/bytes/hash primitives ([`protocol/hcp/hcpbin/src/lib.rs`](../../../protocol/hcp/hcpbin/src/lib.rs)); the blind `golden.rs` convention to extend |
| **Scalar completion** (HARD PREREQUISITE — see below) | `string`(NFC), `f32`/`f64`, `timestamp`, `uuid` scalar codecs. Aggregates cannot be tested without them (the §6.6.1 map golden uses `string`). |
| **WP3-S2** (RFC 0003 frame/wire layer) | **Downstream consumer**, not a dependency. The frame layer prepends the RFC 0003 header (`@0..@4`) and carries an `hcpbin` body produced by this layer. This layer must land **before** or with S2's body-handling. |
| **WP3-S7** (hardening) | **Downstream**: S7's proptest/fuzz fixed-point harness seeds from this layer's golden vectors ([`docs/superpowers/specs/2026-06-14-wp3-s7.md`](2026-06-14-wp3-s7.md) §4.1). |
| **RFC 0002 §7 codegen** | **Downstream**: Zig/BEAM generated types call this runtime value codec; not built here. |

**Scalar-completion gap (blocking).** The landed `hcpbin` implements varint,
signed varint, bool, bytes, hash — but **not** `string` (NFC, pinned to Unicode
15.1.0, §6.4 — needs a normalisation table, flagged as WP3-S2 in
[`src/lib.rs`](../../../protocol/hcp/hcpbin/src/lib.rs) line 19), `f32`/`f64`
(NaN + signed-zero canonicalisation, §6.4), `timestamp`, or `uuid`. Two
sub-tasks are cheap and SHOULD be absorbed into this layer's `scalar.rs`: `uuid`
= 16 raw bytes (no endianness, §5.1), `timestamp` = `i64` ns varint (§5.1).
`string` (NFC/Unicode-15.1.0) and `f32`/`f64` (NaN/±0 canonicalisation) are the
**hard prerequisites** — `string` is required even to reproduce the §6.6.1 map
golden vector. This spec assumes those two land first (or are co-delivered);
designing as if `string` were present would be wrong.

### 7.1 Open questions to track

- **OQ-1 — map-key ordering (§4.4).** RFC 0002 §6.6 ("encoded-byte order")
  contradicts §6.6.1's own worked vector (which is content order); §5.3 governs.
  Working decision: content order for `string`/`bytes`, numeric order for
  integers. Integer order has no RFC worked example — confirm numeric is intended
  (vs varint-byte order) before freezing. A latent RFC-level incoherence; feed to
  [`tools/rfc-incoherence-hunter`](../../../tools/rfc-incoherence-hunter/).
- **OQ-2 — unknown record-tag skipping (§4.7).** RFC 0002 Appendix A's
  `skipUnknownField(tag)` sketch implies generic record-tag skipping, but §6.2
  scalars are not self-delimiting, so a schema-less decoder cannot skip an unknown
  scalar field. This layer rejects unknown record tags; whether the RFC wants a
  protobuf-style wire-type nibble to enable skipping is an RFC decision.
- **OQ-3 — `Value` vs codegen boundary.** This layer ships a dynamic `Value`/
  `Type` codec. RFC 0002 §7 codegen will emit static Zig/BEAM types; confirm the
  generated encoders are expected to *call* this runtime codec vs. inline their
  own (the spec assumes the former, so the fixed-point property is shared).
- **Header tag model (informational).** RFC 0002 §4.2 (`@0` reserved, body tags
  `@1+`) vs RFC 0003 §4.4.1 (header tags `@0..@4`). Irrelevant to this layer
  (body-only), but noted because the body's lowest author tag is `@1` and the
  whole-frame golden vectors assume it.
