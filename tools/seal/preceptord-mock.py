#!/usr/bin/env python3
"""preceptord-mock.py — spike admission controller for votive seals (RFC 0007 Q5).

Usage:
    python3 preceptord-mock.py <provenance.json>

Reads a votive seal (provenance.json produced by sign-provenance.sh), validates
its structure, checks the cryptographic signature, and emits an admission
decision:

    ADMIT: <membrane> closure=<hash> epoch=<epoch>
    REFUSE: <reason>

Exit codes:
    0  ADMIT
    1  REFUSE

Spike behaviour (placeholder mode):
    If signature.placeholder == true the signature bytes are NOT verified
    (the HMAC key is ephemeral and not shipped in the seal). A warning is
    printed to stderr and admission proceeds if the structural checks pass.
    This is "spike mode" — suitable for exercising the end-to-end flow before
    the real ML-DSA-65 key infrastructure exists.

Real-signature verification:
    algorithm == "ml-dsa-65"        → verify with liboqs (import oqs)
    algorithm == "hmac-sha256-placeholder" without placeholder flag → REFUSE
      (a placeholder algorithm without the placeholder flag is malformed)

Closure allowlist (hardcoded for the spike):
    The deploy plane will eventually consult a preceptord policy store to
    map membrane names to admitted closure hashes. For the spike, the check
    is structural only: closure_hash must be a non-empty 64-char hex string
    and membrane must be non-empty. No preceptord policy store is wired yet.

What this answers (RFC 0007 open questions):
    Q5 (image-as-code):  This mock shows the full admit/refuse path over a
        signed votive seal, closing the "produce → sign → admit" loop on a
        single membrane (network/agent-egress is the spike target).
    Q1 (vsock boundary): The seal is checked at closure materialization time,
        NOT at wire time — supporting "the wire layer (RFC 0003 Litany) is
        still needed end-to-end; the seal alone does not replace it."
    Q2 (TPM binding):    Deferred — the mock does not verify a TPM PCR quote.

Python 3.11+ stdlib only (plus optional liboqs for ML-DSA verification).
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sys

# --------------------------------------------------------------------------- #
# Schema constants (mirror provenance-schema.json)
# --------------------------------------------------------------------------- #

_KIND = "votive-seal"
_VALID_ALGORITHMS = {"ml-dsa-65", "hmac-sha256-placeholder"}
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_FIELDS = {"kind", "version", "closure_hash", "topology_epoch",
                    "membrane", "signed_at", "signature"}
_REQUIRED_SIG_FIELDS = {"algorithm", "value"}

# Hardcoded spike allowlist — membrane name -> admission policy.
# For the spike: any well-formed (non-empty) closure_hash is permitted.
# In production this would be a preceptord policy query.
_SPIKE_MEMBRANE_ALLOWLIST = {
    # The primary spike target (agent-egress.vaked).
    "network/agent-egress",
    # Additional membranes recognised by the spike (for testing other paths).
    "filesystem/artifacts",
    "compute/worker",
}


# --------------------------------------------------------------------------- #
# Admission logic
# --------------------------------------------------------------------------- #

def _refuse(reason: str) -> None:
    print("REFUSE: %s" % reason)
    sys.exit(1)


def _warn(msg: str) -> None:
    print("WARNING: %s" % msg, file=sys.stderr)


def _admit(membrane: str, closure_hash: str, epoch: int) -> None:
    print("ADMIT: %s closure=%s epoch=%d" % (membrane, closure_hash, epoch))
    sys.exit(0)


def _canonical_payload_bytes(doc: dict) -> bytes:
    """Reconstruct the canonical signed payload: the provenance fields (no
    'signature', no '$schema') sorted and serialised to compact JSON.
    Must match sign-provenance.sh's Python signing step exactly."""
    payload = {k: v for k, v in doc.items()
               if k not in ("signature", "$schema")}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _verify_ml_dsa_65(payload_bytes: bytes, sig_b64: str, pk_b64: str) -> bool:
    """Verify an ML-DSA-65 (Dilithium3) signature via liboqs.
    Returns True on valid signature, False on failure.
    Raises ImportError if liboqs is not installed."""
    import oqs  # type: ignore

    signature  = base64.b64decode(sig_b64)
    public_key = base64.b64decode(pk_b64)

    with oqs.Signature("Dilithium3") as verifier:
        return verifier.verify(payload_bytes, signature, public_key)


