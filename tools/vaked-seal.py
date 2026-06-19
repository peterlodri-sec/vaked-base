#!/usr/bin/env python3
"""vaked-seal — Vaked votive seal tool (RFC 0007 Q5 spike).

Produce and admit votive seals (provenance.json) for Vaked membranes.
Replaces tools/seal/sign-provenance.sh with a proper CLI.

Usage:
  vaked-seal sign <path-or-hash> <membrane> [epoch]
    Produce a signed votive seal. Writes provenance.json to stdout.
    Uses ML-DSA-65 (liboqs) or HMAC-SHA256 placeholder fallback.

  vaked-seal admit <provenance.json>
    Validate a seal's structure and signature. Returns ADMIT/REFUSE.

  vaked-seal verify <provenance.json>
    Same as admit but with verbose output (exit code signals result).

Examples:
  vaked-seal sign /nix/store/abc... network/agent-egress 2 > provenance.json
  vaked-seal admit provenance.json
  vaked-seal verify provenance.json && echo "seal holds"
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #

def cmd_sign(args) -> int:
    """Produce a signed votive seal."""
    closure = args.closure
    membrane = args.membrane
    epoch = args.epoch or 1

    # Compute closure hash (or use literal hex string)
    if re.match(r'^[0-9a-fA-F]{64}$', closure):
        closure_hash = closure.lower()
    else:
        path = Path(closure)
        if not path.exists():
            print(f"vaked-seal: path not found: {closure}", file=sys.stderr)
            return 1
        sha = hashlib.sha256()
        if path.is_file():
            sha.update(path.read_bytes())
        else:
            for p in sorted(path.rglob('*')):
                if p.is_file():
                    sha.update(p.read_bytes())
        closure_hash = sha.hexdigest()

    # Build canonical payload
    payload = {
        "vaked": {"schema": "votive-seal", "version": "1"},
        "membrane": membrane,
        "closure_hash": closure_hash,
        "topology_epoch": epoch,
        "generated_at": _utcnow(),
    }

    # Sign
    sig_alg, sig_bytes, pub_key, placeholder = _sign_payload(payload)

    # Assemble seal
    signature = {
        "algorithm": sig_alg,
        "value": base64.b64encode(sig_bytes).decode(),
        "public_key": base64.b64encode(pub_key).decode() if pub_key else None,
    }
    if placeholder:
        signature["placeholder"] = True

    seal = {**payload, "signature": signature}
    print(json.dumps(seal, indent=2, sort_keys=False, ensure_ascii=False))
    return 0


def cmd_admit(args) -> int:
    """Validate and admit a seal."""
    return _admit(args.seal_file, verbose=False)


def cmd_verify(args) -> int:
    """Validate a seal with verbose output."""
    return _admit(args.seal_file, verbose=True)


def _admit(path: str, verbose: bool = False) -> int:
    """Validate a seal file and return 0 (admit) or 1 (refuse)."""
    try:
        with open(path) as f:
            seal = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        _say(f"REFUSE: cannot read seal — {e}", verbose)
        return 1

    # Structural checks
    required = {"membrane", "closure_hash", "topology_epoch", "signature"}
    missing = required - set(seal.keys())
    if missing:
        _say(f"REFUSE: missing fields: {', '.join(sorted(missing))}", verbose)
        return 1

    sig = seal["signature"]
    for field in ("algorithm", "value"):
        if field not in sig:
            _say(f"REFUSE: signature missing '{field}'", verbose)
            return 1

    # Verify signature
    payload = {k: v for k, v in seal.items() if k != "signature"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    alg = sig["algorithm"]
    sig_data = base64.b64decode(sig["value"])
    pub_key = base64.b64decode(sig.get("public_key", "")) if sig.get("public_key") else None

    if alg == "ml-dsa-65":
        try:
            import oqs
            verifier = oqs.Signature("Dilithium3")
            result = verifier.verify(canonical, sig_data, pub_key)
            if not result:
                _say("REFUSE: ML-DSA-65 signature invalid", verbose)
                return 1
            _say(f"ADMIT: {seal['membrane']} closure={seal['closure_hash']} epoch={seal['topology_epoch']}", verbose)
            return 0
        except ImportError:
            _say("REFUSE: liboqs not installed for ML-DSA-65 verification", verbose)
            return 1
    elif alg == "hmac-sha256-placeholder":
        if sig.get("placeholder"):
            _say(f"ADMIT (placeholder): {seal['membrane']} — WARNING: HMAC key not available for re-verification", verbose)
            return 0
        _say("REFUSE: hmac-sha256-placeholder without placeholder flag", verbose)
        return 1
    else:
        _say(f"REFUSE: unknown algorithm '{alg}'", verbose)
        return 1


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _sign_payload(payload: dict) -> tuple:
    """Return (algorithm, signature_bytes, public_key_or_None, is_placeholder)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    # Try ML-DSA-65 via liboqs
    try:
        import oqs
        signer = oqs.Signature("Dilithium3")
        pub_key = signer.generate_keypair()
        sig = signer.sign(canonical)
        return ("ml-dsa-65", sig, pub_key, False)
    except ImportError:
        pass

    # Fallback: HMAC-SHA256 placeholder
    key = secrets.token_bytes(32)
    sig = hmac.new(key, canonical, hashlib.sha256).digest()
    print("vaked-seal: WARNING: HMAC-SHA256 placeholder — NOT post-quantum secure", file=sys.stderr)
    return ("hmac-sha256-placeholder", sig, None, True)


def _say(msg: str, verbose: bool) -> None:
    if verbose:
        print(msg)
    else:
        print("ADMIT" if msg.startswith("ADMIT") else "REFUSE")


def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    import re as _re
    global re
    re = _re

    ap = argparse.ArgumentParser(
        prog="vaked-seal",
        description="Vaked votive seal tool — sign, admit, verify (RFC 0007)",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sig = sub.add_parser("sign", help="produce a signed votive seal")
    sig.add_argument("closure", help="filesystem path or 64-char hex hash")
    sig.add_argument("membrane", help="membrane name (e.g. network/agent-egress)")
    sig.add_argument("epoch", nargs="?", type=int, default=None,
                     help="topology epoch (default: 1)")

    adm = sub.add_parser("admit", help="validate a seal, return ADMIT/REFUSE")
    adm.add_argument("seal_file", help="path to provenance.json")

    ver = sub.add_parser("verify", help="validate a seal with verbose output")
    ver.add_argument("seal_file", help="path to provenance.json")

    args = ap.parse_args(argv)

    dispatch = {
        "sign": cmd_sign,
        "admit": cmd_admit,
        "verify": cmd_verify,
    }
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
