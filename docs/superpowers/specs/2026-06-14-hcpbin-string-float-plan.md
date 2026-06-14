# hcpbin `string` + `f32`/`f64` — deferred-scalar implementation plan

## Status

Spec (2026-06-14). Planning artifact for the two scalar encoders explicitly
**deferred** out of WP3-S1 in the `hcpbin` codec
([`protocol/hcp/hcpbin/src/lib.rs`](../../../protocol/hcp/hcpbin/src/lib.rs)
lines 18-23, 488-492): `string` (with NFC normalisation) and `f32`/`f64`
(NaN / signed-zero canonicalisation). WP3-S1 landed varints, `bool`, `bytes`,
and `hash` and left these two TODOs. This document is the implementation-ready
plan for closing them. The work is small, pure, and **fully verifiable on the
M1 dev box** (`cargo test`) — it needs nothing from `dev-cx53` (see §6).

This is a planning artifact: the actual edit is future work, sequenced behind the
WP3 freeze and the citation reconciliation below. It is written to the
adversarial-independence golden convention already established in
[`protocol/hcp/hcpbin/tests/golden.rs`](../../../protocol/hcp/hcpbin/tests/golden.rs)
(every expectation derived from the RFC, blind to the implementation).

## 0. Citation correction (read first)

The WP3 kickoff
([`docs/superpowers/plans/2026-06-14-wp3-kickoff.md`](../plans/2026-06-14-wp3-kickoff.md)
line 43) and issue #167 cite **"RFC 0002 §4 / Appendix A"** for the byte
encoding and golden vectors. That wording is **stale and wrong** (same correction
as the S3 spec §0 and the S7 spec header):

- The byte encoding of values is **RFC 0002 §6** ("`hcpbin` encoding rules"),
  not §4. The two scalars in scope are specified in **RFC 0002 §6.4**
  ("Scalar canonicalisation") — NaN/signed-zero for floats, NFC-against-a-pinned-
  Unicode-version for strings — with the scalar table in **§5.1** and the
  length-prefix primitive rule in **§6.1**.
- **There is no Appendix A in RFC 0002.** Golden vectors are the worked examples
  in RFC 0002 **§6.1.1** (primitives — includes the only in-text float and string
  vectors), §6.3.1, §6.6.1, §6.7.1, and §10. The only `Appendix A` in the RFC set
  is **RFC 0003 Appendix A** (the `hcp.wire` control schema), unrelated to scalars.
- **Internal-citation correction (this task's deps).**
  [`lib.rs`](../../../protocol/hcp/hcpbin/src/lib.rs) line 19 attributes `string`
  to **"WP3-S2"**. That is mislabelled: the kickoff's WP3-S2 deliverable is the
  **frame layer (RFC 0003)** in the `litany` crate
  ([`docs/superpowers/plans/2026-06-14-wp3-kickoff.md`](../plans/2026-06-14-wp3-kickoff.md)
  line 25), **not** an `hcpbin` scalar. Both `string` and `f32`/`f64` are
  `hcpbin`-S1 *deferred scalars* (this plan owns them); they belong to the
  `hcpbin` crate (`protocol/hcp/hcpbin/`), not `litany`. The `lib.rs:19`
  `TODO(WP3-S2)` should be re-tagged to this plan on landing.

All citations below use the corrected section numbers.

## 1. Objective

Add canonical `hcpbin` encode/decode for the two remaining scalar types, matching
the existing `Reader`/`Writer` + free-function API surface exactly, so that the
codec's canonicality property (RFC 0002 §6.8 — exactly one byte string per value,
two implementations agree byte-for-byte) holds for `string` and `f32`/`f64`:

1. **`f32` / `f64`** (RFC 0002 §5.1, §6.4): 4-/8-byte **little-endian** IEEE-754,
   with two canonicalisations applied **before** emission:
   - **NaN** → the single canonical quiet-NaN bit pattern
     (`f32`: `0x7FC00000`; `f64`: `0x7FF8000000000000`).
   - **Signed zero** → `-0.0` encodes as `+0.0`.
