# RFC 0002 — `.hcplang` (HCP schema language)

- **Status:** Draft
- **Created:** 2026-06-09
- **Track:** Protocol

## Abstract

`.hcplang` is the schema / interface-definition language of HCP (the Harness
Control Protocol). It describes the **Votive Frame** types carried over the
**Litany Wire** and the rules by which those frames are serialised into
**`hcpbin`**, HCP's canonical binary encoding. A `.hcplang` schema is the single
source of truth from which both the Zig enforcement daemons and the Erlang/OTP
control plane derive their frame types, so that every peer agrees on field
layout, encoding, and meaning.

This RFC fills in the schema-language portion of the umbrella RFC
[`0001-hcp.md`](./0001-hcp.md) §4. It defines the lexical structure, the type
system, the declaration forms, the `hcpbin` encoding rules, the codegen mapping
to Zig structs and BEAM terms, and the determinism/evidence ties that make HCP
exchanges replayable and tamper-evident. The wire framing and transport
(`0001-hcp.md` §2) and the encoding container (`0001-hcp.md` §3) are referenced
but not redefined here; this RFC owns the *schema* and the *serialisation of
declared types*.

Like the Vaked language itself, `.hcplang` is **small, typed, deterministic,
and source-mapped** (see
[`docs/language/0001-language-manifesto.md`](../../docs/language/0001-language-manifesto.md)
and [`docs/context/PROJECT_CONTEXT.md`](../../docs/context/PROJECT_CONTEXT.md)):
there is exactly one canonical encoding of any value, exactly one canonical
source form, and every generated type carries provenance back to its
declaration.

## Terminology

This table is aligned with [`0001-hcp.md`](./0001-hcp.md) and
[`docs/protocol/README.md`](../../docs/protocol/README.md). New terms introduced
by this RFC are marked **(new)** and are mirrored into the protocol README.

| Term | Definition |
|------|------------|
| HCP | This protocol. |
| Litany Wire | The on-the-wire byte protocol (framing + transport rules). |
| Votive Frame | A single HCP message in the frame model. |
| `.hcplang` | Schema / IDL describing frame and message types (this RFC). |
| `hcpbin` | Canonical binary encoding of frames. |
| Frame class **(new)** | One of the five Votive Frame roles: `request`, `response`, `event`, `control`, `error`. |
| Frame header **(new)** | The implicit, reserved fields every Votive Frame carries (`kind`, `corr`, `stream`, `seq`, `end`); supplied by the wire layer, never declared in `.hcplang`. |
| Tag **(new)** | The stable per-field integer (`@N`) that identifies a field on the wire, independent of source order or name. |
| Schema digest **(new)** | The `hash` of a schema's canonical normalised form; pins which `.hcplang` a frame was encoded against. |

Daemons referenced by this RFC use the established roster from
[`docs/protocol/README.md`](../../docs/protocol/README.md) — protocol daemons
`chapterd` / `preceptord` / `reliquaryd` / `candled` / `petitiond` / `oraclefd`
— and the runtime daemons from
[`docs/runtime/README.md`](../../docs/runtime/README.md): `agent-supervisord`
(Erlang/OTP control plane), `mcp-brokerd` (brokered MCP calls), and `eventd`
(hash-chained, tamper-evident event log). Tooling: `litanyctl`, `litanydump`,
`litanyfmt`, `litanyreplay`.

## 1. Design goals & non-goals

`.hcplang` exists to make HCP exchanges **deterministic and explainable**. It
inherits the Vaked principles directly:

1. **One canonical encoding.** Any value of a declared type has exactly one
   `hcpbin` byte string. Two independent implementations encoding the same value
   MUST produce identical bytes (§6). This is what lets `eventd` hash-chain
   frames and `litanyreplay` reproduce a session.
2. **One canonical source form.** `litanyfmt` is idempotent; the formatted bytes
   of a schema are normative for source-mapping (§3, §9).
3. **Typed and explicit.** No `any`, no untyped maps, no implicit optionals.
   Absence is spelled `?`; a field that may be unset says so.
4. **Stable wire identity.** Fields are identified on the wire by an explicit
   integer **tag** (`@N`), never by source order or name, so schemas can evolve
   without breaking the wire (§8).
5. **Source over cleverness.** The grammar (§3,
   [`grammar.ebnf`](../hcplang/grammar.ebnf)) is deliberately small and rhymes
   with `vaked/grammar/vaked-v0-plus.ebnf`.

**Non-goals.** `.hcplang` is not a general programming language: no expressions,
no computation, no conditionals. It does not define transport or framing (that
is the Litany Wire, [`0001-hcp.md`](./0001-hcp.md) §2) nor the encoding
*container* / length-framing (`0001-hcp.md` §3); it defines the **types** and
the **serialisation of values of those types**. It does not define authority
policy — that is `preceptord`'s domain (§8 of [`0001-hcp.md`](./0001-hcp.md),
and §8 here) — though it provides the typed vocabulary policy is expressed over.

## 2. Lexical structure

A `.hcplang` source file is UTF-8. Identifiers and keywords are ASCII; string
and `bytes` literals may carry arbitrary UTF-8 / escaped content.

### 2.1 Comments and documentation

- **Line comments** begin with `#` and run to end of line. They are insignificant
  and are discarded by the parser.
- **Doc annotations** begin with `///` and run to end of line. They are *not*
  comments: they attach to the immediately following item — a declaration
  (including a nested declaration), a record field, an enum case, a union arm, or
  a service method — and are **preserved through codegen** so generated Zig and
  BEAM types can carry the same documentation (source-mapping, §9). The grammar
  gives each of these a leading `{ annotation }` slot
  ([`grammar.ebnf`](../hcplang/grammar.ebnf)).

### 2.2 Identifiers and keywords

```
ident = letter { letter | digit | "_" } ;
```

