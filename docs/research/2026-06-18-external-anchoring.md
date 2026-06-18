---
title: Anchoring Integrity Claims Externally — Defeating Tamper-with-Reseal
date: 2026-06-18
provenance: deep-research workflow (20 agents, 14 sources, adversarially fetched)
status: research — cited; [UNVERIFIED] tags preserved verbatim
relates: the-honest-swarm-researcher/REPAIR_AUDIT.json (residual: manifest-unanchored)
---

> Repo-specific finding (verified this session): `the-honest-swarm-researcher/SEALS.sha256`
> exists; tags `v0.3.0`–`v0.6.0` are annotated but **unsigned** (`git tag -v v0.6.0` →
> "no signature found"); `tag.gpgSign`/`gpg.format` unset. The repo is currently at the
> L1 / self-referential failure mode with **no external anchor** — Tier 0 (sign the tag)
> is the immediate fix.

## 1. The core problem: self-referential trust

A checked-in `SEALS.sha256` manifest lists SHA-256 digests of the files it covers. By
itself it is **L1-equivalent** integrity: it exists, but is "trivial to bypass or forge"
and "may be incomplete and/or unsigned" (https://slsa.dev/spec/v1.0/levels). The targeted
failure mode is **tamper-with-reseal**: an actor that can write to the repo modifies a
covered file, recomputes its hash, and rewrites `SEALS.sha256` in the *same commit*.
Because the verifier's trust root (the manifest) lives in the same writable location as
the artifacts, the verifier is checking the attacker's arithmetic against the attacker's
answer key. The reseal is internally consistent and undetectable from inside the repo.

The defense is **externalization**: bind the integrity claim to something the resealing
party cannot rewrite in that commit — a key it does not hold, or an append-only log it
does not control. TUF names this a "rollback attack" and is built to protect "even against
attackers that compromise the repository or signing keys" (https://theupdateframework.io/).

## 2. Mechanisms, by externalization strategy

### A. Git signed tags + `git tag -v` — cheapest external anchor
Integrity rests on an external trust anchor — the signer's key in the verifier's keyring,
not the repo. `git tag -v` verifies the signature; a tamper-with-reseal cannot forge it
without the key. Created with `-s`/`-u <key-id>`; backends GPG/X.509/SSH via `gpg.format`.
Git refuses to silently overwrite a fetched tag (force leaves an auditable intent signal).
Universal, zero-infra, offline. Anchor strength = keyring distribution. (https://git-scm.com/docs/git-tag)

### B. Sigstore / cosign + Rekor — external append-only transparency
`cosign verify-blob` verifies a signature over an arbitrary file (the manifest). Keyless:
identity anchored to an external OIDC issuer (`--certificate-identity` /
`--certificate-oidc-issuer`; GitHub Actions = `https://token.actions.githubusercontent.com`) — a CI workflow
identity, not a dev key, becomes the anchor. Rekor is an immutable append-only ledger
outside the producer's control; inclusion provable via a Signed Entry Timestamp (offline).
Default claims-check binds signature to exact digest. Rekor monitor reusable workflow
detects entries under a stolen/rewritten root. Public `rekor.sigstore.dev` (99.5% SLO).
(https://docs.sigstore.dev/cosign/verifying/verify/, https://docs.sigstore.dev/logging/overview/)

### C. in-toto attestations (DSSE) — signed claim, multi-signer capable
Wrap the manifest in a DSSE-signed in-toto Statement; the signature, not a stored hash, is
verified. Consumers MUST verify the signature over the manifest, not re-read declared
hashes. Subjects matched purely by digest. Envelope supports multiple signatures → N-of-M
anchoring. Policy is monotonic: design as "deny unless a valid signed seal attestation
exists." Caveat: a Sigstore Bundle is single-signature, not ITE-5-compliant for multi-signer.
(https://github.com/in-toto/attestation)

### D. SLSA provenance levels — the assurance ladder
L1 = unsigned/incomplete (an unsigned `SEALS.sha256` is L1-equivalent). L2 = signed
provenance from a hosted build platform (prevents post-build tampering). L3 = signing
secret inaccessible to user-defined steps — "the entity that produces content cannot also
forge its seal." Directive: sign in CI, not on the dev MacBook. Cite SLSA **v1.2** as
current (v1.0 levels page is Retired and omits the Source track). (https://slsa.dev/spec/v1.0/levels)

### E. TUF — threshold + role separation + freshness
Most complete defense. `root.json` enumerates trusted keys + thresholds (M-of-N quorum so
a verifier can't reseal alone). Role separation; offline `targets`/`snapshot` keys + online
short-expiry `timestamp`. Freshness/anti-rollback (refuse metadata older than seen). Signed
`snapshot` binds the whole metadata set (defeats mix-and-match). CNCF graduated; highest
operational complexity — overkill for one seal file. (https://theupdateframework.io/)

### F. GitHub branch protection / rulesets — platform-anchored policy
Server-side control: require signed commits, block force-push, restrict the `SEALS.sha256`
path, tag rulesets for immutability, org-level rulesets above any repo admin. Rulesets must
be **Active** to enforce; editing them needs admin (separate from push); readable by anyone
(silent policy tamper is detectable). Access control, not cryptographic proof — pair with A/B/C.
(https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)

### G. CODEOWNERS — **[UNVERIFIED — no citation in evidence]**
Gates review approval on the `SEALS.sha256` path (required-reviewer control); composes with
rulesets. Treat as a complementary review control, not an external cryptographic anchor.

### H. Certificate-Transparency-style append-only logs (RFC 6962) — formal model under B
Append-only, publicly auditable, untrusted log; Merkle tree (SHA-256 — `SEALS` entries map
onto leaves). Inclusion proof (leaf present) + consistency proof (append-only). Signed Tree
Head over root hash with monotonic timestamps (anti-rollback). SCT = signed promise to log
within Maximum Merge Delay. Monitors recompute and cross-check. (https://www.rfc-editor.org/rfc/rfc6962)

## 3. Ranked recommendation for this repo's `SEALS.sha256`

- **Tier 0 — do today: signed git tag + `git tag -v`.** Signing key lives outside the repo;
  same-commit reseal without it fails verification. Set `tag.gpgSign=true` + a dedicated
  `user.signingKey`; tag the seal commit signed. The current `v0.3.0`–`v0.6.0` are unsigned
  → this is the highest-leverage immediate fix. (`git tag -s` is a git op, NOT a build — the
  NO-BUILD-ON-DEV-MACHINE rule does not apply.)
- **Tier 1 — platform lock (GitHub ruleset).** Restrict the `SEALS.sha256` path, require
  signed commits, block force-push, keep Active; CODEOWNERS for a second reviewer [UNVERIFIED].
  Raises *who* can reseal; not cryptographic — pair with Tier 0/2.
- **Tier 2 — transparency-anchored (cosign + Rekor + in-toto), in CI.** Sign the manifest
  keyless against the GitHub OIDC identity (key unreachable by the committing agent — SLSA
  L2/L3), log to Rekor, verify with `cosign verify-blob`. Wrap as DSSE in-toto Statement,
  policy deny-unless-valid. Enable Rekor monitor.
- **Tier 3 — only if you outgrow the above: full TUF** (threshold, offline keys, freshness).

## 4. What NOT to do

- Don't treat an unsigned checked-in `SEALS.sha256` as integrity (SLSA L1).
- Don't re-read the manifest's declared hashes as "verification" — verify the *signature over* it.
- Don't let the committing agent hold the seal-signing key — sign in CI against an OIDC identity.
- Don't rely on a single signature where the threat is the signer itself — use threshold/multi-sig.
- Don't force-overwrite a published seal tag (Git "MUST NOT" silently; destroys the trust-name).
- Don't treat branch protection/rulesets as cryptographic proof (privileged bypass can reseal).
- Don't disable cosign's claims check on the seal path.
- Don't omit a freshness/expiry signal (else indefinite-freeze/rollback is undetectable).
- Cite SLSA **v1.2** as current (v1.0 Retired).

## On Ethereum / on-chain anchoring (Peter's question)
On-chain anchoring (Ethereum smart contracts, EAS) and OpenTimestamps (Bitcoin/Ethereum) are
valid external anchors but are **not** the recommended first layer for a per-commit seal:
they add gas cost + ~block latency + key/contract ops for security a signed tag or Rekor
provides more cheaply. OpenTimestamps gives free permissionless public timestamping without a
contract; reserve full on-chain only if censorship-resistant, third-party, no-trusted-operator
verification is a hard requirement. (Detail in the companion on-chain-vs-translog research doc.)

## Sources
docs.sigstore.dev/logging/overview · docs.sigstore.dev/cosign/verifying/verify ·
github.com/in-toto/attestation · slsa.dev/spec/v1.0/levels · theupdateframework.io ·
git-scm.com/docs/git-tag · docs.github.com/.../about-rulesets · rfc-editor.org/rfc/rfc6962 ·
rfc-editor.org/rfc/rfc9162 · theupdateframework.github.io/specification/latest