2. **`string`** (RFC 0002 §5.1, §6.1, §6.4): length-prefixed UTF-8
   (`varint(byte_len)` + bytes, exactly like `bytes` but with the payload
   **NFC-normalised against a pinned Unicode version** first). The pin is
   **Unicode 15.1.0** (§6.4, frozen for this spec revision). `bytes` is *never*
   normalised — that distinction is the whole point of having both types.

Non-objective: this plan does **not** touch records/frames/unions/maps/enums
(§6.2/§6.3/§6.6/§6.7) or the frame header (`kind`/`corr`/`stream`/`seq`/`end`),
which is the **WIRE layer (RFC 0003)**, explicitly *not* `hcpbin`
(RFC 0002 §4.2, §6 scope note; mirrored in
[`lib.rs`](../../../protocol/hcp/hcpbin/src/lib.rs) lines 22-23, 497-498).

## 2. Inputs / oracles

### 2.1 Normative inputs (RFCs / repo)

- **RFC 0002 §5.1** — scalar table: `f32`/`f64` are "4/8 bytes, little-endian;
  NaN canonicalised (§6.4)"; `string` is "length-prefixed UTF-8 bytes
  (NFC-normalised, §6.4)".
- **RFC 0002 §6.1** — length-prefix primitive: `string` is prefixed by its
  **byte** length as an unsigned minimal varint; "Fixed floats. `f32`/`f64` are
  little-endian IEEE-754 (§6.4 canonicalises NaN/signed-zero)."
- **RFC 0002 §6.4** — the load-bearing section (full text the plan implements):
  - NaN: "Any NaN encodes to the single canonical quiet-NaN bit pattern
    (`f32`: `0x7FC00000`; `f64`: `0x7FF8000000000000`), little-endian on the wire."
  - Signed zero: "`-0.0` encodes as `+0.0`."
  - String: "`string` values are Unicode-normalised to **NFC** before encoding;
    decoders MAY assume NFC. (`bytes` is never normalised.) … conforming
    implementations MUST normalise to NFC using the normalisation data of
    **Unicode 15.1.0** … The pinned version is part of the canonical-encoding
    definition, not an implementation detail; changing it is a breaking change to
    `hcpbin` and MUST be handled as a protocol-version bump … Code points
    unassigned in the pinned version are normalised as that version's data
    specifies (left unchanged where it assigns no mapping)."
- **RFC 0002 §6.3** — implicit defaults relevant to these scalars (this layer does
  not implement default-omission, but the values are fixed here): `f32`/`f64`
  default is **canonical `+0.0`**; `string` default is **empty (length 0)**.
- **RFC 0002 §6.8** — canonicality requirement: lists "NaN and signed-zero
  canonicalisation, and NFC normalisation **against the pinned Unicode version**
  (§6.4) so string bytes are reproducible across implementations" as a jointly-
  sufficient rule; the conformance fixed point is
  `encode(decode(encode(v))) == encode(v)` and cross-impl byte agreement.
- **RFC 0002 §2.3 / §2.3.1** — string *literal* lexis (escapes) — informative
  here; this plan encodes runtime UTF-8 string **values**, not source literals.
- **Existing API contract.**
  [`protocol/hcp/hcpbin/src/lib.rs`](../../../protocol/hcp/hcpbin/src/lib.rs):
  `Writer` (`put_uvarint`, `put_bytes`, `put_bool`, `put_hash`, `into_bytes`),
  `Reader` (`get_uvarint`, `get_bytes`, `get_raw`, `is_empty`), `DecodeError`
  enum, and the `decode_all`/`encode_*`/`decode_*` free-function pattern. The new
  code MUST extend — not reshape — this surface.

### 2.2 In-text golden vectors (the positive oracle)

RFC 0002 §6.1.1 is the only place that works floats and strings to bytes:

