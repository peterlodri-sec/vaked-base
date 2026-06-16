"""Live CTF challenge catalog. Flags + per-challenge hints; box-backed challenges name a
vulnbox module, self-contained puzzles carry a derived `artifact` (shown to the player).

Artifacts are derived FROM the flag at import time so the puzzle and its answer can never
drift. Flag checking is constant-time (`hmac.compare_digest`)."""
from __future__ import annotations

import base64
import codecs
import hmac

_XOR_KEY = 0x42


def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def _rot13(s: str) -> str:
    return codecs.encode(s, "rot13")


def _xor_hex(s: str) -> str:
    return bytes(b ^ _XOR_KEY for b in s.encode()).hex()


def challenge(cid, category, points, flag, hint, box=None, artifact=None) -> dict:
    return {"id": cid, "category": category, "points": int(points), "flag": flag,
            "hint": hint, "box": box, "artifact": artifact}


# Box-backed challenges solve a real vulnbox target (launched on loopback); self-contained
# puzzles are computed locally by the player from the shown `artifact`.
_FLAGS = {
    "web-traversal": "FLAG{tr4v3rs4l_b3y0nd_www}",
    "web-idor": "FLAG{1d0r_4dm1n_n0t3_1337}",
    "crypto-caesar": "FLAG{caesar_rot_thirteen}",
    "misc-base64": "FLAG{base_sixty_four_unwrap}",
    "rev-xor": "FLAG{x0r_single_byte_key}",
}

CHALLENGES = [
    challenge("web-traversal", "web", 200, _FLAGS["web-traversal"],
              "the file= param trusts whatever path you hand it. what's one level up from www/?",
              box={"module": "box_traversal", "solve": "capture_traversal", "path": "vulnbox-trav-root"}),
    challenge("web-idor", "web", 150, _FLAGS["web-idor"],
              "/notes hides the admin id — but ids themselves aren't access-controlled.",
              box={"module": "box_idor", "solve": "capture_idor"}),
    challenge("crypto-caesar", "crypto", 100, _FLAGS["crypto-caesar"],
              "Caesar would approve. shift the letters by 13.",
              artifact=_rot13(_FLAGS["crypto-caesar"])),
    challenge("misc-base64", "misc", 75, _FLAGS["misc-base64"],
              "that trailing = is a giveaway. decode it.",
              artifact=_b64(_FLAGS["misc-base64"])),
    challenge("rev-xor", "rev", 125, _FLAGS["rev-xor"],
              "hex bytes XORed with one secret byte. brute the 256 keys; the flag is printable.",
              artifact=_xor_hex(_FLAGS["rev-xor"])),
]

BY_ID = {c["id"]: c for c in CHALLENGES}
FIRST_BLOOD_BONUS = 50


def by_id() -> dict:
    return BY_ID


def check_flag(cid: str, submitted: str) -> bool:
    """Constant-time check of a submitted flag against the challenge's flag."""
    c = BY_ID.get(cid)
    if not c or submitted is None:
        return False
    return hmac.compare_digest(c["flag"], submitted.strip())