Identifiers are ASCII, begin with a letter, and may contain letters, digits, and
underscores. Unlike Vaked identifiers, `.hcplang` identifiers do **not** permit
`-`, so they map cleanly onto Zig and Erlang identifiers without rewriting.

The reserved keywords are:

```
use  schema  enum  record  union  frame  service
request  response  event  control  error
call  subscribe  yields
list  map
bool  u8 u16 u32 u64  i8 i16 i32 i64  f32 f64
string  bytes  timestamp  hash  uuid
true  false
```

Keywords may not be used as identifiers.

### 2.3 Literals

| Literal | Form | Notes |
|---------|------|-------|
| Integer | `-?[0-9]+` or `0x[0-9a-fA-F]+` | Used for tags, enum values, defaults. |
| Float | `-?[0-9]+\.[0-9]+` | IEEE-754; see §5.1 for canonical form. |
| Boolean | `true` / `false` | |
| String | `"…"` | JSON-style escapes (`\"`, `\\`, `\n`, `\t`, `\uXXXX`); UTF-8. |
| Enum reference | `Type.case` | A qualified reference to an enum case (used as a default). |

### 2.4 Tags and attributes

- A **tag** is written `@N`, where `N` is a non-negative integer literal. Tags
  appear on record fields and union arms (§4, §5) and are the field's stable
  wire identity.
- An **attribute** is written `@name` or `@name(arg, …)` and decorates the
  following declaration or field. Attributes are open-ended metadata; this RFC
  defines a small reserved set (§4.4). Unknown attributes are preserved by
  `litanyfmt` and ignored by encoders.

> Note: `@N` (a bare integer) is a *tag*; `@ident(...)` is an *attribute*. The
> grammar disambiguates on whether the token after `@` is an integer or an
> identifier.

## 3. Source form & `litanyfmt`

The grammar is given in [`grammar.ebnf`](../hcplang/grammar.ebnf) and MUST be
accepted exactly by any conforming parser. `litanyfmt` is the canonical
formatter; its output is idempotent and is the **normative source form** for the
purposes of source-mapping and schema digesting (§9). Two schemas that format to
the same bytes are the same schema.

Canonical source rules enforced by `litanyfmt`:

- Declarations are emitted in source order (formatting does not reorder
  declarations — order is author intent and may be meaningful for readers), but
  **encoding never depends on declaration or field source order** (§6.2).
- Fields within a record are formatted one per line, tag included, aligned.
- Exactly one blank line between top-level declarations; no trailing whitespace;
  files end with a single newline.
- Doc annotations (`///`) immediately precede the item they document.

## 4. The Votive Frame model

A **Votive Frame** is a single HCP message. Every frame belongs to exactly one of
five **frame classes**, declared with the `frame` keyword and a class keyword:

> Note: [`0001-hcp.md`](./0001-hcp.md) describes the frame model in prose with
> four classes (request / response / event / control), folding failure into the
> response path. This RFC **promotes `error` to a fifth first-class frame class**
> so a typed failure is a frame in its own right (terminating either a `request`
> or a stream). This is a forward-reference; `0001-hcp.md` should be reconciled to
> five classes when next revised.

| Class | Keyword | Role |
|-------|---------|------|
| Request | `request` | A peer asks another peer to do something (e.g. a brokered tool call). Carries a fresh correlation id. |
| Response | `response` | The terminal reply to a `request`, on the same correlation id. |
| Event | `event` | An unsolicited or subscription-driven message on a stream (the event stream operator surfaces subscribe to). |
| Control | `control` | Connection / session lifecycle and flow: open/close a chapter (`chapterd`), backpressure, heartbeats (`candled`), subscription setup/teardown. |
| Error | `error` | A typed failure terminating a request or stream. |

### 4.1 Frame declaration

```
frame ToolCallRequest request {
  tool:   string  @1
  args:   bytes   @2
}
```

The keyword after the frame name fixes its class. The body is a **record body**
(§5.2): a set of tagged fields carrying the frame's payload.

### 4.2 The frame header (reserved, implicit)

Every Votive Frame carries a small **frame header**. These fields are supplied
and validated by the Litany Wire layer ([`0001-hcp.md`](./0001-hcp.md) §1–2) and
are **never declared in `.hcplang`**. They occupy a reserved tag space and may
not be redeclared by a frame body:

| Header field | Type | Meaning |
|--------------|------|---------|
| `kind` | `enum FrameKind` | The frame class (request/response/event/control/error). |
| `corr` | `uuid` | Correlation id. A `response`/`error` echoes its `request`'s `corr`; an `event` carries its subscription's `corr`. |
| `stream` | `u64?` | Stream id for multi-frame exchanges; absent for single-shot request/response. |
| `seq` | `u64?` | Monotonic sequence number within a `stream` (chunking / ordering). |
| `end` | `bool` | Set on the final frame of a `stream` (terminal chunk). |

Because the header is reserved and implicit, **author-declared field tags begin
at `@1`**; tag `@0` is reserved for the header/extension space and MUST NOT be
used by a frame, record, or union declaration (§6.2).

Correlation, streaming, and chunking are therefore expressed *structurally* by
the header, not by hand-rolled fields — keeping payloads minimal and the
correlation/stream model uniform across all schemas.

### 4.3 Services

A `service` groups related exchanges and binds frames together:

```
service ToolBroker {
  /// Invoke a brokered tool and await its result.
  call    invoke    (ToolCallRequest) -> ToolCallResponse
  /// Subscribe to the live event stream for a session.
  subscribe watch   (WatchControl) yields ToolEvent
}
```

- `call (Req) -> Resp` binds a `request` frame to its terminal `response` frame.
  The `request` must be of class `request`; the result must be of class
  `response` (an `error` frame may always terminate a call — it is implicit and
  need not be listed).