```
f32(0.0)   -> 00 00 00 00
f32(1.0)   -> 00 00 80 3f
f32(NaN)   -> 00 00 c0 7f          # canonical quiet NaN, not any other variant
f32(-0.0)  -> 00 00 00 00          # canonicalised to +0.0 (NOT 00 00 00 80)

""               -> 00             # varint(len=0)
"hi"             -> 02 68 69
"café" (NFC é)   -> 05 63 61 66 c3 a9
  # if input is decomposed "café", NFC converts it to the precomposed bytes above
```

`f64` vectors are **not** worked in-text; they are **derived** from the §6.4 bit
patterns and IEEE-754 little-endian, and committed as golden vectors:

```
f64(0.0)   -> 00 00 00 00 00 00 00 00
f64(1.0)   -> 00 00 00 00 00 00 f0 3f
f64(NaN)   -> 00 00 00 00 00 00 f8 7f   # 0x7FF8000000000000 LE
f64(-0.0)  -> 00 00 00 00 00 00 00 00   # canonicalised to +0.0
```

### 2.3 NFC conformance oracle (vendored, executable, M1)

The Unicode Character Database **`NormalizationTest.txt` for Unicode 15.1.0** is
the external oracle for the string normaliser. It is vendored into the repo
(§3.4) and drives a conformance test (§5.3): each line gives source / NFC / NFD /
NFKC / NFKD columns; the test asserts `nfc(c1) == c3` for the NFC column across
every row. This makes the pin **self-verifying**: if the chosen crate ever ships
data other than 15.1.0, the conformance test fails the build. Provenance:
`https://www.unicode.org/Public/15.1.0/ucd/NormalizationTest.txt`
(SHA-256 recorded in the vendored file's header comment).

## 3. Design

### 3.1 The Unicode-version pin (the load-bearing decision)

§6.4 pins NFC to **Unicode 15.1.0 data**. The critical subtlety: **the dependency
crate's semver tells you nothing about which Unicode version it bundles** — the
pin is on the *Unicode data*, not the crate. A crate can bump its own version many
times while moving the bundled Unicode data underneath. So the crate is selected
*by its verified bundled Unicode version*, exact-pinned, and then guarded by the
vendored UCD corpus (§2.3) so drift is a build failure.

**Verified facts** (read off the `UNICODE_VERSION` constant in each tagged
release of `unicode-rs/unicode-normalization`, 2026-06-14):

| Crate version | Bundled `UNICODE_VERSION` |
|---|---|
| `0.1.22` | `(15, 0, 0)` |
| **`0.1.23`** | **`(15, 1, 0)`** ← the pin |
| `0.1.24` | `(16, 0, 0)` |
| `0.1.25` / master | `(17, 0, 0)` |

**Decision: depend on `unicode-normalization = "=0.1.23"`** (exact-version pin),
chosen *because* 0.1.23 bundles Unicode 15.1.0 — verified, not inferred from
semver. Rationale vs. the alternative:

- `unicode-normalization 0.1.23` has **version == data** (the crate *is* one
  frozen Unicode table), is dependency-light, and `str::nfc()` →
  `chars()`-iterator maps cleanly onto a streaming encoder. It is the cleaner fit
  for a foundation crate that has been deliberately kept dependency-free.
- **ICU4X (`icu_normalizer`)** is present *transitively* elsewhere in the repo
  (`vaked-agents/ci/{provost,label-tagger}` lockfiles pin `icu_normalizer 2.2.0`),
  but (a) those are unrelated CI tools — `hcpbin` has **zero** deps and is in no
  workspace, so it would gain the dependency fresh regardless; "already vendored"
  buys nothing; and (b) **ICU4X 2.x bundles Unicode 16.0**, which *violates* the
  15.1.0 pin. Using ICU4X to hit 15.1.0 would require an `icu4x-datagen`-frozen
  15.1.0 `DataProvider` vendored in-repo — strictly more machinery than the
  `=0.1.23` pin for no benefit here. Rejected.

**Pin enforcement (three layers):**
1. **Exact version** in `Cargo.toml`: `unicode-normalization = "=0.1.23"`, and the
   resolved entry committed in `Cargo.lock`.
2. **Compile-time assertion** that the crate's declared Unicode version is 15.1.0:
   `const _: () = assert!(unicode_normalization::UNICODE_VERSION == (15, 1, 0));`
   (the crate exports `UNICODE_VERSION`). A future `cargo update` that moves the
   data version breaks the build immediately.
3. **Runtime/test corpus**: the vendored 15.1.0 `NormalizationTest.txt` conformance
   test (§2.3 / §5.3). Belt-and-braces against the data ever diverging from the
   declared constant.

Doc note in code: "Bumping `unicode-normalization` past `=0.1.23` (i.e. changing
the bundled Unicode data version) is a **breaking change to `hcpbin`** and MUST be
handled as a protocol-version bump (RFC 0002 §6.4): it alters the bytes — and thus
the digests — of already-chained `eventd` frames (§9)."

