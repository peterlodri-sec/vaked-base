# Ralph decision log — hcp-litany

> Machine-generated, ADVISORY. Each entry is one strategic decision surfaced by the ralph loop (qwen3-235b-thinking → deepseek-v4-flash). A human ratifies; entries are appended, never rewritten.

## 2026-06-13 — Decision #1: We need to improve the draft strategic decision entry. Let's first identify the 
- **Track:** hcp-litany · **Models:** stage1 hy3-preview · stage2 hy3-preview
- **Context snapshot:** HEAD d4bb11e, 0 open issues

We need to improve the draft strategic decision entry. Let's first identify the issues:

- The draft claims: "RFC 0003 §4 depends on `hcpbin` for frame bodies." The grounding context shows RFC 0003 §4 describes frame delimitation (frame records) using length prefix and frame-bytes, but it doesn't explicitly say it "depends on `hcpbin`" for frame bodies — it says "The wire treats `frame-bytes` as opaque except for parsing the header it itself wrote." and that `frame-bytes` is exactly one `hcpbin`-encoded Votive Frame. So it's correct that the frame body is `hcpbin`-encoded, but the explicit dependency phrasing could be more precise. However, the decision entry says "RFC 0003 §4 depends on `hcpbin` for frame bodies." Actually RFC 0003 §4.1 says `frame-bytes` is header-bytes ++ body-bytes, and body-bytes is `hcpbin` body. So the dependency is clear. We can keep it.

- The draft says "The `hcp-core.hcplang` example (`protocol/hcplang/examples/hcp-core.hcplang`) exercises all type constructs (records, unions, enums, optionals, maps, etc.) and provides a clear, bounded initial target." The example file does show records, unions, enums, optionals, maps (map<string,string>, list<Attr>), etc. It's accurate.

- It says "This directly addresses the `protocol/README.md` statement that the implementation is “Currently empty of code” and unblocks the entire HCP/Litany stack." The protocol/README.md says "Currently empty of code. Implementation directories ... are created when each piece enters its design → plan → implementation cycle." That is correct.

- Recommendation: Option A. The draft gives justification: `hcpbin` is foundational primitive required before wire framing, daemon development, interop testing. RFC 0002 §6 defines canonical encoding rules; RFC 0003 §4 depends on `hcpbin` for frame bodies. The `hcp-core.hcplang` example provides initial schema. It directly addresses the empty-of-code statement.

- Risks: "The `hcpbin` spec (RFC 0002 §6) is detailed but may contain edge cases that only emerge during implementation (e.g., NFC normalization pinned to Unicode 15.1.0, strict varint rejection, default omission rules). However, these are well-defined and can be resolved through conformance testing. Delaying `hcpbin` would block all downstream wire and daemon work." We need to ensure that the edge cases are indeed from RFC 0002 §6. Yes, NFC normalization pinned to Unicode 15.1.0 is in §6.4; strict varint rejection is in §6.1 and §6.8; default omission rules are in §6.3. So those citations are valid.

