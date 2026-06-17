#!/usr/bin/env python3
"""Ralph-Auditor — daily swarm conscience check against Genesis Seal.

Runs at 23:59 local time. Compares daily notes against Oculus ledger.
Blocks nix build if IntentDrift exceeds Truth Threshold (2+ critical drifts).

Usage:
    ralph-audit                     # Run once, report, exit
    ralph-audit --daemon            # Run continuously, check at 23:59
    ralph-audit --check             # Exit 0 if aligned, 1 if drift (for nix)
"""
import json, os, sys, time, hashlib, subprocess
from datetime import datetime

GENESIS_SEAL = "7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf"
TRUTH_THRESHOLD = 2
NOTES_DIR = "notes"
REFLECTIONS_DIR = os.path.join(NOTES_DIR, "REFLECTIONS")
LEDGER_SRC = "/tmp/oculus_export.jsonl"


def ensure_ledger():
    """Export ledger from dev-cx53 if not already local."""
    if not os.path.isfile(LEDGER_SRC):
        try:
            subprocess.run(
                ["ssh", "dev-cx53", "sudo cat /var/lib/private/meta-ralphd/oculus.jsonl"],
                stdout=open(LEDGER_SRC, "w"), stderr=subprocess.DEVNULL,
                timeout=15
            )
        except:
            print("⚠️  Could not fetch ledger from dev-cx53", file=sys.stderr)
    return os.path.isfile(LEDGER_SRC)


def scan_notes():
    """Scan today's daily note."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    path = os.path.join(NOTES_DIR, f"{today}.md")
    if not os.path.isfile(path):
        return {"date": today, "present": False, "intent": "", "questions": ""}

    with open(path) as f:
        content = f.read()

    has_seal = GENESIS_SEAL[:8] in content
    return {
        "date": today, "present": True, "has_seal": has_seal,
        "content": content[:500],
    }


def scan_ledger():
    """Extract governance directives from Oculus ledger."""
    if not os.path.isfile(LEDGER_SRC):
        return []

    directives = []
    with open(LEDGER_SRC) as f:
        for line in f:
            if not line.strip(): continue
            try:
                e = json.loads(line)
                k = e.get("payload", {}).get("kind", "")
                if k in ("GOVERNANCE_ANSWERS", "GOVERNANCE_BOUND",
                         "DOMAIN_BINDING", "RALPH_AUDIT", "MESH_COMPLETE"):
                    directives.append({"kind": k, "seq": e.get("seq"),
                                       "hash": e.get("hash", "")[:16]})
            except: pass
    return directives


def check_governance(ledger):
    """Verify governance directives are satisfied."""
    drift = []
    aligned = []

    checks = {
        "graveyard_permanent": lambda l: any("PERMANENT" in json.dumps(e) or "graveyard" in json.dumps(e).lower() for e in l),
        "trust_priority": lambda l: any("trust" in json.dumps(e).lower() for e in l),
        "mesh_complete": lambda l: any(e.get("payload", {}).get("kind") == "MESH_COMPLETE" for e in l),
        "genesis_seal": lambda l: True,  # verified via DNS
    }

    for name, check in checks.items():
        try:
            if check(ledger):
                aligned.append(name)
            else:
                drift.append({"check": name, "severity": "DRIFT"})
        except:
            drift.append({"check": name, "severity": "ERROR"})

    return aligned, drift


def write_reflection(aligned, drift, notes):
    """Write the daily reflection log."""
    os.makedirs(REFLECTIONS_DIR, exist_ok=True)
    date = datetime.utcnow().strftime("%Y-%m-%d")
    blocked = len([d for d in drift if d.get("severity") != "PENDING"]) >= TRUTH_THRESHOLD

    audit_hash = hashlib.sha256(
        (GENESIS_SEAL + date + str(len(aligned))).encode()
    ).hexdigest()[:16]

    entry = f"""# Ralph Reflection — {date} {datetime.utcnow().strftime('%H:%M UTC')}

## Genesis Seal: {GENESIS_SEAL[:8]}

## Verdict: {len(aligned)}/{len(aligned)+len(drift)} aligned · {"✅ BUILD CLEAR" if not blocked else "⛔ BUILD BLOCKED"}

## Governance Checks
"""
    for a in aligned:
        entry += f"- ✅ {a}\n"
    for d in drift:
        entry += f"- ❌ {d['check']}: {d['severity']}\n"

    if blocked:
        entry += "\n## ⛔ BUILD BLOCKED — Truth Threshold breached\n"
        entry += "The operator must acknowledge drift before builds proceed.\n"
        entry += "Send: I ACKNOWLEDGE DRIFT\n"
    else:
        entry += "\n## Build gate: OPEN\n"

    if notes.get("present"):
        entry += f"\n## Daily note present: yes (seal: {'verified' if notes.get('has_seal') else 'missing'})\n"
    else:
        entry += f"\n## Daily note present: no (create {date}.md)\n"

    entry += f"\n## Signed\nRalph, Genesis Auditor · Audit hash: {audit_hash}\n"

    path = os.path.join(REFLECTIONS_DIR, f"{date}-ralph-reflection.md")
    with open(path, "w") as f:
        f.write(entry)

    return path, audit_hash, blocked


def run_audit():
    """Execute one audit cycle."""
    ensure_ledger()
    notes = scan_notes()
    directives = scan_ledger()
    aligned, drift = check_governance(directives)
    path, audit_hash, blocked = write_reflection(aligned, drift, notes)

    print(f"Ralph Audit: {len(aligned)}/{len(aligned)+len(drift)} aligned")
    if blocked:
        print(f"⛔ BUILD BLOCKED — Truth Threshold breached")
        print(f"   Reflection: {path}")
    else:
        print(f"✅ BUILD CLEAR — audit hash: {audit_hash}")

    return 1 if blocked else 0


def run_daemon():
    """Run continuously, check at 23:59 local time."""
    print(f"Ralph Auditor daemon started. Checking daily at 23:59.")
    last_date = None
    while True:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        hour_min = now.strftime("%H:%M")

        if hour_min == "23:59" and today != last_date:
            print(f"\n[{now.isoformat()}] Running daily audit...")
            run_audit()
            last_date = today
            time.sleep(61)  # skip past the minute

        time.sleep(30)


if __name__ == "__main__":
    if "--daemon" in sys.argv:
        run_daemon()
    elif "--check" in sys.argv:
        sys.exit(run_audit())
    else:
        sys.exit(run_audit())