**Design implication (stated, per CLAUDE.md):** this introduces `hcpbin`'s
**first-ever dependency**. The crate has been intentionally dependency-free (empty
`[dependencies]`). NFC against a pinned Unicode version is irreducibly a data
table; hand-vendoring the table is strictly worse than a pinned, audited,
data-versioned crate. The dependency is justified and the cost (one exact-pinned,
no-default-features, no-transitive-deps crate) is minimal.

### 3.2 Float encode/decode

Encoding (NaN canonicalisation must emit the canonical bits **literally**, never
`to_bits()` of an arbitrary NaN — signaling/payload NaNs are not guaranteed
quiet):

```rust
// f32 (mirror for f64 with 0x7FF8000000000000 / to_le_bytes()/from_le_bytes())
pub fn put_f32(&mut self, value: f32) {
    let bits: u32 = if value.is_nan() {
        0x7FC0_0000                 // canonical quiet NaN (§6.4)
    } else if value == 0.0 {        // matches BOTH +0.0 and -0.0 (-0.0 == 0.0)
        0x0000_0000                 // canonical +0.0 (§6.4)
    } else {
        value.to_bits()
    };
    self.put_raw(&bits.to_le_bytes());   // 4 bytes LE (§6.1, §6.4)
}
```

The `value == 0.0` branch catches `-0.0` because `-0.0 == 0.0` is `true` in IEEE
arithmetic; emitting `+0.0`'s all-zero bits canonicalises signed zero. The
`is_nan()` branch is checked first so a NaN never reaches `to_bits()`.

**Decode — strictness decision (RFC leaves this open; stated with rationale).**
§6.4 mandates *encoder* canonicalisation but, unlike `bool` (where §6.4 says
non-`0x00`/`0x01` bytes are rejected), says only that decoders "MAY assume NFC" and
is **silent on whether a decoder must reject a non-canonical NaN or a `-0.0` on the
wire.** The existing codec is strict everywhere it can be (`NonMinimal`,
`InvalidBool`, `WidthOverflow`, `TrailingBytes`). Two defensible options:

- **(A) Strict-reject** non-canonical float bits (any NaN bit pattern other than
  the canonical quiet pattern; any `-0.0`). Makes "valid wire bytes == canonical
  bytes," giving a *decode-side* fixed point and matching the codec's strict ethos
  and the §6.8 "two implementations agree byte-for-byte" goal.
- **(B) Canonicalise-on-decode** (read bits, re-canonicalise, accept). Matches the
  literal "decoders MAY assume" latitude; more lenient; lets a sloppy peer's frame
  through but normalises it.

**Recommended: (A) strict-reject**, for consistency with the rest of the codec and
because a non-canonical float on the wire is, like a non-minimal varint, a producer
that is not canonical — surfacing it as a `DecodeError` is the same contract.
This is a genuine spec gap; it is **logged as Open question OQ1 (§7)** for sign-off
by the WP3 owner before landing, because it changes the accept-set and is observable
across implementations.