- Next actions: "Open a PR to create `protocol/hcpbin/` with a Zig implementation of the `hcpbin` encoder/decoder, targeting the types defined in `protocol/hcplang/examples/hcp-core.hcplang`. The PR should include unit tests that verify canonical encoding/decoding round-trips and reject non-canonical inputs per RFC 0002 §6.8. Link the PR to a new issue titled “Implement hcpbin canonical binary encoder/decoder”." The PR and issue naming are concrete. The Zig implementation is suggested; however, the decision draft doesn't specify language. Is it in the context? The protocol/README.md says "Implementation directories (wire codec, `.hcplang` compiler, `litany*` tools, the `*d` daemons) are created when each piece enters its design → plan → implementation cycle." The daemons are Zig and Erlang, but the wire codec could be either. The decision entry mentions a Zig implementation. But is Zig mentioned in the context? Not explicitly, but it's plausible. However, the decision should be about prioritizing the `hcpbin` encoder/decoder, not specifying language. The next actions could be generic: "implement an `hcpbin` encoder/decoder (language TBD based on platform needs)"? The draft says Zig, but that's an implementation detail. Since the decision is about priority, we can state the next action as "Create PR implementing `hcpbin` encoder/decoder that targets `hcp-core.hcplang` types and includes canonicality tests per RFC 0002 §6.8. Language choice to be decided with further discussion." But we want to keep it concrete. The context doesn't provide a language decision, so maybe we shouldn't specify Zig. The draft's mention of Zig is not grounded in the context; we could remove "Zig" and say "a Zig (or other) implementation" but we need to be careful. Let's check the context: The only mention of Zig is in RFC 0002 §7 Codegen mapping: "Zig structs for the enforcement daemons" and "Zig struct" etc. So the daemon codegen targets Zig, not that the `hcpbin` library must be Zig. But the codec could be in Zig to be used by those daemons, which is plausible. But the decision entry is making a claim that Zig is needed, which might be an unwarranted tangent. Since the objective is to improve grounding, we should remove the unsupported claim about language or make it optional. For example: "Open a PR to create `protocol/hcpbin/` with an implementation of the `hcpbin` encoder/decoder (language TBD, likely Zig per daemon codegen targets)." That links to the context: RFC 0002 §7 mentions Zig daemon codegen targets. So that's a soft justification. But the draft says "a Zig implementation" outright. We can keep it if we note that daemons are in Zig, and the codec should be in Zig for maximum integration; it's a logical inference but not explicitly stated. I think it's safe to say "a Zig implementation" because the project uses Zig for daemons (RFC 0002 §7). That is context: "`hcpbin` encoding rules" and "Codegen mapping" says "Zig structs for the enforcement daemons ... and BEAM/Erlang terms for the control plane." So the daemons that will use `hcpbin` are Zig, so implementing `hcpbin` in Zig is reasonable. It isn't hand-waving, it's referencing that the project targets Zig. So I'll keep "Zig" but note that it's because the daemons are in Zig.

- Confidence: high. The decision is to prioritize `hcpbin` over other options. The justification is well-supported by the context.

Now, we need to rewrite the entry to be sharper, better grounded: every claim must cite the actual file or issue it relies on; cut hand-waving and hedging; make the Recommendation concrete and the Next actions a specific PR/issue. Remove any claim not supported by the context.

Let's analyze each claim in the draft:

1. "Prioritize implementation of the `hcpbin` canonical binary encoder/decoder for `.hcplang` types." - the question itself is clear.

2. Options: The options list includes A: "Implement `hcpbin` encoder/decoder first, using `hcp-core.hcplang` as the initial test schema." B: implement Litany Wire framing first, deferring `hcpbin` to later. C: implement the `.hcplang` compiler/codegen first, then `hcpbin`. D: implement a daemon first using ad-hoc serialization. That's fine.

3. Recommendation: Option A. The justification includes:
   - "The `hcpbin` encoding is the foundational primitive required before any wire framing, daemon development, or interop testing can begin." That's an assertion. We need to ground it. From the context, RFC 0003 Litany Wire's frame delimitation uses `hcpbin` for frame bodies (§4.1: "frame-bytes is exactly one `hcpbin`-encoded Votive Frame"). So wire framing depends on `hcpbin` for the body encoding, thus `hcpbin` must exist before framing can be exercised meaningfully. Similarly, daemons like `mcp-brokerd` will need to encode/decode frames, so `hcpbin` is necessary. Interop testing also requires a common encoding. So we can cite RFC 0003 §4.1 for the dependency, and possibly the daemon roster in protocol/README.md (which lists daemons that will use frames). The protocol/README.md doesn't explicitly say they need `hcpbin` but it's implied; we can still say that the wire framing (RFC 0003) depends on it. That's sufficient.

   - "RFC 0002 §6 defines the canonical encoding rules; RFC 0003 §4 depends on `hcpbin` for frame bodies." That's accurate, citing those sections.

   - "The `hcp-core.hcplang` example (`protocol/hcplang/examples/hcp-core.hcplang`) exercises all type constructs (records, unions, enums, optionals, maps, etc.) and provides a clear, bounded initial target." The file is present and indeed includes those types. So cite the file path.

   - "This directly addresses the `protocol/README.md` statement that the implementation is “Currently empty of code” and unblocks the entire HCP/Litany stack." The protocol/README.md says "Currently empty of code." So yes.

   The Recommendation also might note that `hcpbin` is the first code needed because many other components (framing, daemons) depend on it. We'll keep.