- `subscribe (Ctrl) yields Ev` binds a `control` frame (the subscription
  request) to a stream of `event` frames. The stream is terminated by an `event`
  with `end = true`, or by an `error`.

Services are the unit `mcp-brokerd` and `petitiond` advertise and that
`preceptord` scopes authority over (§8).

### 4.4 Reserved attributes

| Attribute | Applies to | Meaning |
|-----------|------------|---------|
| `@deprecated` | field, case, arm, method | Retained on the wire for compatibility; codegen emits a deprecation marker. |
| `@since(v="x.y")` | decl, field | Documents the schema version a field was introduced in (§8). |
| `@relic` | field of type `hash` | The field references a durable artifact in `reliquaryd` by content hash. |
| `@redact` | field | The field's value is redacted in `litanydump` output and in `eventd` projections (carries sensitive data). |

**Attribute position (normative).** On a field or union arm, attributes may
appear in **two positions**: as a *leading* prefix before the field/arm name,
and/or as a *trailing* run after the tag (`@N`). Both are equivalent in meaning;
e.g. `relic: hash @3 @relic` carries the trailing `@relic` and is exactly
equivalent to `@relic relic: hash @3`. The grammar's `field` and `union_arm`
productions therefore carry a `{ attribute }` slot in both positions
([`grammar.ebnf`](../hcplang/grammar.ebnf)). The tag `@N` itself is **not** an
attribute (§2.4) and always sits in its fixed position (`ident : type @N`);
`litanyfmt` emits each attribute in a canonical position but accepts either.
On a declaration, attributes lead the `kind` keyword (`@since(v="0.2") record R
{…}`).

Unknown attributes are preserved (round-tripped by `litanyfmt`) and ignored by
encoders, so schemas can carry tool-specific metadata without affecting the wire.

## 5. Type system

`.hcplang` has scalar types, four compound type constructors, and named
references to declared types. It is consistent with the Vaked type vocabulary in
[`vaked/schema/parallel-types.md`](../../vaked/schema/parallel-types.md)
(`list<…>`, `map<…>`, record-style bodies, optionals).

### 5.1 Scalar types

| Type | Domain | Canonical encoding (see §6) |
|------|--------|------------------------------|
| `bool` | true / false | single byte `0x00` / `0x01` |
| `u8 u16 u32 u64` | unsigned ints | LEB128 varint |
| `i8 i16 i32 i64` | signed ints | zig-zag + LEB128 varint |
| `f32` | IEEE-754 binary32 | 4 bytes, little-endian; NaN canonicalised (§6.4) |
| `f64` | IEEE-754 binary64 | 8 bytes, little-endian; NaN canonicalised (§6.4) |
| `string` | UTF-8 text | length-prefixed UTF-8 bytes (NFC-normalised, §6.4) |
| `bytes` | opaque octets | length-prefixed raw bytes |
| `timestamp` | instant | `i64` nanoseconds since Unix epoch (UTC), varint-encoded |
| `hash` | content hash | tagged, length-prefixed digest: `varint(algo-id) varint(len) bytes` (§6.5) |
| `uuid` | 128-bit id | 16 opaque bytes, stored and emitted in field order (no endianness applied — a UUID's internal layout is mixed-endian, so `hcpbin` treats it as 16 raw bytes) |

`hash` is first-class because HCP is evidence-oriented: artifact references
(`reliquaryd`), schema digests, and the `eventd` chain are all `hash` values.

### 5.2 Records (structs)

A `record` is an ordered-by-tag set of named, typed fields:

```
record ToolError {
  code:    u32       @1
  message: string    @2
  detail:  bytes?    @3
}
```

Each field has a name, a type, and a stable tag `@N` (`N >= 1`). Tags MUST be
unique within the record and SHOULD be assigned densely from `@1`. A field may
carry a default literal (`= …`); a field with a default is treated as present
with that value when omitted on the wire (§6.3). Field source order is
insignificant to the encoding (§6.2).

### 5.3 Compound type constructors

| Constructor | Syntax | Notes |
|-------------|--------|-------|
| Optional | `T?` | Presence is explicit. Absent = field omitted on the wire (§6.3). `T?` may not be doubly applied (`T??` is illegal). |
| List | `list<T>` | Ordered, homogeneous. Encoded as count + elements in list order (order is significant and preserved). |
| Map | `map<K, V>` | `K` MUST be a scalar with a total canonical order (`string`, `bytes`, or a sized integer — see `key_type` in the grammar). Encoded as entries sorted by canonical key order (§6.6), so encoding is independent of insertion order. |
| Enum | `enum Name { … }` | A closed set of named integer-valued cases (§5.4). |
| Union | `union Name { … }` | A tagged sum: exactly one arm is present (§5.5). |

Compound types nest (`list<map<string, ToolEvent>>`, `list<Frame?>` etc.) subject
to the optional-no-double-apply rule.

**Optional vs non-optional aggregates (`list`/`map`).** A non-optional
`list<T>` / `map<K,V>` has **two** observable states only — empty and
non-empty — and its implicit default is the empty aggregate; per §6.3 an empty
non-optional aggregate is **omitted** on the wire, so for a decoder *absent
tag = empty aggregate*. Making the aggregate optional (`list<T>?` / `map<K,V>?`)
adds a third, distinct state by lifting *presence* into the value, giving:

| Wire form | `list<T>` (non-optional) | `list<T>?` (optional) |
|-----------|--------------------------|------------------------|
| tag absent | empty list | **null / unset** (the optional is absent) |
| tag present, count `0` | *(illegal — must be omitted)* | **present-but-empty** list |
| tag present, count `> 0` | non-empty list | non-empty list |

So choose `list<T>?` / `map<K,V>?` only when "the producer never set this" must
be distinguishable from "the producer set it to empty"; otherwise prefer the
non-optional form, where absent canonically *is* empty. The same three-state
rule applies to `map<K,V>?`.

### 5.4 Enums

```
enum Severity {
  info  = 0,
  warn  = 1,
  err   = 2,
}
```

Enum cases have explicit integer values (stable wire identity, like tags). The
zero value is the **default case** and is what a `Severity`-typed field decodes
to when omitted (§6.3); authors SHOULD make case `0` a sensible default. Decoders
encountering an unknown enum value MUST preserve it (forward compatibility, §8)
and surface it as "unknown(N)".

### 5.5 Unions

```
union Payload {
  text:   string         @1
  binary: bytes          @2
  nested: ToolEvent      @3
}
```

A union is a tagged sum: on the wire it is exactly one arm — its tag, the arm
value's byte length, and the arm value's encoded bytes (`varint(arm-tag)
varint(byte-len) value`, §6.7). The length prefix is present on **every** arm,
known or unknown, so the arm value is always self-delimiting. Arms carry stable
tags `@N` like record fields. A decoder encountering an unknown arm tag uses the
length to skip the value, and MUST preserve those raw bytes and surface the value
as "unknown arm @N" so it can be re-emitted byte-for-byte (forward
compatibility). Unions are how `Payload`, result variants, and error detail
bodies are modelled without `any`.

### 5.6 The `schema` module

A file's declarations live inside one top-level `schema` block, which fixes the
namespace and the schema version:

```
schema hcp.core {
  version = "0.1.0"
  # enum / record / union / frame / service declarations follow
}
```

A schema name is a **`qualified_ident`** — one or more dot-separated identifiers
(`hcp.core`) — not a plain `ident`; the grammar's `decl_name` is a
`qualified_ident` for this reason. The `version` setting is **mandatory** and
participates in evolution rules (§8). References across schemas use the same
dotted `qualified_ident` form (`hcp.core.Frame`, which is the grammar's `ref`)
and require a `use "path/to/other.hcplang"` import.

## 6. `hcpbin` encoding rules

`hcpbin` is the canonical, deterministic binary encoding of values of
`.hcplang` types. This section specifies it precisely enough that two
independent implementations produce **byte-for-byte identical** output for the
same value — the property `eventd`'s hash chain and `litanyreplay` depend on.

> Scope: this section defines the encoding of *values of declared types*. The
> outer frame container (magic, length-framing, version negotiation) is the
> Litany Wire's concern ([`0001-hcp.md`](./0001-hcp.md) §2–3); `hcpbin` is the
> *body* it carries.

### 6.1 Primitives

- **Varints.** Unsigned integers use unsigned LEB128 (7 bits/byte,
  little-endian, high bit = continuation), with the **minimal** number of bytes
  (no trailing `0x00` continuation groups). Signed integers are zig-zag mapped
  (`(n << 1) ^ (n >> (k-1))`) then varint-encoded, where **`k` is the declared
  integer width in bits** — `k = 8` for `i8`, `16` for `i16`, `32` for `i32`,
  `64` for `i64` — so the arithmetic-shift sign fill matches the field's type.
- **Strict (canonical) varint decode.** Because exactly one byte string is
  canonical, decoders MUST **reject non-minimal / overlong varints**: a varint
  whose final byte is a `0x00` continuation-cleared group that could have been
  elided, or whose length exceeds the maximum needed for the declared width
  (e.g. more than 10 bytes for a 64-bit value, or a value whose decoded
  magnitude does not fit the declared width), is a protocol error (surfaced as
  an `error` frame). Trusting an overlong encoding would admit two byte strings
  for one value and break §6.8.
- **Fixed floats.** `f32`/`f64` are little-endian IEEE-754 (§6.4 canonicalises
  NaN/signed-zero).
- **Length prefixes.** `string`, `bytes`, lists, maps, and nested
  records/unions are prefixed by an unsigned varint byte-length or element-count
  as specified per type below. `string` is prefixed by its **byte** length.

### 6.2 Records and frames: field ordering & tags

A record/frame value is encoded as a sequence of **present fields, emitted in
strictly ascending tag order**, regardless of source order. Each present field is:

```
field := varint(tag)  value-bytes
```

where `value-bytes` is the type's encoding (§6.1, §6.5, §6.6, §6.7). There is no
per-field length prefix for fixed-width scalars (the type fixes the
width/varint), but `string`, `bytes`, `hash`, lists, maps, nested records, and
unions are self-delimiting via their own length/count prefix: `string`/`bytes`
by a `varint` byte-length, lists/maps by a `varint` element count, `hash` by its
`varint(len)` (§6.5), a nested `record` by a `varint` byte-length framing its
tagged-field set (§6.1), and a union by its `varint(byte-len)` (§6.7). This
self-delimitation is what lets a decoder skip a field of an unknown nested shape
and preserve it for round-trip. Rules:

1. **Ascending tag order is mandatory and canonical.** Encoders MUST sort by tag;
   decoders MUST reject out-of-order or duplicate tags (a malformed frame is a
   protocol error, surfaced as an `error` frame).
2. **Omit absent fields.** Optional fields that are absent, and fields equal to
   their declared default, MAY be omitted; to keep encoding canonical, a field
   equal to its default **MUST** be omitted, and an absent optional **MUST** be
   omitted (§6.3). This guarantees one encoding per value.
3. **Tag `@0` is reserved** for the frame header / extension space and is never
   emitted by a declared field.
4. The frame header (§4.2) is encoded by the wire layer ahead of the body's
   tagged fields; within the body, author tags (`>= 1`) apply.

### 6.3 Defaults, optionals, and canonical omission

To guarantee exactly one encoding per value:

- An **absent** `T?` field is omitted (no tag emitted).
- A present `T?` field is emitted as its tag + value (a present-but-default `T?`
  is still emitted, because presence itself is information).
- A non-optional field whose value equals its declared default **MUST be
  omitted**; decoders substitute the default. A non-optional field with no
  declared default has an implicit type default; that implicit default is
  **likewise omitted**.

**Which types have an implicit default.** The implicit (no-`=`) default is
defined for:

| Type | Implicit default |
|------|------------------|
| `bool` | `false` |
| `u8…u64`, `i8…i64` | `0` |
| `f32` / `f64` | `+0.0` (the canonical `+0.0`, §6.4) |
| `string` / `bytes` | empty (length `0`) |
| `list<T>` / `map<K,V>` | empty (count `0`) |
| `enum E` | case `0` (§5.4) |
| `record R` | the record whose **every** field is at *its own* default (see below) |

**Types with NO implicit default — always emitted.** `union`, `hash`, `uuid`,
and `timestamp` have **no implicit default**: there is no canonical "zero"
value to omit against (a union has no defaultable arm; a `hash` has no
defaultable algorithm/digest; a `uuid` has no canonical zero distinct from a
real all-zero id; a `timestamp`'s `0` is a meaningful instant, the Unix epoch,
not "unset"). A **non-optional** field of one of these types is therefore
**always emitted** (its tag + value MUST appear on the wire). To express "no
value" for one of these, the field MUST be declared optional (`T?`) and then
omitted when absent. This is what makes the example's non-optional
`result: ToolResult` union field always present on the wire.

**Nested `record` default (canonical omission of record-typed fields).**
A `record`'s default is **"every field at its default"** — i.e. the value
obtained by omitting all of that record's fields (each non-optional field
falls back to its own implicit/declared default, each optional field is
absent). A non-optional `record`-typed field whose value equals this all-default
record **MUST be omitted**, exactly mirroring the scalar rule; a decoder
substitutes the all-default record. This closes the "all-default nested record →
two valid encodings" hole: the all-default record has the single canonical
encoding *absent*, never an emitted empty body. (If any nested field is
non-default, the record field is present and encoded normally.) The rule is
recursive: a record-typed field of a record-typed field obeys the same test.

Decoders MUST treat "tag absent" and "tag present with default value" for a
non-optional field as the same value; encoders MUST choose the omitted form.

### 6.4 Scalar canonicalisation

- **Bool.** `bool` encodes as a single byte: `false = 0x00`, `true = 0x01`. On
  decode, **any other byte value is rejected** as a protocol error (surfaced as
  an `error` frame); a decoder MUST NOT coerce non-zero bytes to `true`. This
  keeps `bool` one-byte-per-value canonical.
- **NaN.** Any NaN encodes to the single canonical quiet-NaN bit pattern
  (`f32`: `0x7FC00000`; `f64`: `0x7FF8000000000000`), little-endian on the wire.
- **Signed zero.** `-0.0` encodes as `+0.0`.
- **String — NFC against a pinned Unicode version.** `string` values are
  Unicode-normalised to **NFC** before encoding; decoders MAY assume NFC.
  (`bytes` is never normalised.) Because NFC output is *Unicode-version-
  dependent* (the decomposition/composition data and the set of assigned code
  points change between Unicode releases), a bare "normalise to NFC" rule is
  **not** byte-for-byte deterministic across implementations — and any such
  divergence would corrupt the `eventd` hash chain (§9) and break cross-impl
  agreement (§6.8). Therefore the canonical encoding **pins an explicit Unicode
  version**: conforming implementations MUST normalise to NFC using the
  normalisation data of **Unicode 15.1.0** (the frozen version for this revision
  of the spec). The pinned version is part of the canonical-encoding definition,
  not an implementation detail; changing it is a breaking change to `hcpbin` and
  MUST be handled as a protocol-version bump (it would alter the bytes, and thus
  the digests, of already-chained frames). Code points unassigned in the pinned
  version are normalised as that version's data specifies (left unchanged where
  it assigns no mapping). *(Who pays the normalisation CPU cost — producer vs.
  the encoding layer — remains Open question 7; the version pin here is
  independent of that and is required regardless.)*

