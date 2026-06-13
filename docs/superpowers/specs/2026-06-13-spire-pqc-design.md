---
date: 2026-06-13
status: Spike
track: Protocol
author: agent-session
relates-to: protocol/rfcs/0007-post-quantum-litany-sealed-image.md §4, Open Question 3
---

# SPIRE PQC design — RFC 0007 Q3 research spike

## Status

Spike (2026-06-13). Answers RFC 0007 Open Question 3: *"Does the chosen SPIRE
deployment issue ML-DSA SVIDs natively, or is a hybrid-cert shim needed?"*
Supersedes the open question; a follow-on design note (or RFC amendment) will
carry any implementation decision.

## Summary finding

**Native ML-DSA SVIDs from SPIRE are not available in any stable release as of
June 2026.** SPIRE's `ca_key_type` supports four classical key types only:
`ec-p256`, `ec-p384`, `rsa-2048`, `rsa-4096`. The `require_pq_kem` flag (added
experimentally, circa SPIRE 1.10+) enforces ML-KEM-based TLS key exchange
between SPIRE components, but it does not change the SVID signature algorithm —
SVIDs remain ECDSA-signed X.509 certificates.

A community proof-of-concept (`marques-ma/SPIRE-PostQuantum-PoC`) has shown the
architecture is feasible via a SPIRE fork that calls into oqs-openssl for hybrid
PQ material, but that PoC is explicitly non-production and not upstreamed. No
SPIRE upstream issue or roadmap item tracks native ML-DSA SVID support as of the
research date.

**Recommendation for vakedos: implement the hybrid X.509 shim described in §3.**

---

## 1. SPIRE's current PQC posture

### 1.1 Key types — classical only

SPIRE server accepts `ca_key_type` (and `jwt_key_type`) from the set:

| Value | Algorithm | Notes |
|-------|-----------|-------|
| `ec-p256` | ECDSA P-256 (default) | Standard SVID type for most deployments |
| `ec-p384` | ECDSA P-384 | Higher classical security margin |
| `rsa-2048` | RSA-2048 | Legacy; only for compliance requirements |
| `rsa-4096` | RSA-4096 | Larger RSA |

ML-DSA, SLH-DSA, Dilithium, or any NIST PQC signature algorithm are not in
this list and cannot be added through configuration alone. The underlying Go
`crypto/x509` standard library on which SPIRE is built does not support FIPS 204
key OIDs, so even a custom `KeyManager` plugin that returns ML-DSA key handles
would fail at the cert-signing layer.

### 1.2 PQ-KEM transport (SPIRE-to-SPIRE)

SPIRE has an experimental `require_pq_kem` flag (server and agent
configuration), defaulting to `false`, that enforces a post-quantum-safe key
encapsulation mechanism for the TLS channel between SPIRE server and SPIRE
agent. When `true`, an ML-KEM-based TLS 1.3 group is required. This protects
SPIRE's own internal control plane against harvest-now-decrypt-later, but it is
orthogonal to SVID content: the SVID certificates issued through this channel
are still ECDSA-signed. The workload SVID keys and signatures are classical
regardless of whether `require_pq_kem` is set.

### 1.3 Community PoC — not production

`marques-ma/SPIRE-PostQuantum-PoC` (GitHub) demonstrates a SPIRE fork that
adds a `GenWorkloadPQX509SVID` function to the SPIRE server CA. The fork calls
a custom `oqsopenssl` Go package wrapping the OQS-OpenSSL docker image to
generate hybrid PQ key material. The certificate's PQ public key and signature
are smuggled into a DNSName SAN extension because oqs-openssl does not produce
standard X.509 PQ extensions. Key drawbacks explicitly noted by the PoC:

- **Not upstreamed.** The patch is against an older SPIRE version and is
  unmaintained.
- **SAN field abuse.** Encoding PQ material in DNSName SANs is non-standard and
  conflicts with real DNS SAN validation in most mTLS stacks.
