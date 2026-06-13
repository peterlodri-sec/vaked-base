"""eventd.statedep — the RFC 0004 state-dependency layer (reference).

Implements, over the eventd log, the first slice of RFC 0004's implementation
order (protocol/rfcs/0004-multi-agent-state-dependency.md §8):

  1. ``DependencyRegistration`` WAL payload (§2–§3) — the causal anchor,
     logged BEFORE consumption, carrying the topology epoch (§7);
  2. ``RewindEvent`` payload (§3.3) — voids anchors above the rewind point;
  3. the ``StaleDependency`` pause record (§6) the supervisor consumes;
  4. ``DependencyIndex`` — the O(1) lookup index, built as a fold;
  6. the dependency-aware GC floor (§4), with explicit logged eviction (§4.2);
  7. the cold-start verifier (§6): RUNNING only after every direct anchor
     validates; first failure returns its ``StaleDependency``.

(Order 5 — the DAG compiler pass — lives in vakedc, not here. Order 8 — the
zero-copy scan path — is a Zig-port concern, explicitly after correctness.)

Payloads are plain dicts with a ``kind`` discriminator and a ``v`` schema
version (reserved migration space — the byte format hardens at the Zig port):
eventd payload bodies are JSON; the ``.hcplang`` frames in RFC 0004 §2 are the
wire form, this is the logged form. Field names match the RFC structs exactly.
Step / epoch fields are **integers only** — floats are banned from statedep
payloads (cross-runtime number-encoding drift is not worth inviting).

Fold semantics (normative for the reference — the Zig port reproduces them):

  * **Latest-wins in log order** per ``(consumer, producer)`` key.
  * **Re-registration is a new dependency generation**: it REPLACES the
    anchor; cold start validates only the latest registration.
  * **A backwards checkpoint** (lower ``min_required_step`` than its
    predecessor) is accepted: it moves the GC floor *down* — the conservative
    direction. History is only ever released by raising the value.
  * **Eviction voids ALL the consumer's edges at its log position; each edge
    is individually revived only by a ``DependencyRegistration`` logged AFTER
    the eviction** (a real per-producer re-anchor, §6 explicit recovery).
    Re-anchoring producer A does not revive a stale anchor on producer B, and
    an ordinary checkpoint from an evicted consumer — e.g. a delayed write
    from the dead process — never re-admits anything.
"""
from __future__ import annotations

from dataclasses import dataclass

KIND_REGISTRATION = "dependency_registration"
KIND_CHECKPOINT = "consumer_checkpoint"
KIND_REWIND = "rewind_event"
KIND_EVICTION = "consumer_evicted"

STATEDEP_V = 1


def _require_int(name: str, value):
    """Step/epoch fields are ints, full stop (bool is not an int here)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int — floats/non-ints are banned "
                        f"in statedep payloads")
    return value


# --------------------------------------------------------------------------- #
# Payload constructors (RFC 0004 §2 — logged form)
# --------------------------------------------------------------------------- #

def dependency_registration(consumer: str, producer: str, consumer_step: int,
                            producer_step: int, producer_step_hash: str,
                            topology_epoch: int) -> dict:
    """§3.1: MUST be logged before the consumer reads the producer's output."""
    return {"kind": KIND_REGISTRATION, "v": STATEDEP_V, "consumer": consumer,
            "producer": producer,
            "consumer_step": _require_int("consumer_step", consumer_step),
            "producer_step": _require_int("producer_step", producer_step),
            "producer_step_hash": producer_step_hash,
            "topology_epoch": _require_int("topology_epoch", topology_epoch)}


def consumer_checkpoint(consumer_agent: str, producer_agent: str,
                        min_required_step: int, consumer_checkpoint_step: int,
                        topology_epoch: int, last_heartbeat_at: str) -> dict:
    """§4: the consumer's durable acknowledgement; feeds the GC floor."""
    return {"kind": KIND_CHECKPOINT, "v": STATEDEP_V,
            "consumer_agent": consumer_agent,
            "producer_agent": producer_agent,
            "min_required_step": _require_int("min_required_step",
                                              min_required_step),
            "consumer_checkpoint_step": _require_int(
                "consumer_checkpoint_step", consumer_checkpoint_step),
            "topology_epoch": _require_int("topology_epoch", topology_epoch),
            "last_heartbeat_at": last_heartbeat_at}


