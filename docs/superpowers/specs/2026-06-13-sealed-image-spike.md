# Sealed-image spike — RFC 0007 Q5

- **Date:** 2026-06-13
- **Track:** Protocol / tooling spike
- **RFC cross-ref:** RFC 0007 §5 (image-as-code & sealed-image attestation), Open Questions 1, 2, 5
- **Target membrane:** `network/agent-egress` (`vaked/examples/membrane/agent-egress.vaked`)
- **Artifacts:**
  - `tools/seal/provenance-schema.json` — JSON Schema (draft-07) for `provenance.json`
  - `tools/seal/sign-provenance.sh` — shell + Python signing script
  - `tools/seal/preceptord-mock.py` — Python mock admission controller

## 1. What the spike does

This spike closes the **produce → sign → admit** loop for a single Vaked membrane
without requiring the full RFC 0007 PKI or a real preceptord daemon. It exercises
the *image-as-code* flow end-to-end on the `network/agent-egress` membrane:

1. **`provenance-schema.json`** — a JSON Schema (draft-07) defining the
   `provenance.json` votive-seal document. Every materialized image (NixOS
   closure, OCI layer, unikernel) carries one of these; the deploy plane checks
   it before admission. Required fields: `kind`, `version`, `closure_hash`
   (SHA-256 hex), `topology_epoch` (integer), `membrane` (e.g.
   `"network/agent-egress"`), `signed_at` (ISO 8601 UTC). A `signature` object
   carries `algorithm`, `value` (base64), and optionally `public_key` (base64).

2. **`sign-provenance.sh`** — accepts a closure path (directory or file) or a
   bare 64-hex hash plus a membrane name and optional epoch, and writes a signed
   `provenance.json` to stdout.

   Signature strategy (runtime-detected):
   - If `python3 -c "import oqs"` succeeds: sign with **ML-DSA-65** (FIPS 204 /
     CRYSTALS-Dilithium3 level-3) via the liboqs Python bindings. The key pair
     is ephemeral for the spike.
   - Otherwise: fall back to **HMAC-SHA256** with an OS-random ephemeral key.
     The seal carries `"placeholder": true` in the signature object and the
     algorithm is `"hmac-sha256-placeholder"`. This is explicitly NOT ML-DSA and
     NOT post-quantum; the field makes that unambiguous to any downstream consumer.

   Canonical payload: the provenance fields (excluding `signature`) serialised
   with sorted keys and no extra whitespace — `json.dumps(…, sort_keys=True,
   separators=(",", ":"))`. This matches the schema's stated canonical-JSON rule
   and is what gets signed (and what `preceptord-mock.py` reconstructs for
   verification).

3. **`preceptord-mock.py`** — `python3 preceptord-mock.py <provenance.json>`.
   Reads the seal, runs structural validation (required fields, regex on
   `closure_hash`, integer epoch), checks `membrane` against a hardcoded spike
   allowlist, and dispatches on `signature.algorithm`:
   - `"hmac-sha256-placeholder"` with `placeholder: true` → logs a stderr
     warning and proceeds (spike mode; key not available for re-verification).
   - `"ml-dsa-65"` → verifies with liboqs; refuses if the library is absent or
     the signature is invalid.
   - Emits `ADMIT: <membrane> closure=<hash> epoch=<epoch>` (exit 0) or
     `REFUSE: <reason>` (exit 1).

### End-to-end example

```bash
# Produce a seal for the agent-egress closure (hash supplied directly for spike):
./tools/seal/sign-provenance.sh \
    a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4 \
    network/agent-egress \
    1 \
    > /tmp/provenance.json

# Admit (or refuse) via the mock controller:
python3 tools/seal/preceptord-mock.py /tmp/provenance.json
# → WARNING: spike mode: signature.placeholder=true ... (stderr)
# → ADMIT: network/agent-egress closure=a3b4... epoch=1
# exit 0
```

## 2. What this answers

### Q5 — image-as-code flow end-to-end

RFC 0007 Q5 asks whether the full flow (closure produced → votive seal signed →
deploy plane admits) can be demonstrated on at least one membrane. This spike
answers **yes** for `network/agent-egress`:

- The schema defines the seal document format, making it a first-class artifact
  in the lowering output alongside `gen/ebpf.policy` and `gen/RUNTIME.md`.
- The sign script shows how the seal is produced at closure materialization time
  (the point after `nix build` / `nix path-info --hash` returns a store path).
- The mock controller shows the admission check the deploy plane performs before
  activating a new image. The `closure_hash → membrane` binding is the invariant:
  only images whose hash was signed under the declared membrane may be admitted.

### Q1 — vsock boundary (partial)

The seal is applied at **closure materialization time**, not at wire time.
This directly informs Q1: the votive seal establishes *what was built* and
*which membrane it implements*, but does not authenticate the *channel* through
which that image arrives at the deploy plane. The Litany Wire (RFC 0003) is
still needed to protect the delivery channel from the build system to the host.
The seal and the wire are complementary, not substitutes.

The spike confirms: seal-at-build, wire-at-delivery is the correct split.

## 3. What this defers

| Deferred item | Why deferred | Path to resolution |
|---|---|---|
| Real ML-DSA-65 | Requires liboqs or Zig ML-DSA-65. Key infrastructure (PKI, rotation, revocation) not yet designed. | RFC 0007 §6; wire into `vakedc lower` once the Zig ML-DSA-65 crate is available or liboqs is added to the dev shell. |
| Real preceptord | The mock is a script; the real preceptord is a supervised Zig daemon that holds the policy store and the topology epoch. | `daemons/preceptord/` — design → plan → implement per CLAUDE.md convention. |
| TPM measurement binding (Q2) | The seal's `closure_hash` is a content hash, not a TPM PCR quote. Binding the seal to a TPM measurement requires hardware on the vakedos host. | Spike separately on the EPYC 4345P host once the bare-metal NixOS deploy is stable. |
| Epoch fence (Q5 detail) | The mock checks `topology_epoch >= 0` but does not cross-check the current epoch in a live topology store. | Wire into the real preceptord's epoch tracking (RFC 0005 §2.4). |
| Persistent signing key | The spike uses an ephemeral key. | PKI design (separate RFC or RFC 0007 §6 extension): key managed by SPIRE SVID rotation or a hardware token. |

## 4. Next step: wire into `vakedc lower`

The natural next integration point is the `vakedc lower` pass. When a `network`
membrane is lowered (emitter `ebpf.policy`, currently deferred in `lower.py`
`emit_deferred`), the lowering pass should also emit a `provenance.json` stub:

```python
# In emit_deferred (or a new emit_votive_seal emitter):
# For each network membrane node, emit a provenance.json template with
# closure_hash = "<placeholder>" (the build resolves it post-nix-build)
# and all other fields populated from the graph (membrane name, topology_epoch
# from the runtime decl, signed_at = build time).
# The sign step (sign-provenance.sh or its Zig equivalent) then replaces
# the placeholder hash and signs.
```

This closes the declare → lower → sign → admit loop fully within the Vaked
pipeline, making `provenance.json` as first-class as `flake.nix` and
`gen/ebpf.policy`.
