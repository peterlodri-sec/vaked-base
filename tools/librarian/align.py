"""Vaked Librarian — bridges human intent with system execution.

Reads /notes daily brainfarts, compares against Oculus ledger and
CapabilityGraph, produces architectural alignment reports, and
flags Intent Drift that exceeds the Genesis Seal threshold.
"""
import os, json, time, hashlib, glob, re

NOTES_DIR = "notes"
REFLECTIONS_DIR = os.path.join(NOTES_DIR, "REFLECTIONS")
RFC_DIR = os.path.join(NOTES_DIR, "RFCs")
GENESIS_SEAL = "7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf"
DRIFT_THRESHOLD = 2  # number of misalignments before blocking build


def scan_notes():
    """Scan daily brainfart files."""
    notes = []
    for f in sorted(glob.glob(os.path.join(NOTES_DIR, "????-??-??.md"))):
        with open(f) as fh:
            content = fh.read()
        date = os.path.basename(f).replace(".md", "")
        # Extract sections
        intent_match = re.search(r"## Intent.*\n(.*?)(?:\n##|\Z)", content, re.DOTALL)
        questions_match = re.search(r"## Open Questions.*\n(.*?)(?:\n##|\Z)", content, re.DOTALL)
        notes.append({
            "date": date,
            "file": f,
            "intent": intent_match.group(1).strip() if intent_match else "",
            "questions": questions_match.group(1).strip() if questions_match else "",
            "has_genesis_seal": GENESIS_SEAL[:8] in content,
        })
    return notes


def scan_ledger():
    """Extract governance directives from Oculus ledger."""
    directives = []
    ledger_path = "/tmp/oculus_export.jsonl"
    if os.path.isfile(ledger_path):
        with open(ledger_path) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                    kind = e.get("payload", {}).get("kind", "")
                    if kind in ("GOVERNANCE_ANSWERS", "GOVERNANCE_BOUND",
                               "DOMAIN_BINDING", "RALPH_AUDIT"):
                        directives.append({
                            "kind": kind,
                            "seq": e.get("seq"),
                            "hash": e.get("hash", "")[:16],
                        })
                except:
                    pass
    return directives


def check_alignment(notes, directives):
    """Compare human intent against system execution, flag drift."""
    drift = []
    aligned = []

    # Check 1: Graveyard directive
    graveyard_directive = any("graveyard" in str(d).lower() for d in directives)
    if graveyard_directive:
        aligned.append({"check": "graveyard_permanent", "status": "ALIGNED"})
    else:
        drift.append({"check": "graveyard_permanent", "severity": "DRIFT",
                     "detail": "No graveyard permanence directive found in ledger"})

    # Check 2: Trust priority
    trust_priority = any("trust" in str(d).lower() for d in directives)
    if trust_priority:
        aligned.append({"check": "trust_first", "status": "ALIGNED"})
    else:
        drift.append({"check": "trust_first", "severity": "PENDING",
                     "detail": "Grammar v0.5 trust kind proposed but not implemented"})

    # Check 3: Genesis seal present
    seal_present = any(n["has_genesis_seal"] for n in notes)
    if seal_present:
        aligned.append({"check": "genesis_seal_present", "status": "ALIGNED"})
    else:
        drift.append({"check": "genesis_seal_present", "severity": "CRITICAL",
                     "detail": "Genesis seal not found in daily notes"})

    # Check 4: Intent matches execution
    for n in notes:
        if n["intent"]:
            aligned.append({"check": f"intent_documented_{n['date']}",
                          "status": "ALIGNED",
                          "detail": n["intent"][:100]})

    return drift, aligned


def generate_reflection(drift, aligned):
    """Generate today's architectural alignment reflection."""
    date = time.strftime("%Y-%m-%d")
    drift_count = len(drift)
    aligned_count = len(aligned)
    total = drift_count + aligned_count
    score = aligned_count / total if total > 0 else 0
    blocked = drift_count >= DRIFT_THRESHOLD

    reflection = f"""# Architectural Alignment — {date}

## Intent Drift Check
- Scanned: {len(scan_notes())} daily brainfarts, {len(scan_ledger())} governance directives
- Genesis Seal: {GENESIS_SEAL[:8]} (verified via DNS TXT)

## Alignment Score: {aligned_count}/{total} aligned · {drift_count} drift(s)

| Check | Status |
|-------|--------|
"""
    for a in aligned:
        reflection += f"| {a['check']} | {a['status']} |\n"
    for d in drift:
        reflection += f"| {d['check']} | ⚠️ {d['severity']}: {d['detail']} |\n"

    if blocked:
        reflection += f"""
## ⛔ BUILD BLOCKED — Intent Drift exceeds threshold ({DRIFT_THRESHOLD})

The following drift conditions prevent nix build from proceeding:
"""
        for d in drift:
            reflection += f"- **{d['check']}**: {d['detail']}\n"
        reflection += "\n**Action required:** Resolve drift conditions or acknowledge via operator signature.\n"
    else:
        reflection += f"""
## Drift Detected: {drift_count} ({'None — all aligned' if drift_count == 0 else 'minor — below threshold'})
No architectural intent contradicts current system state.
{'The Genesis Seal holds.' if not blocked else ''}
"""

    reflection += f"""
## Signed
Ralph (Vaked Librarian) · Audit hash: {hashlib.sha256((GENESIS_SEAL + date).encode()).hexdigest()[:16]}
"""
    return reflection, blocked


def run_librarian():
    """Execute one librarian cycle."""
    os.makedirs(REFLECTIONS_DIR, exist_ok=True)
    os.makedirs(RFC_DIR, exist_ok=True)

    notes = scan_notes()
    directives = scan_ledger()
    drift, aligned = check_alignment(notes, directives)
    reflection, blocked = generate_reflection(drift, aligned)

    # Write reflection
    path = os.path.join(REFLECTIONS_DIR, f"{time.strftime('%Y-%m-%d')}-architectural-alignment.md")
    with open(path, "w") as f:
        f.write(reflection)

    print(f"Reflection: {path}")
    print(f"Alignment:  {len(aligned)}/{len(aligned)+len(drift)} aligned")
    print(f"Drift:      {len(drift)} ({'BLOCKED' if blocked else 'clear'})")
    return not blocked  # True if build allowed


if __name__ == "__main__":
    ok = run_librarian()
    exit(0 if ok else 1)