### 6.5 `hash` encoding

A `hash` is `varint(algo-id) varint(len) digest-bytes`: the algorithm id, the
digest byte-length, then exactly `len` raw digest bytes. The initial registry:

| `algo-id` | Algorithm | Digest length |
|-----------|-----------|---------------|
| `0x01` | SHA-256 | 32 bytes |
| `0x02` | BLAKE3-256 | 32 bytes |

The explicit `len` prefix makes a `hash` **self-delimiting regardless of
algorithm**: a decoder that does not recognise a future `algo-id` can still skip
exactly `len` bytes and continue parsing the rest of the frame, and preserve the
unknown digest for byte-for-byte round-trip (forward compatibility, §8) — without
the length prefix an unknown `algo-id` would be unskippable and would corrupt the
remainder of the frame. For a **known** `algo-id`, `len` MUST equal the registry
digest length for that algorithm (a mismatch is a protocol error); the prefix is
thus redundant-but-validating for known algorithms and load-bearing for unknown
ones. *(Which algorithm is the **default** for schema digests and the `eventd`
chain remains Open question 4 — the working default is SHA-256 (`0x01`). This
length-prefix fix is about wire skippability and is orthogonal to that choice.)*

### 6.6 Lists and maps

- **List:** `varint(count)` followed by each element's encoding, **in list
  order** (order is significant).
- **Map:** `varint(count)` followed by `key value` pairs, **sorted by the
  canonical byte ordering of the encoded key** (lexicographic over the key's
  `hcpbin` bytes). Duplicate keys are a protocol error. Sorting makes map
  encoding independent of insertion order — required for determinism.

### 6.7 Unions

A union value is `varint(arm-tag) varint(byte-len) value`: the arm tag, the
byte-length of the arm value's encoding, then exactly that many bytes of the
arm value's encoding. Exactly one arm is present. **Every** arm carries the
length prefix — known and unknown alike — so the form is uniform and an arm
value is always self-delimiting:

