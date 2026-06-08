---
name: hcp-rfc-author
description: Use when writing or revising HCP / Litany protocol RFCs (Litany Wire, Votive Frames, .hcplang, hcpbin) under protocol/rfcs/ — enforces the RFC structure, vocabulary, and cross-links. Trigger on "HCP", "Litany", "Votive Frame", ".hcplang", "hcpbin", "RFC", "wire protocol".
---

# Authoring HCP / Litany RFCs

HCP is the harness control / IPC protocol; Litany is its reference implementation.
RFCs are the normative source of truth — overview docs summarize, RFCs decide.

## Where things live

| Concern | Path |
|---------|------|
| RFCs (normative) | `protocol/rfcs/NNNN-*.md` |
| Overview + vocabulary + roster | `docs/protocol/README.md` |
| Code subtree | `protocol/` |

## RFC conventions

1. **Numbering.** Zero-padded, sequential: `0001-hcp.md`, `0002-…`. One concept per
   RFC once the surface grows; `0001` is the umbrella.
2. **Front matter.** Every RFC opens with: Status (Draft / Review / Accepted /
   Superseded), Created date, Track.
3. **Standard sections.** Abstract → Terminology → numbered body sections → Security
   considerations → Open questions. Keep the terminology table aligned with
   `docs/protocol/README.md`; if you add a term, add it in both places.
4. **Use the established vocabulary** exactly: HCP, Litany Wire, Votive Frame,
   `.hcplang`, `hcpbin`, and the daemons `chapterd`/`preceptord`/`reliquaryd`/
   `candled`/`petitiond`/`oraclefd`, tools `litanyctl`/`litanydump`/`litanyfmt`/
   `litanyreplay`. Don't coin synonyms.
5. **Determinism & evidence.** Encodings must be canonical/deterministic; anything
   security-relevant ties back to `preceptord` (authority) and hash-chained `eventd`
   (tamper-evidence).
6. **Cross-link** the runtime (`docs/runtime/README.md`) and, where transport
   choices matter, the [MirageOS unikernel note](../../../docs/language/0010-mirageos-unikernel-surface.md) (vsock).

## When you finish

- Update the roster/vocabulary in `docs/protocol/README.md` if the RFC changed it.
- Bump the RFC's Status when it moves stages; never silently rewrite an Accepted RFC — supersede it.