```rust
// Under decision (A):
pub fn get_f32(&mut self) -> Result<f32, DecodeError> {
    let raw = self.get_raw(4)?;
    let bits = u32::from_le_bytes(raw.try_into().expect("get_raw(4) is 4 bytes"));
    let v = f32::from_bits(bits);
    if v.is_nan() && bits != 0x7FC0_0000 {
        return Err(DecodeError::NonCanonicalFloat);
    }
    if bits == 0x8000_0000 {                 // -0.0 on the wire
        return Err(DecodeError::NonCanonicalFloat);
    }
    Ok(v)
}
```

### 3.3 String encode/decode

```rust
use unicode_normalization::{UnicodeNormalization, is_nfc_quick, IsNormalized};

pub fn put_string(&mut self, value: &str) {
    // NFC against the pinned Unicode 15.1.0 data (§6.4). `bytes` is NOT normalised.
    let nfc: String = value.nfc().collect();      // idempotent; if already NFC, identity
    self.put_bytes(nfc.as_bytes());                // varint(byte_len) + UTF-8 bytes (§6.1)
}

pub fn get_string(&mut self) -> Result<&'a str /* or String, see below */, DecodeError> {
    let raw = self.get_bytes()?;                   // varint(len) + len bytes
    let s = core::str::from_utf8(raw).map_err(|_| DecodeError::InvalidUtf8)?;
    // NFC validation: see decision below.
    Ok(s)
}
```

Notes:
- The encoder is a thin NFC pass over the existing `put_bytes`. The decoder is
  `get_bytes` + UTF-8 validation. UTF-8 validity is **always** enforced on decode
  (`DecodeError::InvalidUtf8`) — that is not optional; a `string` field that is not
  valid UTF-8 is malformed regardless of the NFC question.
- **NFC-on-decode strictness (OQ2, §7).** §6.4: "decoders MAY assume NFC." So a
  spec-conformant decoder *may skip* re-checking NFC. Options:
  - **(A) trust** (skip the NFC check; cheapest; spec-permitted) — but a
    non-NFC-producing peer would smuggle non-canonical bytes past the decoder,
    weakening the §6.8 cross-impl guarantee at the seam where it is cheapest to
    catch.
  - **(B) validate** via `is_nfc_quick`/`is_nfc` and reject non-NFC with a
    `DecodeError::NonCanonicalString`, consistent with decision (A) for floats and
    the codec's strict ethos.
  - **Recommended: (B) validate**, using `is_nfc()` (the exact, not the quick,
    check) so it shares the 15.1.0 pinned data. Logged as **OQ2**; same sign-off
    gate as OQ1 (it changes the accept-set).
- **Borrow vs. owned return.** `get_bytes` returns `&'a [u8]`; under **trust (A)**
  `get_string` can return `&'a str` (zero-copy). Under **validate (B)** it still
  returns `&'a str` (validation is read-only). The free-function `decode_string`
  returns an owned `String` (mirrors `decode_bytes -> Vec<u8>`).

### 3.4 Files to create / modify

```
protocol/hcp/hcpbin/
  Cargo.toml                         # MODIFY: add [dependencies]
                                     #   unicode-normalization = { version = "=0.1.23",
                                     #     default-features = false }
  Cargo.lock                         # MODIFY: commit the resolved 0.1.23 entry
  src/
    lib.rs                           # MODIFY:
                                     #   - Writer::put_f32/put_f64/put_string
                                     #   - Reader::get_f32/get_f64/get_string
                                     #   - free fns encode_f32/decode_f32 (+f64, +string)
                                     #   - DecodeError::{InvalidUtf8, NonCanonicalFloat,
                                     #       NonCanonicalString}  (NonCanonical* gated on OQ1/OQ2)
                                     #   - const _: () = assert!(UNICODE_VERSION == (15,1,0));
                                     #   - retarget the lib.rs:19 TODO(WP3-S2) -> this plan
                                     #   - delete the two satisfied TODOs (lib.rs:488-492)
  tests/
    golden.rs                        # MODIFY (extend existing adversarial-independence suite):
                                     #   float + string positive/negative golden vectors
    nfc_conformance.rs               # CREATE: drives the vendored UCD corpus (§5.3)
  tests/data/
    NormalizationTest-15.1.0.txt     # CREATE (vendored UCD; provenance + SHA-256 in header)
```