def _load_seal(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        _refuse("file not found: %s" % path)
    except json.JSONDecodeError as e:
        _refuse("invalid JSON: %s" % e)


def admit(path: str) -> None:
    doc = _load_seal(path)

    # --- Structural checks ------------------------------------------------- #

    missing = _REQUIRED_FIELDS - doc.keys()
    if missing:
        _refuse("missing required fields: %s" % ", ".join(sorted(missing)))

    if doc.get("kind") != _KIND:
        _refuse("kind must be %r, got %r" % (_KIND, doc.get("kind")))

    closure_hash = doc.get("closure_hash", "")
    if not _HASH_RE.match(str(closure_hash)):
        _refuse("closure_hash must be a 64-char lowercase hex string, got %r"
                % closure_hash)

    membrane = str(doc.get("membrane", ""))
    if not membrane:
        _refuse("membrane must be a non-empty string")

    try:
        epoch = int(doc["topology_epoch"])
    except (TypeError, ValueError):
        _refuse("topology_epoch must be an integer")
    if epoch < 0:
        _refuse("topology_epoch must be >= 0")

    sig = doc.get("signature")
    if not isinstance(sig, dict):
        _refuse("signature must be an object")

    missing_sig = _REQUIRED_SIG_FIELDS - sig.keys()
    if missing_sig:
        _refuse("signature missing fields: %s" % ", ".join(sorted(missing_sig)))

    algorithm = sig.get("algorithm")
    if algorithm not in _VALID_ALGORITHMS:
        _refuse("unknown signature algorithm %r (expected one of: %s)"
                % (algorithm, ", ".join(sorted(_VALID_ALGORITHMS))))

    sig_value = sig.get("value", "")
    if not sig_value:
        _refuse("signature.value must be non-empty")

    try:
        base64.b64decode(sig_value, validate=True)
    except Exception:
        _refuse("signature.value is not valid base64")

    # --- Membrane allowlist check ------------------------------------------ #
    # Spike: check membrane is in the hardcoded allowlist.
    # Production: this would be a preceptord policy query against the topology
    # epoch and the declared Vaked membrane graph.
    if membrane not in _SPIKE_MEMBRANE_ALLOWLIST:
        _warn(
            "membrane %r not in spike allowlist; "
            "production would consult preceptord policy store" % membrane
        )
        # For the spike, proceed with a warning rather than refusing.
        # Uncomment the next line to enforce the allowlist strictly:
        # _refuse("membrane %r not in allowlist" % membrane)

    # --- Signature verification -------------------------------------------- #

    is_placeholder = sig.get("placeholder") is True

    if algorithm == "hmac-sha256-placeholder":
        if not is_placeholder:
            # A placeholder algorithm without placeholder=true is malformed.
            _refuse(
                "algorithm is 'hmac-sha256-placeholder' but signature.placeholder "
                "is not true — malformed seal; refusing"
            )
        # Spike mode: skip signature verification (HMAC key is ephemeral).
        _warn(
            "spike mode: signature.placeholder=true — HMAC-SHA256 signature bytes "
            "NOT verified (ephemeral key not shipped in seal). "
            "Production requires ML-DSA-65 (RFC 0007 §3)."
        )

    elif algorithm == "ml-dsa-65":
        if is_placeholder:
            _refuse(
                "algorithm is 'ml-dsa-65' but signature.placeholder=true — "
                "contradictory seal; refusing"
            )
        pk_b64 = sig.get("public_key")
        if not pk_b64:
            _refuse(
                "algorithm ml-dsa-65 requires signature.public_key "
                "(the Dilithium3 public key bytes, base64-encoded)"
            )
        payload_bytes = _canonical_payload_bytes(doc)
        try:
            valid = _verify_ml_dsa_65(payload_bytes, sig_value, pk_b64)
        except ImportError:
            _refuse(
                "liboqs not available — cannot verify ml-dsa-65 signature. "
                "Install: pip install liboqs-python (requires liboqs shared lib). "
                "See https://github.com/open-quantum-safe/liboqs-python"
            )
        if not valid:
            _refuse("ml-dsa-65 signature verification FAILED")

    # --- Admit ------------------------------------------------------------- #

    _admit(membrane, closure_hash, epoch)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python3 preceptord-mock.py <provenance.json>", file=sys.stderr)
        sys.exit(2)
    admit(sys.argv[1])


if __name__ == "__main__":
    main()
