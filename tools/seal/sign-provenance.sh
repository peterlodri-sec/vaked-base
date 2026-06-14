#!/usr/bin/env bash
# sign-provenance.sh — produce a votive seal (provenance.json) for a Vaked membrane.
#
# Usage:
#   ./sign-provenance.sh <closure-path-or-hash> <membrane-name> [topology-epoch]
#
# Arguments:
#   closure-path-or-hash  Either:
#                           - A filesystem path (directory or file) — closure_hash is
#                             computed with sha256sum / shasum over the path.
#                           - A 64-character hex string — used directly as closure_hash.
#   membrane-name         The declared Vaked membrane in 'kind/name' notation,
#                         e.g. 'network/agent-egress'.
#   topology-epoch        Optional. Integer topology epoch (default: 1).
#
# Output:
#   Signed provenance.json written to stdout. Redirect to a file:
#     ./sign-provenance.sh /nix/store/abc... network/agent-egress 2 > provenance.json
#
# Signature strategy (runtime detection):
#   1. If Python3 is available and 'import oqs' succeeds → sign with ML-DSA-65
#      (FIPS 204 / CRYSTALS-Dilithium3) via liboqs Python bindings.
#   2. If Python3 is not available or liboqs is missing → fall back to
#      HMAC-SHA256 with a randomly generated ephemeral key.
#      NOTE: HMAC-SHA256 is NOT post-quantum and NOT suitable for production.
#      The seal will contain "placeholder": true in the signature object.
#      Real implementation needs: liboqs (https://github.com/open-quantum-safe/liboqs)
#      or the Zig ML-DSA-65 implementation planned in RFC 0007 §6.
#
# Canonical payload:
#   The bytes signed are: the JSON document with the 'signature' key removed,
#   serialized with sorted keys and no extra whitespace (RFC 0007 §5.2).
#
# Spike limitations (RFC 0007 Q5):
#   - No TPM measurement binding (Q2 deferred).
#   - No vsock-layer integration (Q1 deferred — seal is at closure materialization
#     time, before the wire layer).
#   - The HMAC key is ephemeral; the seal cannot be re-verified without it
#     (preceptord-mock.py handles placeholder mode separately).

set -euo pipefail

# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #

