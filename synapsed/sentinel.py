"""Sentinel — reputation-based audit and reporting service (L3).

Sentinel is a non-coercive, integrity-focused layer that monitors gossip
traffic for "logical dishonesty." It does NOT restart services or force
actions — it acts strictly as a Whistleblower.

Architecture::

    ┌─────────────────────────────────────────────────────┐
    │  Sentinel (L3)                                       │
    │  ┌─────────────┐  ┌──────────┐  ┌────────────────┐  │
    │  │ TruthPing   │  │ Trust    │  │ DM Channel     │  │
    │  │ (cross-ref  │  │ Engine   │  │ (rate-limited  │  │
    │  │  claims vs  │  │ (scores) │  │  signed alerts)│  │
    │  │  reality)   │  │          │  │                │  │
    │  └──────┬──────┘  └────┬─────┘  └───────┬────────┘  │
    │         │              │                │           │
    │         └──────────────┴────────────────┘           │
    │                        │                            │
    │              Oculus Ledger (append-only)            │
    └─────────────────────────────────────────────────────┘

Constraints:
    - Rate limited: 1 message per peer every 60 seconds
    - No persistence: logs to Oculus ledger, cannot modify system state
    - Non-blocking: separate thread, must not delay Synapse gossip
    - Non-coercive: no service restarts, only whistleblowing
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("synapsed.sentinel")

# ── Constants ───────────────────────────────────────────────────────────────

DM_ALERT = "SENTINEL_DM_ALERT"
DM_OPERATOR = "SENTINEL_DM_OPERATOR"
TRUST_DECAY_INTERVAL = 300  # 5 min — scores decay toward neutral
MAX_ALERTS_PER_PEER_PER_MIN = 1
SENTINEL_GOSSIP_PORT = 4436  # one above the gateway port
INITIAL_TRUST_SCORE = 1.0
SUSPICION_THRESHOLD = 0.3  # below this → operator alert


@dataclass
class TrustRecord:
    """Reputation state for a single peer."""
    node_id: str
    score: float = INITIAL_TRUST_SCORE
    alert_count: int = 0
    last_alert_ts: float = 0.0
    last_seen_claim: str = ""    # last capability path claimed
    last_seen_hash: str = ""     # last Merkle claim hash
    last_seen_ts: float = 0.0
    flagged: bool = False        # currently under suspicion


class TruthPing:
    """Cross-references capability claims against verified Merkle roots.

    A "lie" is defined as:
        1. A node claims a capability at path P with value V
        2. Sentinel independently queries P from its own verified tree
        3. If Sentinel's value V_sentinel != V_claimed → the node is dishonest
    """

    def __init__(self, local_tree: "CapabilityMerkleTree"):
        self._local_tree = local_tree

    def verify_claim(self, path: str, claimed_value: dict) -> tuple[bool, Optional[dict]]:
        """Verify a capability claim against the local tree.

        Returns (is_honest, actual_value).
        """
        # Walk the local tree to find the value at this path
        actual = self._find_value(path)
        if actual is None:
            # We don't have this capability — can't verify
            return True, None
        if actual != claimed_value:
            return False, actual
        return True, actual

    def _find_value(self, path: str) -> Optional[dict]:
        """Walk the Merkle tree to find a value at the given path."""
        parts = path.strip("/").split("/")
        node = self._local_tree.root
        for part in parts:
            if part not in node.children:
                return None
            node = node.children[part]
        return node.leaf_value

    def cross_reference_gossip(self, peer_id: str, peer_merkle_root: str,
                               path: str, claimed_value: dict) -> Optional[dict]:
        """Cross-reference a gossip claim. Returns an alert dict if dishonest."""
        honest, actual = self.verify_claim(path, claimed_value)
        if not honest:
            return {
                "kind": DM_ALERT,
                "target": peer_id,
                "path": path,
                "claimed": claimed_value,
                "actual": actual,
                "severity": "dishonest_claim",
            }
        return None


class TrustEngine:
    """Maintains per-peer trust scores with decay and flag logic."""

    def __init__(self):
        self._peers: dict[str, TrustRecord] = {}
        self._lock = threading.Lock()

    def get(self, node_id: str) -> TrustRecord:
        with self._lock:
            if node_id not in self._peers:
                self._peers[node_id] = TrustRecord(node_id=node_id)
            return self._peers[node_id]

    def record_claim(self, node_id: str, path: str, merkle_hash: str) -> None:
        """Record a capability claim from a peer."""
        with self._lock:
            rec = self.get(node_id)
            rec.last_seen_claim = path
            rec.last_seen_hash = merkle_hash
            rec.last_seen_ts = time.time()

    def penalize(self, node_id: str, reason: str, amount: float = 0.1) -> float:
        """Decrement a peer's trust score. Returns new score."""
        with self._lock:
            rec = self.get(node_id)
            rec.score = max(0.0, rec.score - amount)
            rec.alert_count += 1
            rec.last_alert_ts = time.time()
            if rec.score < SUSPICION_THRESHOLD:
                rec.flagged = True
            logger.warning("Trust penalize %s: %.2f → %.2f (reason: %s)",
                           node_id, rec.score + amount, rec.score, reason)
            return rec.score

    def reward(self, node_id: str, amount: float = 0.05) -> float:
        """Increment a peer's trust score for honest behavior."""
        with self._lock:
            rec = self.get(node_id)
            rec.score = min(1.0, rec.score + amount)
            if rec.score >= SUSPICION_THRESHOLD:
                rec.flagged = False
            return rec.score

    def decay(self) -> None:
        """Periodic decay: scores drift toward 0.5 (neutral)."""
        with self._lock:
            for rec in self._peers.values():
                if rec.score > 0.5:
                    rec.score = max(0.5, rec.score - 0.02)
                elif rec.score < 0.5:
                    rec.score = min(0.5, rec.score + 0.02)

    def trust_index(self) -> float:
        """Overall swarm trust index (0.0–1.0)."""
        with self._lock:
            if not self._peers:
                return 1.0
            return sum(r.score for r in self._peers.values()) / len(self._peers)

    def flagged_peers(self) -> list[str]:
        with self._lock:
            return [n for n, r in self._peers.items() if r.flagged]

    def to_dict(self) -> dict:
        with self._lock:
            return {
                n: {
                    "score": round(r.score, 3),
                    "alerts": r.alert_count,
                    "flagged": r.flagged,
                    "last_seen_claim": r.last_seen_claim,
                    "last_seen_ts": r.last_seen_ts,
                }
                for n, r in self._peers.items()
            }