def rewind_event(producer: str, rewind_to_step: int, rewind_to_hash: str,
                 topology_epoch: int) -> dict:
    """§3.3: anchors above ``rewind_to_step`` are void after this event."""
    return {"kind": KIND_REWIND, "v": STATEDEP_V, "producer": producer,
            "rewind_to_step": _require_int("rewind_to_step", rewind_to_step),
            "rewind_to_hash": rewind_to_hash,
            "topology_epoch": _require_int("topology_epoch", topology_epoch)}


def consumer_evicted(consumer_agent: str, reason: str,
                     topology_epoch: int) -> dict:
    """§4.2: explicit, logged eviction of a dead consumer from the GC floor —
    never silent. Voids that consumer's anchors (cold start will pause it)."""
    return {"kind": KIND_EVICTION, "v": STATEDEP_V,
            "consumer_agent": consumer_agent,
            "reason": reason,
            "topology_epoch": _require_int("topology_epoch", topology_epoch)}


# --------------------------------------------------------------------------- #
# The pause record (RFC 0004 §6)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class StaleDependency:
    """Why the supervisor refused the RUNNING transition (PAUSED reason)."""
    producer: str
    expected_step: int
    expected_hash: str
    observed_tip: int | None
    topology_epoch: int


# --------------------------------------------------------------------------- #
# The O(1) dependency index (RFC 0004 §8 order 4) — built as a fold
# --------------------------------------------------------------------------- #