No new crate, no workspace change; `hcpbin` stays a single leaf crate (now with one
pinned dependency). `golden.rs` is **extended in place** to preserve its
adversarial-independence convention (every new vector cites the RFC §, written blind
to `lib.rs`).

## 4. Worked encodings (golden, from §2.2)

```
# floats
put_f32(0.0)             -> 00 00 00 00
put_f32(1.0)             -> 00 00 80 3f
put_f32(f32::NAN)        -> 00 00 c0 7f
put_f32(-0.0)            -> 00 00 00 00          # canonicalised
put_f64(1.0)             -> 00 00 00 00 00 00 f0 3f
put_f64(f64::NAN)        -> 00 00 00 00 00 00 f8 7f

# adversarial NaN: a signaling/payload NaN must still emit the canonical quiet bits
put_f32(f32::from_bits(0x7F80_0001))   -> 00 00 c0 7f   # NOT 01 00 80 7f

# strings
put_string("")           -> 00
put_string("hi")         -> 02 68 69
put_string("café")       -> 05 63 61 66 c3 a9            # NFC precomposed é
put_string("cafe\u{301}")-> 05 63 61 66 c3 a9            # decomposed input -> same NFC bytes
```

The last string row is the key NFC golden: two distinct Rust `&str` inputs (one
precomposed, one decomposed) MUST encode to identical bytes — the property §6.4 /
§6.8 exist to guarantee, and the reason a bare "normalise to NFC" without a pinned
version is insufficient.

## 5. Test plan

### 5.1 Where it runs

**All of it runs on M1 via `cargo test -p hcpbin`.** The codec is pure (no
namespace syscalls, no transport, no async). The kickoff's "No local builds on M1"
applies to the *transport / perf* targets (RFC 0003 wire I/O, the ≤10µs/frame
bench on the 8-core box), **not** to the pure value codec — the same scoping the
S3 spec §5 already established for the equally-pure router. `dev-cx53` is needed
for **nothing** in this plan's acceptance criteria (§8).

| Test | Command | Where |
|---|---|---|
| Float + string positive golden vectors (§2.2, §4) | `cargo test -p hcpbin --test golden` | M1 |
| Float + string negative / strictness vectors (§5.2) | `cargo test -p hcpbin --test golden` | M1 |
| Round-trip fixed point `encode(decode(encode(v)))==encode(v)` | `cargo test -p hcpbin` | M1 |
| NFC conformance vs vendored UCD 15.1.0 (§5.3) | `cargo test -p hcpbin --test nfc_conformance` | M1 |
| Unicode-version pin compile assertion (§3.1) | `cargo build -p hcpbin` (fails to compile if data != 15.1.0) | M1 |

### 5.2 Negative / strictness vectors (the decision-rule oracle)

Mirrors `golden.rs`'s existing rejection tables. Each asserts an error per cited §:

- `decode_string` of invalid UTF-8 (e.g. `[0x01, 0xff]`) -> `InvalidUtf8`.
- `decode_string` / `decode_f*` with **trailing bytes** -> `TrailingBytes`
  (consume-all, via the existing `decode_all` wrapper).
- `decode_f32` of a truncated 3-byte input -> `UnexpectedEof`.
- **(if OQ1 = strict-reject)** `decode_f32` of `[01,00,80,7f]` (non-canonical NaN)
  and `[00,00,00,80]` (`-0.0`) -> `NonCanonicalFloat`; `f64` analogues.
- **(if OQ2 = validate)** `decode_string` of valid-UTF-8-but-non-NFC bytes
  (the decomposed `cafe\u{301}` byte sequence `63 61 66 65 cc 81`) ->
  `NonCanonicalString`.
- Encoder canonicalisation asserts: `put_f32` of every NaN variant and of `-0.0`
  produces the §2.2 canonical bytes; `put_string` of decomposed input produces the
  precomposed bytes.