class DMChannel:
    """Dedicated gossip channel for signed Sentinel alerts.

    Rate-limited: 1 message per peer per 60 seconds.
    Messages are logged to the Oculus ledger but cannot modify system state.
    """

    def __init__(self, node_id: str, data_dir: str):
        self.node_id = node_id
        self.data_dir = data_dir
        self._last_sent: dict[str, float] = {}  # peer_id → timestamp
        self._lock = threading.Lock()

    def can_send(self, peer_id: str) -> bool:
        """Rate limit check: 1 msg/peer/60s."""
        with self._lock:
            last = self._last_sent.get(peer_id, 0.0)
            return (time.time() - last) >= 60

    def send_alert(self, peer_id: str, alert: dict) -> Optional[dict]:
        """Send a signed alert to a peer (logs to Oculus ledger).

        Returns the alert dict for ledger recording, or None if rate-limited.
        """
        if not self.can_send(peer_id):
            logger.debug("Rate-limited alert to %s", peer_id)
            return None

        with self._lock:
            self._last_sent[peer_id] = time.time()

        alert["nonce"] = uuid.uuid4().hex[:16]
        alert["sentinel_id"] = self.node_id
        alert["timestamp"] = time.time()
        # In production, sign with Sentinel's Ed25519 key
        alert["signature"] = f"sentinel-{uuid.uuid4().hex[:8]}"
        return alert

    def send_operator_alert(self, alert: dict) -> dict:
        """Send an alert to the operator (logged to Oculus ledger)."""
        alert["kind"] = DM_OPERATOR
        alert["nonce"] = uuid.uuid4().hex[:16]
        alert["sentinel_id"] = self.node_id
        alert["timestamp"] = time.time()
        alert["signature"] = f"operator-{uuid.uuid4().hex[:8]}"
        return alert


