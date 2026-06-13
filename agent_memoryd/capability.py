"""agent_memoryd.capability — POLA-attenuated ``mem`` capability enforcement.

Implements the ``mem`` capability domain from 0014 §"Recall (the read path)":

    none < recall < append < admin

Agents may only:
  * ``mem.recall`` — read/query their own scope entries (or granted entries)
  * ``mem.append`` — store new entries (mining fibers)
  * ``mem.admin`` — store, recall, and forget (delete) any entry; the
    control plane only

Every store/recall/forget is checked against the token's level before the
operation proceeds. POLA: tokens may only carry the minimum necessary level.

Python 3.11+ stdlib only (mirrors the eventd/agent-guardd reference discipline).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class CapLevel(IntEnum):
    """Ordered lattice: none < recall < append < admin."""
    NONE = 0
    RECALL = 1
    APPEND = 2
    ADMIN = 3

    @classmethod
    def from_str(cls, s: str) -> "CapLevel":
        mapping = {
            "none": cls.NONE,
            "recall": cls.RECALL,
            "append": cls.APPEND,
            "admin": cls.ADMIN,
        }
        try:
            return mapping[s.lower()]
        except KeyError:
            raise ValueError("unknown mem capability level %r; "
                             "expected one of %s" % (s, list(mapping)))

    def __str__(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class CapabilityToken:
    """A POLA-attenuated access credential for the ``mem`` domain.

    ``agent_id`` is the identity the token was issued to; ``level`` is the
    maximum capability granted; ``scope`` optionally restricts the token to
    a single scope partition (``"session"``, ``"agent"``, or ``"runtime"``).
    A ``scope=None`` token covers all scopes (admin use only in practice).
    """
    agent_id: str
    level: CapLevel
    scope: "str | None" = None       # None → all scopes (admin only)

    def allows(self, required: CapLevel) -> bool:
        return self.level >= required

    def scope_visible(self, entry_scope: str, entry_agent_id: str) -> bool:
        """True if this token can see an entry with the given scope + owner.

        Visibility rules (POLA — least privilege):
          * admin    → sees all entries regardless of scope/owner.
          * append   → sees entries it owns, or entries in a matching scope.
          * recall   → sees entries it owns (same agent_id), or entries in a
                       scope to which the token's scope field matches.
          * none     → sees nothing.
        """
        if self.level == CapLevel.NONE:
            return False
        if self.level == CapLevel.ADMIN:
            return True
        # scope-restricted token: must match the entry's scope
        if self.scope is not None and self.scope != entry_scope:
            return False
        # own entries always visible at recall+
        if entry_agent_id == self.agent_id:
            return True
        # runtime scope: shared across agents — visible at recall+
        if entry_scope == "runtime":
            return True
        # agent scope: only the owning agent sees it (unless admin)
        if entry_scope == "agent":
            return False
        # session scope: only the owning agent's session
        return False


def check_capability(token: CapabilityToken, required: CapLevel) -> None:
    """Raise ``PermissionError`` if ``token.level < required``.

    This is the enforcement point called at every store / recall / forget
    before the operation touches the store.
    """
    if not token.allows(required):
        raise PermissionError(
            "mem capability insufficient: agent %r holds %s, "
            "requires %s" % (token.agent_id, token.level, required))


def token_from_dict(d: dict) -> CapabilityToken:
    """Deserialise a capability token from a request payload dict.

    Expected shape::

        {"agent_id": "...", "level": "recall"|"append"|"admin",
         "scope": "session"|"agent"|"runtime" | null}
    """
    agent_id = d.get("agent_id", "")
    if not agent_id:
        raise ValueError("capability token missing agent_id")
    level = CapLevel.from_str(d.get("level", "none"))
    scope = d.get("scope")       # None is fine — means all scopes
    if scope is not None and scope not in ("session", "agent", "runtime"):
        raise ValueError("unknown scope %r in capability token" % scope)
    return CapabilityToken(agent_id=agent_id, level=level, scope=scope)