```
union-value := varint(arm-tag)  varint(byte-len)  value-bytes[byte-len]
```

A decoder that recognises `arm-tag` decodes `value-bytes` as that arm's declared
type; for a **known** arm, `byte-len` MUST equal the actual encoded length of the
value (a mismatch is a protocol error). A decoder that does **not** recognise
`arm-tag` uses `byte-len` to skip the value, preserves those raw bytes, and
surfaces the value as "unknown arm @N", re-emitting `varint(arm-tag)
varint(byte-len) value-bytes` verbatim on round-trip (forward-compatible, §8).
This is what makes unknown arms both skippable and preservable byte-for-byte —
the earlier "no length on known arms, length on unknown arms" split was
self-contradictory (a decoder cannot know an arm is unknown until it has already
needed the length to find the value's end).

### 6.8 Canonicality requirement (normative)

A `.hcplang` encoder is **canonical** iff, for every value `v` of every declared
type, `encode(v)` is uniquely determined by `v` and the schema. The rules above
are jointly sufficient:

- minimal varints (§6.1), with decoders rejecting non-minimal/overlong varints
  (§6.1) so no two byte strings decode to one integer;
- zig-zag sign-fill bound to the declared integer width `k` (§6.1);
- `bool` is exactly `0x00`/`0x01`, other bytes rejected (§6.4);
- present fields in strictly ascending tag order, duplicates/out-of-order
  rejected (§6.2);
- default omission for non-optional fields — including the all-default nested
  `record` rule (§6.3) — and the "no implicit default, always emit" rule for
  `union`/`hash`/`uuid`/`timestamp` (§6.3);
- NaN and signed-zero canonicalisation, and NFC normalisation **against the
  pinned Unicode version** (§6.4) so string bytes are reproducible across
  implementations;
- length-prefixed `hash` (§6.5) and length-prefixed union arms (§6.7), so even
  unknown algorithms/arms round-trip to identical bytes;
- map entries sorted by canonical encoded-key order, list order preserved
  (§6.6).

Conformance test: round-trip and re-encode MUST be a fixed point
(`encode(decode(encode(v))) == encode(v)`), and two conforming implementations
MUST agree byte-for-byte. `litanydump` and `litanyreplay` rely on this.

## 7. Codegen mapping

A `.hcplang` schema lowers to native types in two targets: **Zig structs** for the
enforcement daemons (`mcp-brokerd`, `agent-guardd`, `sandboxd`, `fs-snapshotd`,
`eventd` — [`docs/runtime/README.md`](../../docs/runtime/README.md)) and
**BEAM/Erlang terms** for the control plane (`agent-supervisord`). Generated code
carries source-map provenance back to the `.hcplang` declaration (§9), echoing
the Vaked compilation path (Vaked → typed graph → Zig daemon configs + OTP
control plane — [`docs/context/PROJECT_CONTEXT.md`](../../docs/context/PROJECT_CONTEXT.md)).

### 7.1 Mapping table

| `.hcplang` | Zig (daemons) | BEAM / Erlang (`agent-supervisord`) |
|------------|---------------|--------------------------------------|
| `bool` | `bool` | `boolean()` (`true` / `false`) |
| `u8..u64` | `u8`..`u64` | `non_neg_integer()` |
| `i8..i64` | `i8`..`i64` | `integer()` |
| `f32` / `f64` | `f32` / `f64` | `float()` |
| `string` | `[]const u8` (UTF-8, NFC) | `binary()` (UTF-8) |
| `bytes` | `[]const u8` | `binary()` |
| `timestamp` | `i64` (ns) | `integer()` (ns) |
| `hash` | `struct { algo: u8, digest: []const u8 }` | `{hash, Algo :: byte(), Digest :: binary()}` |
| `uuid` | `[16]u8` | `<<_:128>>` (16-byte binary) |
| `T?` | `?T` | `T | undefined` (key absent in map) |
| `list<T>` | `[]T` (slice) | `[T]` (list, order preserved) |
| `map<K,V>` | `std.AutoHashMap(K, V)` | `#{K => V}` |
| `record R { … }` | `struct R { … }` (fields incl. tag metadata) | map `#{field => Value}` with `__type__ => 'R'` |
| `enum E { … }` | `enum(uN) E { … }` | atom per case (`info` / `warn` / `error`) |
| `union U { … }` | `union(enum) U { … }` (tagged) | `{Arm :: atom(), Value}` 2-tuple |
| `frame F …` | `struct F` + `pub const frame_kind` | map with `__frame__ => 'F'`, `__kind__ => Class` |
| `service S { … }` | a `S` namespace of typed `fn` stubs | a behaviour module `S` with callback specs |

Notes:

- **Tags travel with the type.** Generated Zig structs carry a comptime tag table
  (`pub const _tags = .{ .tool = 1, .args = 2 }`); generated Erlang carries a
  module function `tags/0` returning `#{tool => 1, args => 2}`. The encoder/decoder
  in each language is generated from this table, so neither side hand-writes wire
  offsets.
- **Enums** lower to the smallest unsigned Zig integer that holds the largest
  case value; on BEAM they are atoms, with `unknown(N)` represented as
  `{unknown, N}`.
- **Header fields (§4.2)** are not part of the generated payload struct; they are
  produced/consumed by the generated wire (de)serialiser.
- **`@redact` fields** generate a redaction shim used by `litanydump` and the
  `eventd` projection; the underlying value still encodes normally.

### 7.2 Round-trip guarantee

For any value, encode-in-Zig then decode-in-BEAM (and vice-versa) MUST yield an
equal value, and re-encoding MUST reproduce the same `hcpbin` bytes (§6.8). This
cross-language fixed point is the contract that lets a Zig daemon and the OTP
control plane exchange frames safely.

This includes **forward-compatible content neither side fully understands**:
because every union arm (§6.7) and every `hash` (§6.5) is length-prefixed, a
decoder that meets an unknown arm tag or an unknown `hash` `algo-id` skips the
value by its length, retains the raw bytes, and re-emits them verbatim. An
unknown union arm therefore survives a Zig⇄BEAM round-trip byte-for-byte (the
generated tagged-union type carries an `unknown @N` variant holding the raw
`varint(byte-len) value-bytes`), so a frame produced by a newer peer re-serialises
identically through an older one — the property §8's minor-version evolution
relies on.

## 8. Versioning & evolution

Schema evolution is governed by the mandatory `version` (semver) on the `schema`
block (§5.6) and by tag stability:

- **Tags are forever.** A tag, once assigned to a field/arm, MUST NOT be reused
  for a different field/arm. Removing a field retires its tag (mark
  `@deprecated`, do not reuse).
- **Adding** an optional field / a new enum case / a new union arm with a fresh
  tag is a **minor** (backward-compatible) change. Decoders preserve unknown
  tags/cases/arms (§5.4, §5.5, §6.7) so old peers tolerate new ones.
- **Removing or retyping** a field, or changing a tag's meaning, is a **major**
  (breaking) change and MUST bump the major version.
- A frame on the wire pins its schema via the **schema digest** (the `hash` of the
  schema's `litanyfmt`-canonical normalised form). `oraclefd` resolves a digest
  to a schema; `preceptord` may scope authority by digest (only frames matching an
  approved schema are admitted). Version negotiation at connection setup is the
  Litany Wire's job ([`0001-hcp.md`](./0001-hcp.md) §2).

## 9. Determinism, source-mapping & evidence

This RFC's encoding rules are the foundation of HCP's evidence story; they tie
back to the Vaked principles (preserve provenance, validate before generating,
keep things deterministic — [manifesto](../../docs/language/0001-language-manifesto.md)):

- **Determinism.** §6 guarantees a single canonical `hcpbin` byte string per
  value. Without this, hash-chaining and replay are meaningless.
- **Source-mapping.** Every generated Zig/BEAM type, every tag, and every doc
  annotation carries provenance back to a `(schema-digest, decl, field)` triple.
  `litanydump` can therefore render a captured frame against the exact schema it
  was encoded with, and point each field back to its `.hcplang` source.
- **Tamper-evidence (`eventd`).** Frames admitted to the runtime are appended to
  `eventd`'s append-only, hash-chained log. Because `hcpbin` is canonical, the
  hash over a frame is stable and a chain entry is `H(prev || hcpbin(frame))`.
  Any post-hoc edit breaks the chain.
- **Authority (`preceptord`).** What a peer may request is `preceptord`'s
  decision. `.hcplang` supplies the typed vocabulary that policy is written
  over: services, frame classes, schema digests, and `@relic`/`@redact`
  annotations. `preceptord` may admit/deny by service, frame class, or schema
  digest (§8).
- **Replay (`litanyreplay`).** A captured Litany Wire log replays
  deterministically because every frame body is canonical `hcpbin` decoded
  against a digest-pinned schema.

## 10. Worked example

The schema [`protocol/hcplang/examples/hcp-core.hcplang`](../hcplang/examples/hcp-core.hcplang)
defines the five core Votive Frames and one concrete brokered tool-call exchange.
Walking the key pieces:

```
schema hcp.core {
  version = "0.1.0"

  enum Severity { info = 0, warn = 1, err = 2 }

  /// The body of a tool result: exactly one arm is present (§5.5).
  union ToolResult {
    text:   string  @1
    binary: bytes   @2
    relic:  hash    @3 @relic   # reliquaryd artifact reference (trailing attr, §4.4)
  }

  /// A brokered tool invocation (mcp-brokerd dispatches these).
  frame ToolCallRequest request {
    tool: string  @1
    args: bytes   @2          # opaque, tool-specific request body
  }

  frame ToolCallResponse response {
    result:   ToolResult  @1            # non-optional union: no default, always emitted (§6.3)
    severity: Severity    @2 = info     # scalar default; omitted on the wire (§6.3)
  }

  service ToolBroker {
    call invoke (ToolCallRequest) -> ToolCallResponse
  }
}
```

Encoding a `ToolCallRequest{ tool = "fs.read", args = <0x6b6579> }` as `hcpbin`
(body only; the header in §4.2 is prepended by the wire layer):

```
# fields emitted in ascending tag order (§6.2)
01                      # tag @1  (varint)
07 66 73 2e 72 65 61 64 # string len=7 "fs.read" (varint len + NFC UTF-8 bytes)
02                      # tag @2  (varint)
03 6b 65 79             # bytes  len=3  0x6b 0x65 0x79
```

Any conforming encoder produces exactly these body bytes (§6.8). `eventd` chains
`H(prev || header || body)`; `litanydump` decodes them against the `hcp.core`
schema digest and maps `@1 → ToolCallRequest.tool`, `@2 → ToolCallRequest.args`.

The matching `ToolCallResponse` echoes the request's `corr` (§4.2). Its
`result: ToolResult` is a **non-optional union**, so it has no implicit default
and is **always emitted** (§6.3); a `relic`-arm result whose `hash` resolves in
`reliquaryd` encodes as field tag `@1`, then the union `arm-tag @3`, then the
arm value's byte-length, then the `hash` itself (`varint(byte-len) value`,
§6.5 / §6.7):

```
01                      # field tag @1 (result)
03                      # union arm-tag @3 (relic)            (§6.7: arm-tag first)
22                      # union arm byte-len = 34 (the hash value that follows)
01                      # hash algo-id = 0x01 (SHA-256, §6.5)
20                      # hash digest len = 32
<32 bytes of digest>    # the SHA-256 digest
```

The `severity` field is omitted whenever it equals its `info` default (§6.3), so
a default-severity response carries only `@1`.

## 11. Security considerations

- **Authority** is `preceptord`'s; `.hcplang` only provides the typed vocabulary
  (services, frame classes, schema digests, `@relic`/`@redact`). A schema cannot
  grant capability — admission is always a `preceptord` decision (§8, §9).
- **Tamper-evidence** depends entirely on §6 canonicality: a non-canonical
  encoder would let two byte strings represent one value and break the `eventd`
  hash chain. Conformance to §6.8 is therefore a security property, not just a
  correctness one.
- **`@redact`** marks fields whose values must be elided from `litanydump` output
  and `eventd` projections; the field still participates in encoding and hashing
  (the digest covers the real value), but operator surfaces never see it.
- **Unknown tags/arms/cases** are preserved, not executed: forward compatibility
  must never become a code-execution or confused-deputy path. Decoders treat
  unknown content as opaque bytes for round-trip only.
- **Replay** (`litanyreplay`) reproduces captured frames deterministically; it
  MUST run against the same digest-pinned schema, and MUST NOT be a way to bypass
  `preceptord` (replayed frames are re-admitted under current policy).

## Open questions

These are genuinely-undecided design choices. The RFC makes a working decision
where one is needed to stay internally consistent, but flags it here for review.
Several are inherited from [`0001-hcp.md`](./0001-hcp.md)'s open questions.

1. **Baseline transport.** §6 assumes a byte stream but does not fix one. The
   umbrella RFC lists stdio vs unix socket vs vsock; vsock matters for the
   [MirageOS unikernel surface](../../docs/language/0010-mirageos-unikernel-surface.md)
   (a sealed unikernel exposing a membrane over vsock). *Working assumption:*
   length-framed stream, transport-agnostic; **defer the baseline choice to the
   Litany Wire RFC.** Does `.hcplang` need any transport-aware annotation at all,
   or stay fully transport-agnostic?
2. **MCP-inside-frames vs HCP-peer.** Is `mcp-brokerd` an HCP peer that *speaks*
   MCP outward (MCP terminates at the broker), or is MCP tunnelled inside Votive
   Frames (MCP messages as `bytes`/`union` payloads)? This RFC models a tool call
   with an opaque `args: bytes` body, which supports *either* reading, but a
   first-class `union McpMessage { … }` would be needed for tunnelling. **Needs
   adjudication** — it determines whether `.hcplang` grows MCP-shaped types.
3. **Tag `@0` / extension space.** This RFC reserves `@0` for the header and an
   extension space but does not define the extension mechanism. Should unknown
   top-level extensions be a reserved union at `@0`, or handled purely by the
   wire layer?
4. **Hash algorithm default.** §6.5 defaults schema digests / `eventd` to
   SHA-256. Should BLAKE3-256 be the default (speed), and should the algorithm be
   schema-pinned, connection-negotiated, or fixed protocol-wide? *(Provisional,
   for the human to confirm: independent of the default, §6.5 now **length-
   prefixes the digest** (`varint(algo-id) varint(len) bytes`) so that an unknown
   future `algo-id` is skippable and round-trippable. That wire-skippability fix
   stands whatever default you pick here; it does not pre-decide the default.)*
5. **`map` key canonicalisation for floats.** Float keys are disallowed
   (`key_type` excludes `f32`/`f64`) to avoid `-0.0`/NaN ordering ambiguity. Is
   that restriction acceptable, or is there a real need for float-keyed maps?
6. **Default-omission vs explicit presence.** §6.3 mandates omitting
   default-valued non-optional fields for canonicality. An alternative is "always
   emit non-optional fields" (simpler decoders, larger frames, but also
   canonical). Which trade-off does HCP want?