These negative vectors are gated on the OQ1/OQ2 decisions (§7); if the owner picks
the lenient branch, the corresponding rows become *acceptance* (round-trip)
vectors instead of rejection vectors. The positive vectors (§4) are unconditional.

### 5.3 NFC conformance harness

`tests/nfc_conformance.rs` parses `tests/data/NormalizationTest-15.1.0.txt`
(semicolon-delimited UCD format; skip `#`/`@` lines), and for each row with columns
`(c1 source, c2 NFC, c3 NFD, c4 NFKC, c5 NFKD)` asserts
`hcpbin string-encode(c1)` decodes-or-normalises to the same bytes as
`hcpbin string-encode(c2)` — i.e. `nfc(source) == NFC column` — for the NFC
relation. This is what makes the 15.1.0 pin **self-verifying**: a future data-version
drift produces a row mismatch and a red test, enforcing the "changing the pin is a
breaking protocol bump" rule (§3.1, §6.4) mechanically. The corpus is committed;
no network access at test time.

### 5.4 Needs `dev-cx53` / Linux

**Nothing in §8.** For completeness, the items that *are* Linux/dev-cx53-gated
remain other sprints' concerns and are unaffected by this plan: the ≤10µs/frame
perf baseline (WP3-S6, 8-core box), the Zig port of the codec for the daemon fleet
(WP4; `zig build -Dtarget=x86_64-linux` is compile-only on M1), and live `eventd`
integration (WP3-S5). The string/float scalars feed those later, but their own
verification is 100% M1-local.

## 6. M1-vs-dev-cx53 split (summary)

| Concern | M1 (`cargo test`) | dev-cx53 / Linux |
|---|---|---|
| Float encode/decode + canonicalisation | ✅ all | — |
| String encode/decode + NFC pin | ✅ all | — |
| NFC conformance vs UCD 15.1.0 | ✅ vendored corpus | — |
| Pin compile-assertion | ✅ | — |
| Perf (≤10µs/frame) | — | WP3-S6 (not this plan) |
| Zig port of these scalars | compile-only (`zig build -Dtarget=x86_64-linux`) | WP4 runtime |

The split is clean because the deliverable is pure value codec + a committed data
table — both fully exercisable on the M1 host. This matches the S3 spec's already-
ratified reasoning that the pure layers of the HCP stack are M1-testable.

## 7. Risks / open questions

- **OQ1 — float decode strictness (§3.2).** §6.4 mandates encoder
  canonicalisation but is silent on decoder rejection of non-canonical NaN /
  `-0.0` (contrast `bool`, which §6.4 explicitly makes strict). Recommended:
  **strict-reject** (`DecodeError::NonCanonicalFloat`), for consistency with the
  codec's strict ethos and the §6.8 cross-impl-agreement goal. Decision changes
  the accept-set, so **must be signed off by the WP3 owner before landing**; the
  RFC could also be amended to state the rule explicitly (recommended — close the
  gap in the spec, not just the code).
- **OQ2 — NFC-on-decode strictness (§3.3).** §6.4 says "decoders MAY assume NFC."
  Recommended: **validate** (`is_nfc()` against the pinned data;
  `DecodeError::NonCanonicalString`) for the same reasons as OQ1. Same sign-off
  gate. UTF-8 validity (`InvalidUtf8`) is enforced unconditionally regardless of
  OQ2.
- **First dependency on `hcpbin` (§3.1).** Introduces the crate's only dependency
  (`unicode-normalization =0.1.23`, `default-features = false`). Justified (NFC is
  irreducibly a Unicode data table; a pinned audited crate beats hand-vendoring the
  table). Pin guarded three ways (exact version + compile assert + UCD corpus).
- **Pin drift / supply chain.** A `cargo update` that bumps past `=0.1.23` would
  silently change the bundled Unicode data and corrupt determinism. Mitigated by
  the exact `=` pin, the committed `Cargo.lock`, and the compile-time
  `UNICODE_VERSION == (15,1,0)` assertion — any drift is a build failure.
