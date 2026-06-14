import os
from pathlib import Path

RFC_DIR = Path(os.getenv("RFC_DIR", "/rfcs/protocol/rfcs"))
REPO_ROOT = Path(os.getenv("RFC_DIR_ROOT", "/rfcs"))


def ingest_rfcs() -> dict[str, str]:
    result: dict[str, str] = {}
    if not RFC_DIR.exists():
        return result
    for path in sorted(RFC_DIR.glob("*.md")):
        try:
            result[path.stem] = path.read_text(encoding="utf-8")
        except OSError:
            pass
    vocab_path = REPO_ROOT / "docs/protocol/README.md"
    if vocab_path.exists():
        try:
            result["vocab-protocol"] = vocab_path.read_text(encoding="utf-8")
        except OSError:
            pass
    return result


def build_corpus_summary(rfc_texts: dict[str, str]) -> str:
    """Compact section-header listing for section_classifier."""
    parts = []
    for name, text in rfc_texts.items():
        headers = [l for l in text.split("\n") if l.startswith("#")][:25]
        parts.append(f"RFC {name}:\n" + "\n".join(headers))
    return "\n\n".join(parts)


def build_full_corpus(rfc_texts: dict[str, str]) -> str:
    """RFC 0004 in full; others excerpted to 150 lines to bound context."""
    parts = []
    for name, text in rfc_texts.items():
        if "0004" in name:
            parts.append(f"=== {name} (full) ===\n{text}")
        else:
            lines = text.split("\n")[:150]
            parts.append(f"=== {name} (excerpt) ===\n" + "\n".join(lines))
    return "\n\n".join(parts)


def render_finding(f: dict) -> str:
    return (
        f"[{f.get('severity', '?').upper()}] {f.get('specialist', '?')} specialist\n"
        f"Section: {f.get('section_ref', '?')} in {f.get('rfc_id', '?')}\n"
        f"Type: {f.get('finding_type', '?')}\n"
        f"Finding: {f.get('description', '?')}\n"
        f"Quote: {f.get('supporting_quote', '?')}"
    )


def render_verified_findings(findings: list[dict]) -> str:
    lines = []
    for f in findings:
        verdict = f.get("verdict", "not_verified")
        refutation = f.get("refutation_argument", "")
        lines.append(
            f"[{verdict.upper()}] [{f.get('severity', '?').upper()}] "
            f"{f.get('section_ref', '?')}: {f.get('description', '?')}"
            + (f"\n  Refutation: {refutation}" if refutation else "")
        )
    return "\n\n".join(lines)


def deduplicate_findings(findings: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    unique = []
    for f in findings:
        key = (
            f.get("rfc_id", ""),
            f.get("section_ref", ""),
            f.get("finding_type", ""),
            f.get("description", "")[:80],
        )
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique
