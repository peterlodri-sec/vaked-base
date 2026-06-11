"""ralphcore — pure-logic core for the ralph decision/strategy loop.

Python 3.12 stdlib only. No external dependencies.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Task 1 — Config loader
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Repo:
    """A tracked repository."""

    name: str
    path: str
    gh: str


def load_repos(config_path: str) -> list[Repo]:
    """Load repos from a JSON config file, expanding user paths to absolute."""
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    return [
        Repo(
            name=r["name"],
            path=os.path.abspath(os.path.expanduser(r["path"])),
            gh=r["gh"],
        )
        for r in data["repos"]
    ]


# ---------------------------------------------------------------------------
# Task 2 — Cost math
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Price:
    """Per-million-token pricing for a model."""

    prompt_per_m: float
    completion_per_m: float


def cost_usd(usage: dict, price: Price) -> float:
    """Return USD cost for a single API call given token usage and pricing."""
    pin = usage.get("prompt_tokens", 0) or 0
    pout = usage.get("completion_tokens", 0) or 0
    return pin / 1e6 * price.prompt_per_m + pout / 1e6 * price.completion_per_m


FALLBACK_PRICES: dict[str, Price] = {
    "qwen/qwen3-235b-a22b-thinking-2507": Price(0.10, 0.10),
    "deepseek/deepseek-v4-flash": Price(0.098, 0.197),
}


# ---------------------------------------------------------------------------
# Task 3 — Candidate selection
# ---------------------------------------------------------------------------


def select_candidate(candidates: list[dict]) -> dict | None:
    """Return the best candidate to decide next.

    Prefers unaddressed candidates; falls back to all candidates if all are
    addressed. Picks the highest urgency (ties broken by first occurrence).
    Returns None for an empty list.
    """
    if not candidates:
        return None
    unaddressed = [c for c in candidates if not c.get("addressed", False)]
    pool = unaddressed if unaddressed else candidates
    best = pool[0]
    for c in pool[1:]:
        if int(c.get("urgency", 0)) > int(best.get("urgency", 0)):
            best = c
    return best


# ---------------------------------------------------------------------------
# Task 4 — Round-robin repo selection
# ---------------------------------------------------------------------------


def next_repo(
    names: list[str],
    current: str | None,
    unavailable: set,
) -> str | None:
    """Return the next repo name in round-robin order, skipping unavailable.

    Returns None if every name is unavailable.
    If current is None or not in names, returns the first available name.
    """
    available = [n for n in names if n not in unavailable]
    if not available:
        return None
    if current is None or current not in names:
        return available[0]
    start = names.index(current)
    n = len(names)
    for i in range(1, n + 1):
        cand = names[(start + i) % n]
        if cand in available:
            return cand
    return available[0]


# ---------------------------------------------------------------------------
# Task 5 — Prompt + entry formatting
# ---------------------------------------------------------------------------

_STAGE1_SYS = (
    "You are the strategy advisor for the {repo} repository. From the project state and the titles of prior decisions, identify the open STRATEGIC decisions that matter most right now. Return JSON ONLY matching the schema: "
    '{{"candidates":[{{"title":str,"why_now":str,"urgency":1-5,"addressed":bool}}]}}. '
    "Mark addressed=true if a prior-decision title already covers it. Rank by urgency. Do not invent work; ground every candidate in the provided state."
)

_STAGE2_SYS = (
    "You are the strategy advisor for the {repo} repository. Given ONE chosen decision and the full project context, write a single decision entry in GitHub-flavored markdown with these bold-labelled lines: Decision / question, Options, Recommendation, Risks, Next actions, Confidence (low|med|high). Be concrete and grounded; no preamble, output only the entry body."
)


def build_stage1_messages(
    repo: str,
    compact_state: str,
    prior_titles: list[str],
) -> list[dict]:
    """Build the message list for the stage-1 (candidate enumeration) LLM call."""
    titles = "\n".join("- " + t for t in prior_titles) or "(none yet)"
    return [
        {"role": "system", "content": _STAGE1_SYS.format(repo=repo)},
        {"role": "user", "content": f"# Prior decision titles\n{titles}\n\n# Project state\n{compact_state}"},
    ]


def build_stage2_messages(
    repo: str,
    full_context: str,
    candidate: dict,
) -> list[dict]:
    """Build the message list for the stage-2 (decision body) LLM call."""
    c = json.dumps(candidate, ensure_ascii=False)
    return [
        {"role": "system", "content": _STAGE2_SYS.format(repo=repo)},
        {"role": "user", "content": f"# Chosen decision\n{c}\n\n# Full project context\n{full_context}"},
    ]


def format_entry(
    n: int,
    date: str,
    repo: str,
    head: str,
    open_issues: int,
    body: str,
    s1: str,
    s2: str,
) -> str:
    """Format a completed decision entry for the decision log."""
    first = next(
        (ln.strip(" #*-") for ln in body.splitlines() if ln.strip()),
        "untitled",
    )
    title = first[:80]
    return (
        f"## {date} — Decision #{n}: {title}\n"
        f"- **Repo:** {repo} · **Models:** stage1 {s1} · stage2 {s2}\n"
        f"- **Context snapshot:** HEAD {head}, {open_issues} open issues\n\n"
        f"{body.rstrip()}\n\n"
    )