if [[ $# -lt 2 ]]; then
    echo "usage: $0 <closure-path-or-hash> <membrane-name> [topology-epoch]" >&2
    exit 1
fi

CLOSURE_INPUT="$1"
MEMBRANE_NAME="$2"
TOPOLOGY_EPOCH="${3:-1}"

# --------------------------------------------------------------------------- #
# Compute closure_hash
# --------------------------------------------------------------------------- #

# If CLOSURE_INPUT looks like a 64-char hex string, use it directly.
if [[ "$CLOSURE_INPUT" =~ ^[0-9a-f]{64}$ ]]; then
    CLOSURE_HASH="$CLOSURE_INPUT"
elif [[ -e "$CLOSURE_INPUT" ]]; then
    # Hash the path: for a directory, hash the sorted file tree (deterministic).
    # For a regular file, hash directly.
    if command -v sha256sum >/dev/null 2>&1; then
        HASH_CMD="sha256sum"
        HASH_EXTRACT="{print \$1}"
    elif command -v shasum >/dev/null 2>&1; then
        HASH_CMD="shasum -a 256"
        HASH_EXTRACT="{print \$1}"
    else
        echo "error: neither sha256sum nor shasum found; install one or pass a hash directly" >&2
        exit 1
    fi

    if [[ -d "$CLOSURE_INPUT" ]]; then
        # Deterministic directory hash: hash each file (sorted path), then hash
        # the concatenated "<sha256>  <relpath>" lines. Mirrors 'nix path-info --hash'.
        CLOSURE_HASH=$(
            find "$CLOSURE_INPUT" -type f | sort |
            while IFS= read -r f; do
                $HASH_CMD "$f" | awk "$HASH_EXTRACT" | tr -d '\n'
                echo "  ${f#"$CLOSURE_INPUT/"}"
            done | $HASH_CMD | awk "$HASH_EXTRACT"
        )
    else
        CLOSURE_HASH=$($HASH_CMD "$CLOSURE_INPUT" | awk "$HASH_EXTRACT")
    fi
else
    echo "error: '$CLOSURE_INPUT' is not a path and not a 64-char hex hash" >&2
    exit 1
fi

# Validate hash looks right.
if [[ ! "$CLOSURE_HASH" =~ ^[0-9a-f]{64}$ ]]; then
    echo "error: computed closure_hash '$CLOSURE_HASH' is not a 64-char hex string" >&2
    exit 1
fi

# --------------------------------------------------------------------------- #
# Timestamp
# --------------------------------------------------------------------------- #

if command -v date >/dev/null 2>&1; then
    SIGNED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ")
else
    SIGNED_AT="1970-01-01T00:00:00Z"
fi

# --------------------------------------------------------------------------- #
# Produce the canonical payload JSON (no 'signature' key) and sign it.
# --------------------------------------------------------------------------- #
#
# The canonical payload is the provenance document with sorted keys and no
# extra whitespace, minus the 'signature' field. This is what gets signed.
# Python3 is required for the signing step (either path: oqs or hmac).

if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 is required for signing (for hmac-sha256 fallback at minimum)" >&2
    exit 1
fi

# Determine whether ML-DSA-65 (liboqs) is available.
ML_DSA_AVAILABLE=false
if python3 -c "import oqs" 2>/dev/null; then
    ML_DSA_AVAILABLE=true
fi

# Delegate sign + JSON assembly to Python for reliable base64 and JSON handling.
python3 - "$CLOSURE_HASH" "$MEMBRANE_NAME" "$TOPOLOGY_EPOCH" "$SIGNED_AT" "$ML_DSA_AVAILABLE" <<'PYEOF'
import sys
import json
import hashlib
import hmac
import base64
import os
import secrets

closure_hash = sys.argv[1]
membrane     = sys.argv[2]
epoch        = int(sys.argv[3])
signed_at    = sys.argv[4]
ml_dsa_avail = sys.argv[5] == "true"

# The canonical payload: all required provenance fields, NO 'signature' key.
# Keys sorted per RFC 0007 §5.2 canonical-JSON rule.
payload = {
    "kind":            "votive-seal",
    "version":         "1",
    "closure_hash":    closure_hash,
    "topology_epoch":  epoch,
    "membrane":        membrane,
    "signed_at":       signed_at,
}
canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False).encode("utf-8")

if ml_dsa_avail:
    # ---------- ML-DSA-65 path (liboqs Python bindings) ----------
    # ML-DSA-65 = FIPS 204 / CRYSTALS-Dilithium3 (security level 3, 192-bit
    # classical / post-quantum secure). The key pair is ephemeral for the spike;
    # a real deployment would use a hardware-backed key managed by the PKI.
    import oqs  # type: ignore

    with oqs.Signature("Dilithium3") as signer:
        public_key = signer.generate_keypair()
        signature  = signer.sign(canonical_payload)

    sig_b64 = base64.b64encode(signature).decode("ascii")
    pk_b64  = base64.b64encode(public_key).decode("ascii")

    seal = {
        **payload,
        "$schema": "http://json-schema.org/draft-07/schema#",
        "signature": {
            "algorithm":  "ml-dsa-65",
            "value":      sig_b64,
            "public_key": pk_b64,
        },
    }

else:
    # ---------- HMAC-SHA256 placeholder path ----------
    #
    # NOTE: This is NOT ML-DSA and is NOT post-quantum secure.
    # It is a spike-only placeholder so the end-to-end flow (sign → admit)
    # can be exercised before liboqs or the Zig ML-DSA-65 implementation is
    # available. The 'placeholder: true' field signals this to preceptord-mock.py
    # and to any downstream consumer.
    #
    # Real implementation needs:
    #   - liboqs Python: pip install liboqs-python
    #     (requires liboqs shared library: https://github.com/open-quantum-safe/liboqs)
    #   - OR: Zig ML-DSA-65 implementation wired into vakedc lower (RFC 0007 §6)
    #
    # Key: 32 bytes of OS randomness (ephemeral; not persisted). In production
    # the ML-DSA signing key is managed by the PKI and never written to disk
    # as raw bytes.
    key       = secrets.token_bytes(32)
    sig_bytes = hmac.new(key, canonical_payload, hashlib.sha256).digest()
    sig_b64   = base64.b64encode(sig_bytes).decode("ascii")

    seal = {
        **payload,
        "$schema": "http://json-schema.org/draft-07/schema#",
        "signature": {
            "algorithm":  "hmac-sha256-placeholder",
            "value":      sig_b64,
            "placeholder": True,
            # public_key is intentionally omitted: the HMAC key is symmetric and
            # ephemeral; it is NOT shipped in the seal. preceptord-mock.py
            # recognises placeholder=true and proceeds in spike mode without
            # re-verification of the signature bytes.
        },
    }

print(json.dumps(seal, sort_keys=True, indent=2, ensure_ascii=False))
PYEOF