7. **String normalisation cost.** §6.4 mandates NFC normalisation of `string` on
   encode. This is a real CPU cost on the hot path in the Zig daemons. Acceptable,
   or should normalisation be the producer's responsibility with decoders
   trusting (and only validating) NFC? *(Provisional, for the human to confirm:
   this question is about **who pays** the cost and stays open. Independently,
   §6.4 now **pins the Unicode version to 15.1.0** for NFC, because NFC output is
   version-dependent and a bare "normalise to NFC" rule is not byte-for-byte
   deterministic across implementations — without a pinned version the `eventd`
   hash chain diverges between peers built against different Unicode tables. The
   version pin is required for determinism regardless of who runs the
   normalisation; please confirm 15.1.0 as the frozen baseline, or substitute the
   preferred stable Unicode version.)*
8. **Service/method authority granularity.** §8/§9 let `preceptord` scope by
   service, frame class, or schema digest. Is method-level (`call invoke`)
   granularity also required, and if so should methods carry a stable id like
   fields do?

## References

- [`protocol/rfcs/0001-hcp.md`](./0001-hcp.md) — umbrella HCP RFC (frame model,
  wire, encoding container, roles).
- [`docs/protocol/README.md`](../../docs/protocol/README.md) — HCP / Litany
  overview, vocabulary, daemon roster, tools.
- [`docs/runtime/README.md`](../../docs/runtime/README.md) — runtime daemon
  roster (`agent-supervisord`, `eventd`, `mcp-brokerd`, …).
- [`docs/context/PROJECT_CONTEXT.md`](../../docs/context/PROJECT_CONTEXT.md) —
  canonical project overview, mantra, membranes, core stack.
- [`docs/language/0001-language-manifesto.md`](../../docs/language/0001-language-manifesto.md)
  — Vaked language principles `.hcplang` inherits.
- [`docs/language/0010-mirageos-unikernel-surface.md`](../../docs/language/0010-mirageos-unikernel-surface.md)
  — vsock / unikernel transport surface (Open question 1).
- [`protocol/hcplang/grammar.ebnf`](../hcplang/grammar.ebnf) — the normative
  grammar.
- [`protocol/hcplang/examples/hcp-core.hcplang`](../hcplang/examples/hcp-core.hcplang)
  — the worked example (§10).