class DependencyIndex:
    """Fold of the state-dependency payloads in a verified log.

    Latest-wins per key, in log order (the log is the time axis):
      * ``registrations[(consumer, producer)]`` — the live anchor + the log
        seq it was registered at (rewinds logged AFTER it can void it);
      * ``checkpoints[(consumer, producer)]`` — the latest acknowledgement;
      * ``rewinds[producer]`` — the latest rewind (with its log seq);
      * ``evicted[consumer]`` — the log seq of the latest explicit eviction;
        an edge is LIVE iff its registration was logged after that seq.
    """

    def __init__(self):
        self.registrations: dict[tuple[str, str], dict] = {}
        self.checkpoints: dict[tuple[str, str], dict] = {}
        self.rewinds: dict[str, dict] = {}
        self.evicted: dict[str, int] = {}

    @classmethod
    def from_entries(cls, entries: list[dict]) -> "DependencyIndex":
        idx = cls()
        for e in entries:
            p = e.get("payload", {})
            kind = p.get("kind")
            if kind == KIND_REGISTRATION:
                idx.registrations[(p["consumer"], p["producer"])] = \
                    dict(p, _at_seq=e["seq"])
            elif kind == KIND_CHECKPOINT:
                idx.checkpoints[(p["consumer_agent"], p["producer_agent"])] = \
                    dict(p, _at_seq=e["seq"])
            elif kind == KIND_REWIND:
                idx.rewinds[p["producer"]] = dict(p, _at_seq=e["seq"])
            elif kind == KIND_EVICTION:
                idx.evicted[p["consumer_agent"]] = e["seq"]
        return idx

    def _edge_live(self, consumer: str, producer: str) -> bool:
        """An edge survives eviction only via a registration logged AFTER the
        consumer's latest eviction (§6 explicit recovery is per producer:
        re-anchoring A never revives a stale anchor on B; checkpoints never
        revive anything)."""
        ev_seq = self.evicted.get(consumer)
        if ev_seq is None:
            return True
        reg = self.registrations.get((consumer, producer))
        return reg is not None and reg["_at_seq"] > ev_seq

    # -- GC floor (§4) -------------------------------------------------------

    def gc_floor(self, producer: str) -> int | None:
        """producer_gc_floor = min over non-evicted downstream consumers'
        constraints for this producer (§4.1 condition 1 — proof retention (2)
        and epoch audit (3) are the compactor's burden). ``None`` means no
        live consumer constrains this producer.

        Per consumer: a ``ConsumerCheckpoint`` logged AFTER the latest
        registration is the acknowledgement and contributes its
        ``min_required_step``; a registration NOT yet acknowledged pins the
        floor at its own ``producer_step`` — §4 forbids truncating an anchor
        whose consumer has not checkpointed past it."""
        floors = []
        for consumer, prod in set(self.registrations) | set(self.checkpoints):
            if prod != producer or not self._edge_live(consumer, prod):
                continue
            reg = self.registrations.get((consumer, prod))
            cp = self.checkpoints.get((consumer, prod))
            if cp is not None and (reg is None
                                   or cp["_at_seq"] > reg["_at_seq"]):
                floors.append(cp["min_required_step"])
            elif reg is not None:
                floors.append(reg["producer_step"])
        return min(floors) if floors else None

    def gc_floor_explain(self, producer: str) -> dict:
        """Operator diagnosis (#35): *which* live consumers pin
        ``producer_gc_floor`` and why. Returns
        ``{"floor": int|None, "pinned_by": [ {consumer, min_required_step,
        source, last_heartbeat_at} … ]}`` — one contributor per live edge,
        sorted by (min_required_step, consumer) so the floor is
        ``pinned_by[0]["min_required_step"]`` and the listing is
        deterministic. ``source`` is ``"checkpoint"`` (acknowledged) or
        ``"registration"`` (unacknowledged anchor); ``last_heartbeat_at`` is
        the checkpoint's heartbeat or ``None`` for a bare registration. This
        is what an operator reads when GC refuses to move."""
        pinned = []
        for consumer, prod in set(self.registrations) | set(self.checkpoints):
            if prod != producer or not self._edge_live(consumer, prod):
                continue
            reg = self.registrations.get((consumer, prod))
            cp = self.checkpoints.get((consumer, prod))
            if cp is not None and (reg is None
                                   or cp["_at_seq"] > reg["_at_seq"]):
                pinned.append({"consumer": consumer,
                               "min_required_step": cp["min_required_step"],
                               "source": "checkpoint",
                               "last_heartbeat_at": cp.get("last_heartbeat_at")})
            elif reg is not None:
                pinned.append({"consumer": consumer,
                               "min_required_step": reg["producer_step"],
                               "source": "registration",
                               "last_heartbeat_at": None})
        pinned.sort(key=lambda c: (c["min_required_step"], c["consumer"]))
        floor = pinned[0]["min_required_step"] if pinned else None
        return {"floor": floor, "pinned_by": pinned}

    # -- memory bounding (#35) ------------------------------------------------

    def prune_evicted(self) -> int:
        """Reclaim the dead **checkpoint** records of evicted consumers: a
        checkpoint whose edge is no longer live (``_edge_live`` False) only
        ever fed the GC floor, and ``gc_floor`` already filters it out, so
        dropping it changes nothing — it just frees memory in a long-running
        daemon that evicted a never-returning consumer.

        **Registrations are deliberately NOT pruned.** ``verify_cold_start``
        reads a dead registration as an active PAUSE signal (the consumer
        still owes a re-anchor on that producer, §6); deleting it would
        silently flip a consumer from PAUSED to RUNNING. (A re-anchor after
        eviction overwrites the key with a live registration via latest-wins,
        so the only dead registrations left are genuinely-owed ones.) Returns
        the count removed; never changes ``gc_floor`` / ``verify_cold_start``
        results."""
        removed = 0
        for key in [k for k in self.checkpoints
                    if not self._edge_live(k[0], k[1])]:
            del self.checkpoints[key]
            removed += 1
        return removed

    # -- cold-start verifier (§6) ---------------------------------------------

    def verify_cold_start(self, consumer: str,
                          entries: list[dict]) -> StaleDependency | None:
        """Validate every direct producer anchor of ``consumer`` against the
        verified log. ``None`` ⇒ RUNNING; otherwise the first (in registration
        order — deterministic) ``StaleDependency`` ⇒ PAUSED(stale_dependency).

        An anchor is stale when: the anchored entry is missing (truncated past
        the floor), its hash diverges, a rewind for the producer logged after
        the registration undercuts it, or the edge was voided by an eviction
        and not re-anchored since (§4.2 — liveness is per producer edge)."""
        observed_tip = entries[-1]["seq"] if entries else None
        for (cons, producer), reg in self.registrations.items():
            if cons != consumer:
                continue
            stale = StaleDependency(
                producer=producer,
                expected_step=reg["producer_step"],
                expected_hash=reg["producer_step_hash"],
                observed_tip=observed_tip,
                topology_epoch=reg["topology_epoch"],
            )
            if not self._edge_live(consumer, producer):
                return stale
            step = reg["producer_step"]
            if observed_tip is None or step > observed_tip:
                return stale
            anchored = entries[step]
            if anchored.get("hash") != reg["producer_step_hash"]:
                return stale
            rew = self.rewinds.get(producer)
            if rew is not None and rew["_at_seq"] > reg["_at_seq"] \
                    and rew["rewind_to_step"] < step:
                return stale
        return None