- **Docker shim architecture.** The oqsopenssl package shells out to a running
  OQS-OpenSSL docker container for crypto operations, adding latency and
  architectural coupling.
- **Not FIPS 204 compliant.** The PoC predates the final ML-DSA standard; its
  Dilithium parameters do not match FIPS 204 exactly.

This PoC validates the feasibility of the shim approach (§3) but does not
provide a production path.

### 1.4 Upstream roadmap

No tracked issue, RFC, or milestone in `spiffe/spire` addresses native PQC SVID
support as of the research date. The SPIFFE community is watching IETF work on
PQC X.509 extensions (ITU-T Rec. X.509 §9.8; IETF Hackathon pqc-certificates),
but no timeline commitment exists. A reasonable assumption: native ML-DSA SVIDs
in SPIRE upstream are 2–4 years away from stable availability, contingent on
Go's crypto library absorbing FIPS 204 support.

---

## 2. If native support becomes available

This section is forward-looking — captured for the crypto-agility (RFC 0007 §6)
migration path, not for immediate implementation.

When SPIRE upstream gains a `ml-dsa-65` (or composite `ed25519+ml-dsa-65`)
`ca_key_type`:

```hcl
# spire-server.conf — hypothetical future config
server {
  trust_domain   = "agentfield.vakedos"
  ca_key_type    = "ml-dsa-65"       # FIPS 204 parameter set II
  ca_ttl         = "24h"
  svid_ttl       = "1h"
  require_pq_kem = true              # already available today
}
```

SVIDs would carry an OID from the FIPS 204 namespace, the SPIRE bundle would
include the ML-DSA trust anchor, and workloads would present ML-DSA-signed
X.509 certs for mTLS. The Litany Wire implementation (RFC 0007 §3) would
validate the hybrid transcript signature against the ML-DSA half of the SVID.

Until that is available, §3 is the operational path.

---

## 3. Hybrid X.509 shim design (recommended for vakedos)

Since SPIRE cannot natively issue ML-DSA SVIDs, the recommended approach is a
**post-processing shim** that attaches ML-DSA-65 material to the classical SVID
as a non-critical X.509v3 extension. Verifiers that understand the extension
check both; legacy verifiers that do not understand it ignore the extension
(X.509 non-critical semantics) and validate classically.

### 3.1 Architecture overview

```
SPIRE Workload API
    │
    │ classical X.509 SVID (ECDSA P-256, short-lived)
    ▼
PQC Shim (local sidecar or library)
    │ reads SVID from Workload API
    │ generates ephemeral ML-DSA-65 keypair (liboqs)
    │   OR fetches long-lived ML-DSA key from KMS
    │ appends extension OID 1.3.9999.2.7.1 (ml-dsa-65 public key)
    │ appends extension OID 1.3.9999.2.7.2 (ml-dsa-65 signature over TBSCertificate)
    │ re-emits cert with extensions added (DER re-encoding)
    ▼
Workload (Litany Wire / RFC 0007 §3)
    │
    │ presents shim-augmented SVID in mTLS handshake
    │ peer verifies:
    │   (a) ECDSA signature — classical validation path
    │   (b) ML-DSA-65 extension — PQC validation path
    │ connection accepted if both paths hold
    ▼
preceptord / oraclefd
```

### 3.2 X.509 extension encoding

Two non-critical extensions are added to the SVID DER after SPIRE issues it:

| OID | Content | Format |
|-----|---------|--------|
| `1.3.9999.2.7.1` | ML-DSA-65 SubjectPublicKeyInfo (SPKI) | DER-encoded SPKI, per FIPS 204 |
| `1.3.9999.2.7.2` | ML-DSA-65 signature over TBSCertificate | Raw ML-DSA signature bytes |

The OID `1.3.9999` is used by the Open Quantum Safe project for prototype/test
PQ algorithms and is the conventional space for pre-standard work. When
IETF/IANA allocates permanent OIDs for composite ML-DSA certificates (in
progress as of mid-2026 via IETF LAMPS WG draft `lamps-pq-composite-sigs`),
the shim should be updated; the crypto-agility machinery (RFC 0007 §6) makes
this a suite version bump.