4. Risks: "The `hcpbin` spec (RFC 0002 §6) is detailed but may contain edge cases that only emerge during implementation (e.g., NFC normalization pinned to Unicode 15.1.0, strict varint rejection, default omission rules)." Those are risks. We can cite specific sub-sections: NFC normalization in §6.

## 2026-06-13 — Decision #2: Decision / question:
- **Track:** hcp-litany · **Models:** stage1 hy3-preview · stage2 deepseek-v4-pro
- **Context snapshot:** HEAD 0a0a5ff, 8 open issues

**Decision / question:**  
Should the `hcpbin` canonical binary encoder/decoder for `.hcplang` types be the first code artifact implemented in the HCP/Litany stack?

**Options**  
- **A** — Implement `hcpbin` first, using `protocol/hcplang/examples/hcp-core.hcplang` as the conformance schema. This immediately unblocks Litany Wire framing (RFC 0003), daemon development, and interop testing.  
- **B** — Implement Litany Wire framing first, delaying `hcpbin`. RFC 0003 framing bodies require `hcpbin`-encoded Votive Frames, so a temporary ad‑hoc encoding would be needed, breaking canonicality from the start.  
- **C** — Implement the `.hcplang` compiler/codegen first, then `hcpbin`. The compiler produces types that `hcpbin` encodes, but without `hcpbin` the compiler’s output cannot be validated.  
- **D** — Implement a daemon first using ad‑hoc serialization, then retrofit `hcpbin`. Non‑canonical frames would enter the `eventd` chain, undermining tamper‑evidence and replay guarantees.

**Recommendation**  
**Option A — Implement `hcpbin` first.**  
`protocol/README.md` states the implementation is “Currently empty of code.” The HCP architecture defines `hcpbin` (RFC 0002) as the canonical binary encoding for all `.hcplang` types, and Litany Wire (RFC 0003) requires `hcpbin`‑encoded frame bodies. No wire‑level or daemon work can produce correct frames without it.  
`hcp-core.hcplang` exercises all type constructs—records, unions, enums, optionals, maps, lists—providing a precise, bounded target for the encoder/decoder. Delivering `hcpbin` against this schema unlocks the entire downstream stack.

**Risks**  
- The `hcpbin` specification defines strict canonicalization rules; edge cases may surface during implementation. These can be resolved through conformance tests round‑tripping the `hcp-core` schema.  
- Delaying `hcpbin` blocks all dependent work (framing, `mcp‑brokerd`, `eventd`) because every component must emit canonical frames to preserve the chain of trust.

**Next actions**  
1. Open issue “Implement hcpbin canonical binary encoder/decoder” referencing RFC 0002 and the `hcp-core.hcplang` schema.  
2. Submit a PR to a new `protocol/hcpbin/` directory that implements the encoder/decoder targeting the types in `hcp-core.hcplang`, with unit tests verifying canonical round‑trips and rejection of non‑canonical inputs per the specification. Language choice: Zig (per RFC 0002’s daemon codegen mapping) or a portable C library with Zig bindings.  
3. After `hcpbin` lands, implement Litany Wire framing (RFC 0003) on top of it, then the `hcp‑core` service frames.

**Confidence**  
**High** — the HCP architecture places `hcpbin` as the foundational encoding (RFC 0001, RFC 0002, RFC 0003). The `hcp-core.hcplang` schema exists and is ready to serve as the conformance target. No alternative can proceed without `hcpbin` while maintaining canonicality guarantees.

