"""optitroncore — pure-stdlib logic for vaked-optitron (no network, no IO side effects).

Houses the hash-chained ledger primitives (mirrored from ralphcore so the tool stays
self-contained per the fleet archetype), the strict-gate scoring, the crawl/verify/
bench/adjudicate prompt builders + JSON schemas, and the source-independence and
bench-output parsers. Everything here is deterministic and unit-testable offline.
"""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Hash-chained ledger primitives (mirrored from tools/ralph/ralphcore.py — kept
# local so optitron has no cross-tool import; the chain is the "immutable" leg:
# the findings ledger is tamper-evident and replayable).
# ---------------------------------------------------------------------------

GENESIS_HASH = "0" * 64


def canon(payload: dict) -> str:
    """Canonical JSON (sorted keys, compact) — the exact bytes that get hashed."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def chain_hash(prev_hex: str, payload: dict) -> str:
    """sha256(prev_hash || canonical(payload)) — the link function."""
    return hashlib.sha256((prev_hex + canon(payload)).encode("utf-8")).hexdigest()


def make_entry(prev_hex: str, seq: int, payload: dict) -> dict:
    """One hash-chained log entry. `prev_hex` is GENESIS_HASH for seq 0."""
    return {"seq": seq, "prev": prev_hex, "payload": payload,
            "hash": chain_hash(prev_hex, payload)}


def verify_chain(entries: list[dict]) -> bool:
    """True iff entries form a contiguous, untampered chain from genesis."""
    prev = GENESIS_HASH
    for i, e in enumerate(entries):
        if e.get("seq") != i or e.get("prev") != prev:
            return False
        if e.get("hash") != chain_hash(prev, e.get("payload", {})):
            return False
        prev = e["hash"]
    return True


def longest_valid_prefix(entries: list[dict]) -> list[dict]:
    """Longest untampered chain prefix — the boot-recovery counterpart (torn tail)."""
    out: list[dict] = []
    prev = GENESIS_HASH
    for i, e in enumerate(entries):
        if (e.get("seq") != i or e.get("prev") != prev
                or e.get("hash") != chain_hash(prev, e.get("payload", {}))):
            break
        out.append(e)
        prev = e["hash"]
    return out


# ---------------------------------------------------------------------------
# Scope — optitron only hunts in these domains. A candidate outside scope is
# discarded before any verification spend.
# ---------------------------------------------------------------------------

SCOPE = ("compiler", "allocator", "zig", "rust", "vaked")


def in_scope(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in SCOPE)


# ---------------------------------------------------------------------------
# Strict-gate JSON schemas (OpenRouter `response_format: json_schema`). Every
# field required so a lenient provider can't omit one and slip past the gate.
# ---------------------------------------------------------------------------

def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "additionalProperties": False,
            "required": required, "properties": props}


def schema(name: str, root: dict) -> dict:
    return {"type": "json_schema",
            "json_schema": {"name": name, "strict": True, "schema": root}}


CRAWL_SCHEMA = schema("optitron_candidates", _obj({
    "candidates": {"type": "array", "items": _obj({
        "title": {"type": "string"},
        "area": {"type": "string", "enum": list(SCOPE)},
        "mechanism": {"type": "string"},          # how/why it is faster, concretely
        "claim": {"type": "string"},              # the measurable claim
        "sources": {"type": "array", "items": _obj({
            "url": {"type": "string"},
            "kind": {"type": "string"},           # paper | release-note | upstream-rfc | benchmark
            "org": {"type": "string"},            # publishing org/author (for independence)
            "quote": {"type": "string"},          # exact sentence supporting the claim
        }, ["url", "kind", "org", "quote"])},
        "signature": {"type": "string"},          # grep-able marker if already-applied in a repo
    }, ["title", "area", "mechanism", "claim", "sources", "signature"])},
}, ["candidates"]))


VERIFY_SCHEMA = schema("optitron_verify", _obj({
    "independent": {"type": "boolean"},           # ≥2 sources, distinct origins, no citation-chain
    "independent_count": {"type": "integer"},
    "rationale": {"type": "string"},
    "claim_supported": {"type": "boolean"},       # the exact quotes back the claim
    "caveats": {"type": "string"},
}, ["independent", "independent_count", "rationale", "claim_supported", "caveats"]))


# A single self-contained program that prints exactly:  OPTITRON_BENCH baseline=<ns> optimized=<ns>
BENCH_SCHEMA = schema("optitron_bench", _obj({
    "lang": {"type": "string", "enum": ["rust", "c"]},
    "source": {"type": "string"},                 # full program text
    "notes": {"type": "string"},
}, ["lang", "source", "notes"]))


ADJUDICATE_SCHEMA = schema("optitron_adjudicate", _obj({
    "confidence": {"type": "number"},             # 0..1 — internal certainty it's real + novel
    "novel": {"type": "boolean"},
    "hallucination_risk": {"type": "string", "enum": ["low", "medium", "high"]},
    "verdict": {"type": "string"},                # one-line adjudication
}, ["confidence", "novel", "hallucination_risk", "verdict"]))


# ---------------------------------------------------------------------------
# Prompt builders. The crawl prompt embeds the SKILL.md (the declarative spec)
# as the system message, so the harness is a faithful projection of the skill.
# ---------------------------------------------------------------------------

def build_crawl_messages(skill: str, purpose: str, sources_hint: str,
                         prior_titles: list[str]) -> list[dict]:
    prior = "\n".join(f"- {t}" for t in prior_titles[-40:]) or "(none yet)"
    user = (
        f"{purpose}\n\nCRAWL these source families for RECENT, in-scope candidate "
        f"optimizations (compiler | allocator | zig | rust | vaked):\n{sources_hint}\n\n"
        "For each candidate give the concrete mechanism, the measurable claim, and "
        ">=2 sources with EXACT supporting quotes + the publishing org (for an "
        "independence check). Provide a grep-able `signature` that would appear in a "
        "codebase that ALREADY applies it (used to reject non-novel finds).\n\n"
        "Do NOT invent sources or quotes. If you cannot find a real, recent, "
        "in-scope optimization with real sources, return an EMPTY candidates array.\n\n"
        f"Already-found (do not repeat):\n{prior}"
    )
    return [{"role": "system", "content": skill}, {"role": "user", "content": user}]


def build_verify_messages(skill: str, candidate: dict) -> list[dict]:
    user = (
        "Adversarially CROSS-CHECK this candidate. Decide `independent`: are there "
        ">=2 authoritative sources from DISTINCT origins (different orgs/domains) that "
        "each independently support the claim — NOT a citation chain where one merely "
        "cites another? Count them. Confirm the exact quotes actually support the "
        "claim. Be skeptical; a plausible-sounding but unsourced mechanism is a "
        "hallucination.\n\nCANDIDATE:\n" + json.dumps(candidate, indent=2)
    )
    return [{"role": "system", "content": skill}, {"role": "user", "content": user}]


def build_bench_messages(skill: str, candidate: dict) -> list[dict]:
    user = (
        "Write ONE self-contained micro-benchmark that demonstrates this optimization "
        "versus its baseline. Constraints: single file; no external crates/deps; "
        "deterministic; runs in < 20s; uses a monotonic clock. It MUST print exactly "
        "one line to stdout:\n    OPTITRON_BENCH baseline=<ns> optimized=<ns>\n"
        "where the two values are nanoseconds for the baseline vs optimized variant of "
        "the SAME workload. No other stdout. lang is `rust` (compiled with `rustc -O`) "
        "or `c` (compiled with `cc -O2`).\n\nCANDIDATE:\n" + json.dumps(candidate, indent=2)
    )
    return [{"role": "system", "content": skill}, {"role": "user", "content": user}]


def build_adjudicate_messages(skill: str, candidate: dict, verify: dict,
                              bench: dict) -> list[dict]:
    user = (
        "Final adjudication. Given the candidate, the cross-check verdict, and the "
        "MEASURED benchmark result, output your internal certainty (`confidence` 0..1) "
        "that this is a REAL, NOVEL optimization — not a hallucination. Be conservative: "
        "reserve confidence >= 0.8 for findings with independent sources AND a real "
        "measured improvement. Anything speculative scores low.\n\n"
        f"CANDIDATE:\n{json.dumps(candidate, indent=2)}\n\n"
        f"CROSS-CHECK:\n{json.dumps(verify, indent=2)}\n\n"
        f"BENCH:\n{json.dumps(bench, indent=2)}"
    )
    return [{"role": "system", "content": skill}, {"role": "user", "content": user}]


# ---------------------------------------------------------------------------
# Deterministic checks
# ---------------------------------------------------------------------------

def _registrable_domain(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def sources_independent(sources: list[dict], min_sources: int = 2) -> bool:
    """True iff >= min_sources from DISTINCT registrable domains AND distinct orgs.
    Catches citation-chains/self-references that share a domain or author."""
    domains = {d for s in sources if (d := _registrable_domain(s.get("url", "")))}
    orgs = {o.strip().lower() for s in sources if (o := s.get("org", "").strip())}
    return len(domains) >= min_sources and len(orgs) >= min_sources


_BENCH_RE = re.compile(r"OPTITRON_BENCH\s+baseline=([0-9.]+)\s+optimized=([0-9.]+)")


def parse_bench_output(stdout: str) -> "dict | None":
    """Parse the bench sentinel line → {baseline, optimized, delta} (delta = relative
    improvement). None if absent/malformed/non-positive."""
    m = _BENCH_RE.search(stdout or "")
    if not m:
        return None
    try:
        base, opt = float(m.group(1)), float(m.group(2))
    except ValueError:
        return None
    if base <= 0 or opt < 0:
        return None
    return {"baseline_ns": base, "optimized_ns": opt, "delta": (base - opt) / base}


def passes_gate(*, verify: dict, bench: "dict | None", adjudication: dict,
                min_sources: int, min_confidence: float, min_delta: float) -> "tuple[bool, str]":
    """The strict gate. Returns (passed, reason-if-rejected)."""
    if not verify.get("independent") or verify.get("independent_count", 0) < min_sources:
        return False, "insufficient-independent-sources"
    if not verify.get("claim_supported"):
        return False, "claim-not-supported"
    if not bench or bench.get("delta", 0.0) < min_delta:
        return False, "benchmark-missing-or-below-threshold"
    if not adjudication.get("novel"):
        return False, "not-novel"
    if adjudication.get("hallucination_risk") == "high":
        return False, "high-hallucination-risk"
    if adjudication.get("confidence", 0.0) < min_confidence:
        return False, "below-confidence-threshold"
    return True, ""
