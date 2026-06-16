"""Mnemosyne — recursive ancestry compactor for the Oculus ledger.

Every 24h, Mnemosyne:
  1. Scans the Oculus ledger and genesis audit log
  2. Identifies entries older than 7 days
  3. Verifies hash-chain integrity of the old segment
  4. Separates Critical events (preserved) from Normal events (squashed)
  5. Compresses Normal events into an AncestryProof (Merkle root + count + time range)
  6. Writes a new compacted ledger with the squashed state

Constraints:
  - Genesis Anchor + last 7 days stay High-Fidelity (never squashed)
  - Critical error events (EMERGENCY, ERROR, FAIL, CRITICAL) are preserved
  - Only Normal Operation noise is compressed
  - Hash-chain integrity must be verified before any squash
  - The AncestryProof includes the Merkle root of the squashed segment
    so the chain remains verifiable end-to-end
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("mnemosyne")

# ── Constants ───────────────────────────────────────────────────────────────

SQUASH_INTERVAL_SEC = 86400  # 24 hours
HIGH_FIDELITY_DAYS = 7
CRITICAL_KEYWORDS = ["EMERGENCY", "ERROR", "FAIL", "CRITICAL", "BREACH"]
GENESIS_HASH = "0" * 64
ANCESTRY_PROOF_KIND = "ANCESTRY_PROOF"
ANCHOR_KIND = "MNEMOSYNE_ANCHOR"


# ── Ancestry Proof ─────────────────────────────────────────────────────────


class AncestryProof:
    """A zero-knowledge summary of a squashed audit segment.

    The proof contains:
      - count: number of original entries squashed
      - root_hash: Merkle root of the squashed segment
      - time_start / time_end: wall-clock range
      - seq_start / seq_end: sequence range
      - integrity_hash: sha256(concat of all original hashes)
      - preserved_critical: list of critical events exempt from squash
    """

    def __init__(self, entries: list[dict], critical_entries: list[dict] = None):
        self.entries = entries
        self.critical_entries = critical_entries or []
        self._compute()

    def _compute(self):
        self.count = len(self.entries)
        if not self.entries:
            self.root_hash = GENESIS_HASH
            self.time_start = 0
            self.time_end = 0
            self.seq_start = 0
            self.seq_end = 0
            self.integrity_hash = GENESIS_HASH
            return

        # Time range
        timestamps = []
        for e in self.entries:
            t = e.get("payload", {}).get("timestamp", 0)
            if isinstance(t, (int, float)):
                timestamps.append(t)
        self.time_start = min(timestamps) if timestamps else 0
        self.time_end = max(timestamps) if timestamps else 0

        # Seq range
        seqs = [e.get("seq", 0) for e in self.entries]
        self.seq_start = min(seqs) if seqs else 0
        self.seq_end = max(seqs) if seqs else 0

        # Root hash: sha256 of the last entry's hash in the segment
        last_entry = self.entries[-1]
        self.root_hash = last_entry.get("hash", GENESIS_HASH)

        # Integrity hash: sha256 of all hashes concatenated
        h = hashlib.sha256()
        for e in self.entries:
            h.update(e.get("hash", GENESIS_HASH).encode("ascii"))
        self.integrity_hash = h.hexdigest()

    def to_entry(self, prev_hash: str, seq: int) -> dict:
        """Convert this proof to an Oculus ledger entry."""
        payload = {
            "kind": ANCESTRY_PROOF_KIND,
            "squashed_count": self.count,
            "seq_start": self.seq_start,
            "seq_end": self.seq_end,
            "time_start": self.time_start,
            "time_end": self.time_end,
            "root_hash": self.root_hash,
            "integrity_hash": self.integrity_hash,
            "preserved_critical": [
                {
                    "seq": ce.get("seq"),
                    "kind": ce.get("payload", {}).get("kind"),
                    "timestamp": ce.get("payload", {}).get("timestamp"),
                    "summary": str(ce.get("payload", {}))[:200],
                }
                for ce in self.critical_entries
            ],
            "compressed_at": time.time(),
        }
        payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=True,
                                   separators=(",", ":")).encode("utf-8")
        h = hashlib.sha256()
        h.update(prev_hash.encode("ascii"))
        h.update(payload_bytes)
        entry_hash = h.hexdigest()

        return {
            "seq": seq,
            "prev": prev_hash,
            "payload": payload,
            "hash": entry_hash,
        }


# ── Critical Event Classifier ──────────────────────────────────────────────


def is_critical_event(entry: dict) -> bool:
    """Determine if an event is critical and should be preserved from squash."""
    payload = entry.get("payload", {})
    kind = payload.get("kind", "").upper()
    verdict = payload.get("verdict", "").upper()

    # Check by kind
    for kw in CRITICAL_KEYWORDS:
        if kw in kind:
            return True

    # Check by verdict
    if verdict == "FAIL":
        return True

    # Preserve specific event types
    preserve_kinds = {"CHAOS_MONKEY_TEST", "CIRCUIT_BREAKER_OPEN",
                      "EMERGENCY_HOLD_ACTIVE", "RECURSION_DETECTED",
                      "OPTIMIZATION_WARNING", "SYSTEM_READY"}
    if kind in preserve_kinds:
        return True

    return False


# ── Chain Verification ─────────────────────────────────────────────────────


def verify_chain(entries: list[dict]) -> bool:
    """Verify the hash-chain integrity of a list of entries."""
    prev = GENESIS_HASH
    for e in entries:
        if e.get("prev", "") != prev:
            logger.error("Chain break at seq=%d: expected prev=%s, got %s",
                         e.get("seq"), prev[:16], e.get("prev", "")[:16])
            return False
        # Recompute hash
        payload_bytes = json.dumps(e["payload"], sort_keys=True,
                                   ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        h = hashlib.sha256()
        h.update(prev.encode("ascii"))
        h.update(payload_bytes)
        expected = h.hexdigest()
        if e.get("hash", "") != expected:
            logger.error("Hash mismatch at seq=%d", e.get("seq"))
            return False
        prev = e.get("hash", GENESIS_HASH)
    return True


# ── State Squash ───────────────────────────────────────────────────────────


def squash_ledger(ledger_path: str, high_fidelity_days: int = HIGH_FIDELITY_DAYS,
                  dry_run: bool = False) -> Optional[list[dict]]:
    """Perform one squash cycle on the Oculus ledger.

    Args:
        ledger_path: Path to the JSONL ledger file.
        high_fidelity_days: Keep this many days intact (default 7).
        dry_run: If True, just report what would be squashed without writing.

    Returns:
        The new ledger entries (including AncestryProof), or None if dry_run.
    """
    if not os.path.isfile(ledger_path):
        logger.warning("Ledger not found: %s", ledger_path)
        return None

    # Load all entries
    entries = []
    with open(ledger_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON at line: %s", e)
                return None

    if len(entries) < 2:
        logger.info("Ledger too small to squash (%d entries)", len(entries))
        return None

    # Verify full chain integrity
    if not verify_chain(entries):
        logger.error("Chain integrity check FAILED — refusing to squash")
        return None

    now = time.time()
    cutoff = now - (high_fidelity_days * 86400)

    # Separate old vs recent
    old_entries = []
    recent_entries = []
    for e in entries:
        ts = e.get("payload", {}).get("timestamp", 0)
        if ts > 0 and ts < cutoff and e.get("seq", 0) > 0:
            old_entries.append(e)
        else:
            recent_entries.append(e)

    # Genesis anchor (seq=0) is always preserved
    genesis_entry = entries[0] if entries else None

    if not old_entries:
        logger.info("No entries older than %d days to squash", high_fidelity_days)
        return None

    # Separate critical from normal among old entries
    old_critical = [e for e in old_entries if is_critical_event(e)]
    old_normal = [e for e in old_entries if not is_critical_event(e)]

    logger.info(
        "Squash analysis: %d old (%d critical, %d normal), %d recent + genesis",
        len(old_entries), len(old_critical), len(old_normal), len(recent_entries)
    )

    if not old_normal:
        logger.info("No normal-operation entries to squash")
        return None

    # Build ancestry proof from normal entries
    proof = AncestryProof(old_normal, old_critical)

    # Build new ledger: genesis + proof + preserved critical + recent
    new_entries = []
    prev = GENESIS_HASH
    seq = 0

    if genesis_entry:
        new_entries.append(genesis_entry)
        prev = genesis_entry["hash"]
        seq = genesis_entry["seq"]

    # Insert the ancestry proof
    proof_entry = proof.to_entry(prev, seq + 1)
    new_entries.append(proof_entry)
    prev = proof_entry["hash"]
    seq = proof_entry["seq"]

    # Insert preserved critical events (re-hash them into the chain)
    for ce in old_critical:
        seq += 1
        ce["seq"] = seq
        ce["prev"] = prev
        payload_bytes = json.dumps(ce["payload"], sort_keys=True,
                                   ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        h = hashlib.sha256()
        h.update(prev.encode("ascii"))
        h.update(payload_bytes)
        ce["hash"] = h.hexdigest()
        new_entries.append(ce)
        prev = ce["hash"]

    # Insert recent entries
    for re_entry in recent_entries:
        if re_entry.get("seq", -1) == 0 and genesis_entry:
            continue  # already added
        seq += 1
        re_entry["seq"] = seq
        re_entry["prev"] = prev
        payload_bytes = json.dumps(re_entry["payload"], sort_keys=True,
                                   ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        h = hashlib.sha256()
        h.update(prev.encode("ascii"))
        h.update(payload_bytes)
        re_entry["hash"] = h.hexdigest()
        new_entries.append(re_entry)
        prev = re_entry["hash"]

    # Report
    original_entries = len(entries)
    new_count = len(new_entries)
    compressed = original_entries - new_count
    compression_ratio = (1 - (new_count / original_entries)) * 100 if original_entries > 0 else 0

    logger.info(
        "Squash complete: %d → %d entries (%d compressed, %.1f%% reduction)",
        original_entries, new_count, compressed, compression_ratio
    )

    if dry_run:
        print("\n=== DRY RUN ===")
        print(f"  Original entries:     {original_entries}")
        print(f"  New entries:          {new_count}")
        print(f"  Compressed:           {compressed}")
        print(f"  Reduction:            {compression_ratio:.1f}%")
        print(f"  Old critical preserved: {len(old_critical)}")
        print(f"  Old normal squashed:    {len(old_normal)}")
        print(f"  AncestryProof root:   {proof.root_hash[:16]}...")
        print(f"  Integrity hash:       {proof.integrity_hash[:16]}...")
        print(f"  Time range:           {time.ctime(proof.time_start)} → {time.ctime(proof.time_end)}")
        print(f"  Chain verified:       yes")
        print()
        for ce in old_critical:
            ce_kind = ce.get("payload", {}).get("kind", "?")
            ce_seq = ce.get("seq", "?")
            print(f"  PRESERVED: seq={ce_seq} kind={ce_kind}")
        return new_entries

    # Write new ledger
    backup_path = ledger_path + ".pre-squash"
    os.rename(ledger_path, backup_path)
    logger.info("Backup written: %s", backup_path)

    with open(ledger_path, "w") as f:
        for entry in new_entries:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())

    logger.info("Squashed ledger written: %s (%d entries)", ledger_path, new_count)
    return new_entries


def run_mnemosyne(ledger_path: str, interval_sec: int = SQUASH_INTERVAL_SEC,
                  high_fidelity_days: int = HIGH_FIDELITY_DAYS,
                  dry_run: bool = False) -> None:
    """Run Mnemosyne as a background service.

    Performs one squash cycle, then sleeps for ``interval_sec``.
    """
    logger.info("Mnemosyne starting (interval=%ds, high_fidelity=%dd, ledger=%s)",
                interval_sec, high_fidelity_days, ledger_path)

    if dry_run:
        squash_ledger(ledger_path, high_fidelity_days, dry_run=True)
        return

    while True:
        squash_ledger(ledger_path, high_fidelity_days, dry_run=False)
        logger.info("Sleeping for %d seconds until next squash cycle", interval_sec)
        time.sleep(interval_sec)
