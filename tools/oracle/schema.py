"""vaked-oracle finding record schema (see docs/oracle/v0.md)."""
from __future__ import annotations

FINDING_KIND = "oracle_finding"
FINDING_V = 1
FIDELITY_METHOD = "normalized-token-similarity"


def function_entry(*, name: str, addr: str, pseudo_c_sha: str, refined_c: str | None,
                   fidelity_score: float | None = None,
                   frida: dict | None = None, ebpf: dict | None = None) -> dict:
    """One analyzed function. Dynamic evidence is independently nullable."""
    return {
        "name": name,
        "addr": addr,
        "pseudo_c_sha": pseudo_c_sha,
        "refined_c": refined_c,
        "fidelity": {"score": fidelity_score, "method": FIDELITY_METHOD},
        "dynamic": {"frida": frida, "ebpf": ebpf},
    }


def build_finding(*, target: dict, decompiler: dict, functions: list[dict],
                  confidence: float, observed_effects: dict | None = None,
                  transition_xref: str | None = None) -> dict:
    """Assemble the finding payload (the ledger entry will add the chain fields)."""
    return {
        "kind": FINDING_KIND,
        "v": FINDING_V,
        "target": target,
        "decompiler": decompiler,
        "functions": functions,
        "observed_effects": observed_effects or {"writes": [], "deletes": []},
        "transition_xref": transition_xref,
        "confidence": confidence,
    }


def validate_finding(f: dict) -> None:
    """Raise ValueError if the finding is structurally invalid."""
    if f.get("kind") != FINDING_KIND:
        raise ValueError(f"bad kind: {f.get('kind')!r}")
    if f.get("v") != FINDING_V:
        raise ValueError(f"bad version: {f.get('v')!r}")
    for key in ("target", "decompiler", "functions", "observed_effects", "confidence"):
        if key not in f:
            raise ValueError(f"missing key: {key}")
    oe = f["observed_effects"]
    if set(oe) != {"writes", "deletes"}:
        raise ValueError("observed_effects must have exactly writes+deletes")
