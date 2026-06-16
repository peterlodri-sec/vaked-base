"""The non-currency winner reward: a codename honorific + a verifiable trophy attestation.

The champion is NOT paid currency — they earn a lore codename + a hash-chained trophy
(recognition + a tamper-evident bragging right). The codename is derived from the run's
pre-trophy chain hash, so it is deterministic, replay-stable, and unforgeable: a third
party can confirm `champion` earned `codename` for the run whose hash is `bound_to`.
"""
from __future__ import annotations

# ASCII lore pool (Mysterious Universe / project codenames).
CODENAMES = [
    "brett-shaw", "anstetten", "praetorian", "infra-light", "feketecs", "sherlock",
    "katedralis", "bolygorozsa", "opium-waltz", "the-cordon", "static-armor", "the-dossier",
]


def codename_for(prior_hash: str) -> str:
    """Deterministic codename bound to the run's pre-trophy chain hash."""
    return CODENAMES[int(prior_hash, 16) % len(CODENAMES)]


def mint_trophy(champion_id: str, prior_hash: str, welfare: int) -> dict:
    """The trophy payload (appended to the ledger as the final, chained event)."""
    codename = codename_for(prior_hash)
    return {
        "kind": "trophy",
        "champion": champion_id,
        "codename": codename,
        "bound_to": prior_hash,
        "welfare": welfare,
        "citation": 'CTF champion "%s" → codename "%s" (bound to run %s)'
                    % (champion_id, codename, prior_hash[:12]),
    }