- **`unicode-normalization` `no_std` / features.** Confirm the crate compiles with
  `default-features = false` for the daemon-embeddable build path; the NFC API
  (`UnicodeNormalization::nfc`, `is_nfc`, `UNICODE_VERSION`) is in the default
  surface. Verify at landing.
- **Zig parity (WP4).** The eventual Zig port of the codec MUST normalise NFC
  against the **same** Unicode 15.1.0 data, or Zig↔Rust round-trip (RFC 0002 §7.2)
  diverges on strings. The Zig port must vendor an equivalent 15.1.0 table and run
  the same UCD conformance corpus. Out of scope here; flagged for WP4-S4.

## 8. Acceptance criteria

Done when ALL hold (all verifiable on M1, none requiring dev-cx53):

1. `cargo build -p hcpbin` is clean **and** the `UNICODE_VERSION == (15,1,0)`
   compile assertion is present and passing (proves the data pin, not just the
   crate version).
2. `Writer::{put_f32,put_f64,put_string}` and `Reader::{get_f32,get_f64,get_string}`
   exist, plus the matching `encode_*`/`decode_*` free functions, extending the
   existing API surface (no reshaping of `Reader`/`Writer`/`DecodeError`/`decode_all`).
3. Positive golden vectors (§2.2/§4) pass in `golden.rs`, including the
   precomposed-vs-decomposed `café`/`cafe\u{301}` → identical-bytes NFC vector and
   the signaling-NaN → canonical-quiet-bits vector.
4. Round-trip fixed point `encode(decode(encode(v))) == encode(v)` holds for floats
   (incl. NaN, ±0.0, ±inf, subnormals) and strings (incl. multi-byte UTF-8 and a
   decomposed input that normalises).
5. Negative/strictness vectors (§5.2) pass, matching whatever OQ1/OQ2 decision is
   ratified (strict-reject vectors *or* lenient round-trip vectors — not both).
   `InvalidUtf8` rejection of non-UTF-8 string bytes is unconditional.
6. NFC conformance test (§5.3) passes against the vendored Unicode 15.1.0
   `NormalizationTest.txt` (the NFC column), with the corpus committed and its
   provenance + SHA-256 recorded.
7. The satisfied `TODO`s in `lib.rs` (lines 488-492) are removed and the mislabelled
   `TODO(WP3-S2)` on line 19 is retargeted to this plan; the `string`/`float` items
   no longer appear in the crate's "out of scope" header list.
8. OQ1 and OQ2 are explicitly resolved (sign-off recorded) before merge — the spec
   gaps are closed by decision, not left implicit in the code.
9. No dependency on `dev-cx53` for 1-8; the perf baseline remains a WP3-S6 gate and
   is not a criterion here.

## 9. Dependencies on other sprints

| Relationship | Item | Status |
|---|---|---|
| **Builds on** | WP3-S1 `hcpbin` primitives (`Reader`/`Writer`, `decode_all`, `DecodeError`, `golden.rs` convention) | Landed ([`lib.rs`](../../../protocol/hcp/hcpbin/src/lib.rs), [`golden.rs`](../../../protocol/hcp/hcpbin/tests/golden.rs)) |
| **New external dep** | `unicode-normalization =0.1.23` (Unicode 15.1.0 data) | Available on crates.io; verified `UNICODE_VERSION (15,1,0)` |
| **Consumed by** | WP3-S2 frame layer / records-frames-unions encoders (need `string`/`f*` as field types) | Future; these scalars are a precondition for any schema with `string`/`f32`/`f64` fields |
| **Consumed by** | `eventd` hash chain / `litanyreplay` (RFC 0002 §9) — rely on canonical string/float bytes | Determinism guaranteed only once these scalars + the pin land |
| **Parity obligation** | WP4 Zig port must use the same 15.1.0 NFC data + UCD corpus (§7) | Future (WP4-S4) |

The two scalars are a **precondition** for the compound encoders (§6.2/§6.6/§6.7):
no schema carrying a `string`, `f32`, or `f64` field can be encoded canonically
until this lands. It is the smallest remaining gap between the current primitive
codec and a codec that can serialise the worked example in RFC 0002 §10.