The signature in `1.3.9999.2.7.2` is computed over the **unmodified
TBSCertificate** (the same bytes SPIRE signed with ECDSA). This means:
- SPIRE's ECDSA signature and the shim's ML-DSA signature cover the same
  content.
- The ML-DSA signature does not cover the extensions themselves (to avoid
  circularity), consistent with the alt-signature approach in ITU-T X.509 §9.8.
- A verifier can check ML-DSA independently of ECDSA by extracting
  TBSCertificate from the modified cert and verifying against the public key in
  `1.3.9999.2.7.1`.

### 3.3 ML-DSA keypair management

Two models for the ML-DSA keypair attached to each SVID:

**Model A — ephemeral per-rotation (simpler, recommended for v1):**

Each time the Workload API delivers a new SVID (on rotation, typically every
hour), the shim generates a fresh ML-DSA-65 keypair from `liboqs`, signs the
TBSCertificate, and embeds the public key in the extension. The private key is
held in memory for the lifetime of the SVID and discarded on rotation. The
classical SPIRE rotation schedule drives everything.

Advantages:
- No key storage problem — the ML-DSA key lives as long as the SVID.
- No KMS dependency in v1.
- Rotation is automatic, same cadence as the SPIFFE rotation (RFC 0006 §1.5).

Disadvantages:
- The ML-DSA private key is in process memory; a memory-disclosure attack
  against the workload process exposes it.
- Peers cannot pin or cache the ML-DSA public key across rotations (it changes
  every hour).

**Model B — long-lived ML-DSA key in KMS (stronger, v2):**