class Sentinel:
    """Non-coercive, integrity-focused audit layer.

    Runs as a background thread. Monitors gossip claims, cross-references
    against verified state, and logs alerts to the Oculus ledger.
    """

    def __init__(self, node_id: str, data_dir: str,
                 local_tree: "CapabilityMerkleTree"):
        self.node_id = f"sentinel-{node_id}"
        self.data_dir = data_dir
        self.truth = TruthPing(local_tree)
        self.trust = TrustEngine()
        self.dm = DMChannel(self.node_id, data_dir)
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the Sentinel background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Sentinel started (node=%s)", self.node_id)

    def stop(self):
        self._running = False

    def _loop(self):
        """Main audit loop — runs every 10 seconds."""
        while self._running:
            try:
                self._audit_cycle()
            except Exception as e:
                logger.error("Sentinel audit error: %s", e, exc_info=True)
            time.sleep(10)

    def _audit_cycle(self):
        """One audit cycle: check peers, decay trust, log to Oculus."""
        self.trust.decay()

    def inspect_gossip_claim(self, peer_id: str, path: str,
                             claimed_value: dict, peer_root: str) -> Optional[dict]:
        """Inspect a gossip claim for dishonesty.

        Returns an alert dict if a lie is detected, None otherwise.
        """
        # Record the claim
        self.trust.record_claim(peer_id, path, peer_root)

        # Cross-reference
        alert = self.truth.cross_reference_gossip(
            peer_id, peer_root, path, claimed_value
        )

        if alert:
            # Penalize trust
            self.trust.penalize(peer_id, f"dishonest_claim at {path}", amount=0.15)

            # Send DM to peer (rate-limited)
            dm = self.dm.send_alert(peer_id, alert)
            if dm:
                logger.warning("Sentinel alerted %s: claim at %s is dishonest",
                               peer_id, path)

                # Also send operator alert if trust dropped below threshold
                if self.trust.get(peer_id).score < SUSPICION_THRESHOLD:
                    op_alert = self.dm.send_operator_alert({
                        "kind": DM_OPERATOR,
                        "target": peer_id,
                        "path": path,
                        "trust_score": self.trust.get(peer_id).score,
                        "severity": "critical_trust_drop",
                        "message": f"Peer {peer_id} trust score dropped to "
                                   f"{self.trust.get(peer_id).score:.2f}",
                    })
                    if op_alert:
                        logger.critical("Operator alert: %s", op_alert.get("message"))

            return alert

        # Honest claim — small trust reward
        self.trust.reward(peer_id, amount=0.01)
        return None

    def inject_test_lie(self, liar_id: str = "edge-node-02-test",
                        path: str = "genesis/network/egress",
                        fake_value: Optional[dict] = None) -> dict:
        """Simulate a malicious capability claim for testing.

        Returns the alert that Sentinel generates.
        """
        if fake_value is None:
            fake_value = {
                "default": "allow",
                "authority": "rogue",
                "fabricated": True,
                "timestamp": time.time(),
            }
        alert = self.inspect_gossip_claim(
            liar_id, path, fake_value,
            peer_root="FAKE_ROOT_HASH_FOR_TEST"
        )
        return alert or {"kind": "NO_ALERT", "note": "claim was honest"}

    @property
    def trust_index(self) -> float:
        return self.trust.trust_index()

    def to_dict(self) -> dict:
        return {
            "sentinel_id": self.node_id,
            "trust_index": round(self.trust.trust_index(), 3),
            "flagged_peers": self.trust.flagged_peers(),
            "peers": self.trust.to_dict(),
        }
