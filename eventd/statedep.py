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

Payloads are plain dicts with a ``kind`` discriminator: eventd payload bodies
are JSON; the ``.hcplang`` frames in RFC 0004 §2 are the wire form, this is
the logged form. Field names match the RFC structs exactly.
"""
from __future__ import annotations

from dataclasses import dataclass

KIND_REGISTRATION = "dependency_registration"
KIND_CHECKPOINT = "consumer_checkpoint"
KIND_REWIND = "rewind_event"
KIND_EVICTION = "consumer_evicted"


# --------------------------------------------------------------------------- #
# Payload constructors (RFC 0004 §2 — logged form)
# --------------------------------------------------------------------------- #

def dependency_registration(consumer: str, producer: str, consumer_step: int,
                            producer_step: int, producer_step_hash: str,
                            topology_epoch: int) -> dict:
    """§3.1: MUST be logged before the consumer reads the producer's output."""
    return {"kind": KIND_REGISTRATION, "consumer": consumer,
            "producer": producer, "consumer_step": consumer_step,
            "producer_step": producer_step,
            "producer_step_hash": producer_step_hash,
            "topology_epoch": topology_epoch}


def consumer_checkpoint(consumer_agent: str, producer_agent: str,
                        min_required_step: int, consumer_checkpoint_step: int,
                        topology_epoch: int, last_heartbeat_at: str) -> dict:
    """§4: the consumer's durable acknowledgement; feeds the GC floor."""
    return {"kind": KIND_CHECKPOINT, "consumer_agent": consumer_agent,
            "producer_agent": producer_agent,
            "min_required_step": min_required_step,
            "consumer_checkpoint_step": consumer_checkpoint_step,
            "topology_epoch": topology_epoch,
            "last_heartbeat_at": last_heartbeat_at}


def rewind_event(producer: str, rewind_to_step: int, rewind_to_hash: str,
                 topology_epoch: int) -> dict:
    """§3.3: anchors above ``rewind_to_step`` are void after this event."""
    return {"kind": KIND_REWIND, "producer": producer,
            "rewind_to_step": rewind_to_step,
            "rewind_to_hash": rewind_to_hash,
            "topology_epoch": topology_epoch}


def consumer_evicted(consumer_agent: str, reason: str,
                     topology_epoch: int) -> dict:
    """§4.2: explicit, logged eviction of a dead consumer from the GC floor —
    never silent. Voids that consumer's anchors (cold start will pause it)."""
    return {"kind": KIND_EVICTION, "consumer_agent": consumer_agent,
            "reason": reason, "topology_epoch": topology_epoch}


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
      * ``evicted`` — consumers removed from the floor by explicit eviction.
    """

    def __init__(self):
        self.registrations: dict[tuple[str, str], dict] = {}
        self.checkpoints: dict[tuple[str, str], dict] = {}
        self.rewinds: dict[str, dict] = {}
        self.evicted: set[str] = set()

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
                idx.evicted.add(p["consumer_agent"])
        return idx

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
            if prod != producer or consumer in self.evicted:
                continue
            reg = self.registrations.get((consumer, prod))
            cp = self.checkpoints.get((consumer, prod))
            if cp is not None and (reg is None
                                   or cp["_at_seq"] > reg["_at_seq"]):
                floors.append(cp["min_required_step"])
            elif reg is not None:
                floors.append(reg["producer_step"])
        return min(floors) if floors else None

    # -- cold-start verifier (§6) ---------------------------------------------

    def verify_cold_start(self, consumer: str,
                          entries: list[dict]) -> StaleDependency | None:
        """Validate every direct producer anchor of ``consumer`` against the
        verified log. ``None`` ⇒ RUNNING; otherwise the first (in registration
        order — deterministic) ``StaleDependency`` ⇒ PAUSED(stale_dependency).

        An anchor is stale when: the anchored entry is missing (truncated past
        the floor), its hash diverges, a rewind for the producer logged after
        the registration undercuts it, or the consumer was evicted (§4.2)."""
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
            if consumer in self.evicted:
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