A hardware-backed ML-DSA-65 key (e.g., stored in a Zig-managed memory-mapped
file under `agent-guardd`'s namespace, or in a future HSM) is bound to the
agent's SPIFFE ID. The shim fetches the public key from the KMS and signs with
the private key. The KMS key rotates on a longer schedule (quarterly or annually)
than the SVID (hourly).

Advantages:
- ML-DSA private key never in workload process memory.
- Peers can cache the ML-DSA public key across SVID rotations.

Disadvantages:
- Requires a key management daemon not yet in the vakedos roster.
- Rotation decoupled from SVID rotation; cert renewal flow is more complex (§5
  open question 1).

**Recommendation:** Start with Model A for the v1 spike (RFC 0007 Open Question
5). Graduate to Model B when `agent-guardd` or a dedicated key-management daemon
is specified.

### 3.4 liboqs as the ML-DSA implementation

`liboqs` (Open Quantum Safe / PQCA) is the reference implementation:

- Version 0.14.0 (latest as of mid-2026) supports ML-DSA-44/65/87 (FIPS 204
  final) and drops the older Dilithium round-3 variants.
- Available in nixpkgs as `pkgs.liboqs`; compatible with the vakedos NixOS
  environment.
- `oqs-provider` wraps `liboqs` as an OpenSSL 3 provider, enabling PQ key
  generation and signing via the standard OpenSSL API.
- For a shim in Go (consistent with SPIRE's own language),
  `github.com/open-quantum-safe/liboqs-go` provides CGo bindings to liboqs.
- For a Zig shim, `liboqs` can be linked directly as a C library via Zig's
  native C interop; no CGo overhead.

**Key selection:** ML-DSA-65 (parameter set II, NIST security level 3) for
per-agent SVIDs, matching RFC 0007 §4. The trust-domain root uses SLH-DSA
(available in liboqs as FIPS 205 variant), consistent with RFC 0007 §4's
conservatism for long-lived roots.

### 3.5 Shim deployment on vakedos

The shim runs as a small sidecar or in-process library alongside each workload.
On vakedos (NixOS, `hosts/vakedos/configuration.nix`), the shim is packaged as
a NixOS module that:

1. Is declared in the lowered `gen/zig/<fiber>.json` as a sidecar entry (or
   as a library linked into the Litany Wire implementation).
2. Receives the Workload API socket path and the augmented-SVID output path.
3. Watches the SVID via the SPIRE Workload API streaming gRPC interface and
   re-issues the augmented cert within milliseconds of each rotation.
4. Exposes the augmented cert on a local path; the workload reads from this
   path rather than directly from SPIRE.

```nix
# future nixosModule fragment (illustrative)
services.vakedPqcShim = {
  enable       = true;
  spireSocket  = "/run/spire/agent.sock";
  outputPath   = "/run/vaked-pqc/%i/svid.pem";
  keyType      = "ml-dsa-65";
  liboqsPackage = pkgs.liboqs;
};
```

The host already provides the prerequisites: `liboqs` can be added to
`environment.systemPackages` or pulled into the daemon's closure; user
namespaces, systemd services, and the Zig toolchain (`pkgs.zig`) are in place.

The AMD EPYC 4345P (Zen 5, AVX-512) performs ML-DSA-65 operations in the
low-microsecond range; there is no performance concern for the SVID rotation
cadence (hourly) or for handshake overhead at the agent count expected on a
single-host deployment.

### 3.6 Verifier logic

Litany Wire peers (RFC 0007 §3) verify the SVID on a TLS handshake by:

1. Extracting the peer certificate's two OQS extensions.
2. If both extensions are present:
   - Verify the ECDSA signature on TBSCertificate (classical path).
   - Reconstruct the ML-DSA-65 public key from extension `1.3.9999.2.7.1`.
   - Verify the ML-DSA-65 signature in `1.3.9999.2.7.2` over TBSCertificate.
   - **Accept if both succeed.** A cert that passes only one half indicates
     tampering or certificate substitution; reject and log to `eventd`.
3. If extensions are absent (classical-only peer or pre-shim SVID):
   - Verify ECDSA only; accept if the peer's `crypto_suite` field indicates
     classical-only mode.
   - If local policy requires hybrid (`pq-required`), emit
     `REFUSE{pq-required}` per RFC 0007 §3 negotiation and record to `eventd`.

The "accept if both succeed" rule is stricter than the "secure if either holds"
framing used for the forward-secrecy property of the key exchange (§3 of RFC
0007). The distinction: hybrid KEM protects *sessions in transit* (secure if
either KEM holds against future decryption), while the shim protects *identity
assertions* (a forger must break both ECDSA and ML-DSA to mint a valid cert;
once generated, both halves should verify). Both properties are present and
complementary.

---

## 4. Recommendation for vakedos

**Deploy SPIRE with `require_pq_kem = true` for the SPIRE control plane (no
code change required), and implement the hybrid X.509 shim (§3) for workload
SVIDs to provide PQ-signed identity at the Litany Wire layer.**

Concrete steps:

| Step | Action | Status |
|------|--------|--------|
| 1 | Enable `require_pq_kem = true` in `spire-server.conf` and `spire-agent.conf` | Config-only; unblocked |
| 2 | Add `liboqs` to vakedos `environment.systemPackages` in `configuration.nix` | Nixpkgs package exists |
| 3 | Implement shim (Zig, Model A) reading Workload API, writing augmented SVIDs | New implementation |
| 4 | Wire shim output into the Litany Wire handshake path | Requires RFC 0003/0007 wire impl |
| 5 | Implement verifier logic for the two OQS extensions in the wire layer | Part of wire impl |
| 6 | RFC 0007 spike: lower a minimal `network` membrane, attach votive seal, verify measured admit/refuse with shim-augmented identity | RFC 0007 Open Question 5 |

**Version:** SPIRE v1.10 or later (for `require_pq_kem` support); pin in
`flake.nix` to a specific release hash.

**Key algorithm choices:**
- Per-agent SVIDs: Ed25519 (classical) + ML-DSA-65 (PQ) hybrid shim.
- Trust-domain root: SLH-DSA (FIPS 205) via a separately managed offline
  signing ceremony; not issued through SPIRE's CA path.
- liboqs ≥ 0.14.0 required for FIPS 204 final (not round-3 Dilithium).

---

## 5. Open questions remaining

1. **Cert renewal flow for Model B (long-lived ML-DSA key):** When the SPIRE
   SVID rotates (hourly) but the ML-DSA key rotates quarterly, what is the
   update protocol? Peers that have cached the ML-DSA public key must be
   notified of ML-DSA key rotation separately from SVID rotation. Lean: treat
   ML-DSA rotation as a topology-epoch bump (RFC 0006 §1.4) so in-flight
   epoch-valid frames remain valid through the rotation window.

2. **SPIRE upstream PQC timeline:** When Go's `crypto/x509` adds FIPS 204 OID
   support and SPIRE upstream incorporates it, the shim should be retired and
   replaced by native `ca_key_type = "ml-dsa-65"`. Track the Go issue tracker
   and `spiffe/spire` releases; the crypto-agility machinery (RFC 0007 §6)
   makes the migration a suite version bump with no wire-format change.

3. **SLH-DSA root signing ceremony:** The trust-domain root using SLH-DSA
   (RFC 0007 §4) is not covered by the SPIRE CA path. This requires an offline
   key ceremony and a SPIRE UpstreamAuthority plugin that can present an
   SLH-DSA-signed root bundle. Liboqs supports SLH-DSA from 0.12+; the plugin
   design is deferred until the SPIRE native PQC path is clearer.

4. **OID finalization:** The `1.3.9999.2.7.*` namespace is OQS prototype space.
   IETF LAMPS WG is working on composite ML-DSA certificate OIDs; track and
   migrate when IANA allocates stable OIDs. The shim's OID values should be
   constants behind a named suite version (RFC 0007 §6 crypto-agility).

5. **Composite vs. dual-extension:** IETF's composite approach encodes the PQ
   key + signature and classical key + signature as a single composite OID
   (e.g., `id-MLDSA65-Ed25519`), rather than two separate extensions. The
   composite approach is more standards-aligned and produces a single verifiable
   object; the dual-extension approach described here is easier to implement
   today without a composite-capable X.509 library. Revisit when `oqs-provider`
   and Go's crypto stack support composite certificates in a production-grade
   release.

---

## References

- [RFC 0007](../../../protocol/rfcs/0007-post-quantum-litany-sealed-image.md) §4 — Post-quantum identity & attestation
- [RFC 0006](../../../protocol/rfcs/0006-transport-identity-distribution.md) — SPIFFE/SPIRE identity model
- [`hosts/vakedos/configuration.nix`](../../../hosts/vakedos/configuration.nix) — Target host
- [SPIRE Server Configuration Reference](https://spiffe.io/docs/latest/deploying/spire_server/) — `ca_key_type`, `require_pq_kem`
- [marques-ma/SPIRE-PostQuantum-PoC](https://github.com/marques-ma/SPIRE-PostQuantum-PoC) — Community PoC
- [open-quantum-safe/liboqs](https://github.com/open-quantum-safe/liboqs) — ML-DSA implementation
- [open-quantum-safe/oqs-provider](https://github.com/open-quantum-safe/oqs-provider) — OpenSSL 3 PQ provider
- [Open Quantum Safe X.509](https://openquantumsafe.org/applications/x509.html) — PQ X.509 tooling
- [IETF-Hackathon/pqc-certificates](https://github.com/IETF-Hackathon/pqc-certificates) — PQ X.509 certificate work
- [FIPS 204 (ML-DSA)](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) — NIST standard
- [RFC 9794 — Terminology for PQ/Traditional Hybrid Schemes](https://www.rfc-editor.org/rfc/rfc9794.html)
- [liboqs 0.14.0 release announcement](https://pqca.org/blog/2025/pqca-announces-release-of-liboqs-version-0-14-0-from-open-quantum-safe-project/) — ML-DSA FIPS 204 final
