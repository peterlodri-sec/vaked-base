"""ralphcore — pure-logic core for the ralph decision/strategy loop.

Python 3.12 stdlib only. No external dependencies.
"""
from __future__ import annotations

import json
import os
import re
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
# Tracks — the primary axis (per-model concept loops). A track is a concept
# area inside the home repo, pinned to one model. `tracks.json` replaces
# `repos.json`; `Repo`/`load_repos` are kept for the deprecated repo mode.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrackContext:
    """What a track reads: doc globs + path filters (relative to the home repo)."""

    docs: list[str]
    paths: list[str]


@dataclass(frozen=True)
class Track:
    """A concept track: a topic + the one model that advances it."""

    name: str
    topic: str
    model: str
    label: str
    context: TrackContext


def load_tracks(config_path: str) -> list[Track]:
    """Load tracks from a JSON config file."""
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    out: list[Track] = []
    for t in data["tracks"]:
        c = t.get("context", {})
        out.append(
            Track(
                name=t["name"],
                topic=t["topic"],
                model=t["model"],
                label=t.get("label", ""),
                context=TrackContext(
                    docs=list(c.get("docs", [])),
                    paths=list(c.get("paths", [])),
                ),
            )
        )
    return out


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


# Per-1M-token fallback prices. The deepseek/qwen rates are real as of
# 2026-06-11; the hy3-preview/mimo rates are placeholders until the live
# OpenRouter /models refresh (Phase 4) overrides them. Every track model in
# tracks.json MUST have an entry here so cost is never silently guessed.
FALLBACK_PRICES: dict[str, Price] = {
    "qwen/qwen3-235b-a22b-thinking-2507": Price(0.10, 0.10),
    "deepseek/deepseek-v4-flash": Price(0.098, 0.197),
    "tencent/hy3-preview": Price(0.10, 0.20),     # placeholder — refresh from /models
    "xiaomi/mimo-v2.5": Price(0.10, 0.20),        # placeholder — refresh from /models
    "openai/gpt-oss-120b": Price(0.10, 0.30),     # toot generator — placeholder
    "deepseek/deepseek-v4-pro": Price(0.435, 0.87),  # RALPH_WRITER_MODEL (full V4) — live /models 2026-06-13
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
# Round-robin selection — one ring algorithm shared by the deprecated repo
# axis (`next_repo`) and the primary track axis (`next_track`).
# ---------------------------------------------------------------------------


def _next_in_ring(
    names: list[str],
    current: str | None,
    unavailable: set,
) -> str | None:
    """Return the next name in round-robin order, skipping unavailable ones.

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


# Same algorithm, two names: repos are the deprecated axis, tracks the primary.
next_repo = _next_in_ring
next_track = _next_in_ring


# ---------------------------------------------------------------------------
# Task 5 — Prompt + entry formatting
# ---------------------------------------------------------------------------

_STAGE1_SYS = (
    "You are the strategy advisor for {subject}. From the project state and the titles of prior decisions, identify the open STRATEGIC decisions that matter most right now. Return JSON ONLY matching the schema: "
    '{{"candidates":[{{"title":str,"why_now":str,"urgency":1-5,"addressed":bool}}]}}. '
    "Mark addressed=true if a prior-decision title already covers it. Rank by urgency. Do not invent work; ground every candidate in the provided state."
)

_STAGE2_SYS = (
    "You are the strategy advisor for {subject}. Given ONE chosen decision and the full project context, write a single decision entry in GitHub-flavored markdown with these bold-labelled lines: Decision / question, Options, Recommendation, Risks, Next actions, Confidence (low|med|high). "
    "GROUND every claim in the provided context — reference the actual file or issue it relies on (e.g. `docs/language/0011-type-system.md`, issue #17). Do NOT invent facts, files, or issues not present in the context. Make the Recommendation concrete and the Next actions a specific PR or issue to open. No preamble; output only the entry body."
)

_CRITIQUE_SYS = (
    "You are a rigorous reviewer improving a DRAFT strategic decision entry for {subject}. "
    "Rewrite it to be sharper and better grounded: every claim must cite the actual file or issue it relies on (from the context); cut hand-waving and hedging; make the Recommendation concrete and the Next actions a specific PR/issue. Remove any claim not supported by the context. "
    "Keep the SAME bold-labelled structure (Decision / question, Options, Recommendation, Risks, Next actions, Confidence). Output ONLY the improved entry body — no preamble, no meta-commentary about your changes."
)


def build_stage1_messages(
    subject: str,
    compact_state: str,
    prior_titles: list[str],
    mission: str = "",
    overrides: "list[str] | None" = None,
) -> list[dict]:
    """Build the message list for the stage-1 (candidate enumeration) LLM call.
    `subject` is what the advisor reasons about — a repo name (deprecated repo
    mode) or a track topic. `mission` (the PURPOSE.md preamble) is prepended to
    the system message so the loop always reasons in service of its stated goal.
    `overrides` are prior recommendations the human REJECTED (the ratify
    feedback loop) — injected so the loop learns what not to repeat."""
    titles = "\n".join("- " + t for t in prior_titles) or "(none yet)"
    system = _STAGE1_SYS.format(subject=subject)
    if mission.strip():
        system = mission.strip() + "\n\n---\n\n" + system
    user = f"# Prior decision titles\n{titles}\n\n# Project state\n{compact_state}"
    if overrides:
        rejected = "\n".join("- " + o for o in overrides)
        user = ("# Human overrides — prior recommendations the human REJECTED. "
                "Do NOT repeat these; address the stated reason instead.\n"
                + rejected + "\n\n" + user)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_stage2_messages(
    subject: str,
    full_context: str,
    candidate: dict,
) -> list[dict]:
    """Build the message list for the stage-2 (decision body) LLM call.
    `subject` is a repo name or track topic (see build_stage1_messages)."""
    c = json.dumps(candidate, ensure_ascii=False)
    return [
        {"role": "system", "content": _STAGE2_SYS.format(subject=subject)},
        {"role": "user", "content": f"# Chosen decision\n{c}\n\n# Full project context\n{full_context}"},
    ]


def build_critique_messages(
    subject: str,
    draft: str,
    full_context: str,
) -> list[dict]:
    """Stage-3 self-critique → rewrite of a stage-2 draft, grounded in context."""
    return [
        {"role": "system", "content": _CRITIQUE_SYS.format(subject=subject)},
        {"role": "user", "content":
            f"# Draft decision entry to improve\n{draft}\n\n"
            f"# Grounding context (cite these; reject claims not supported here)\n{full_context}"},
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
    subject_label: str = "Repo",
) -> str:
    """Format a completed decision entry for the decision log. `repo` is the
    subject name (a repo in repo mode, a track name in track mode);
    `subject_label` is the bold label for it ("Repo" or "Track")."""
    first = next(
        (ln.strip(" #*-") for ln in body.splitlines() if ln.strip()),
        "untitled",
    )
    title = first[:80]
    return (
        f"## {date} — Decision #{n}: {title}\n"
        f"- **{subject_label}:** {repo} · **Models:** stage1 {s1} · stage2 {s2}\n"
        f"- **Context snapshot:** HEAD {head}, {open_issues} open issues\n\n"
        f"{body.rstrip()}\n\n"
    )


# ---------------------------------------------------------------------------
# Flat-cost windowing — the PURPOSE.md research bet ("near-flat cost while
# history compounds"). Stage-1 already uses titles only; stage-2 must NOT inject
# the whole ever-growing decision log, or cost/decision climbs linearly with
# history. `window_log` keeps the last N full entries verbatim and collapses the
# older prefix to a one-line marker, so the stage-2 prompt is O(1) in log size
# past N. Maps nullclaw's compaction.zig keep_recent (issue #57).
# ---------------------------------------------------------------------------

_DECISION_HDR_RE = re.compile(
    r"^##\s+(?P<date>\S+)\s+—\s+Decision\s+#(?P<n>\d+):", re.M)


def window_log(text: str, keep_recent: int = 20) -> str:
    """Bound a decision-log's text so its length is O(1) in history size.

    Splits ``text`` into its leading preamble + one block per ``## … Decision
    #N: …`` header (the format `format_entry` emits), keeps the last
    ``keep_recent`` blocks verbatim, and replaces the older prefix with a single
    summary line (count + the elided ``#lo–#hi`` span). A log with at most
    ``keep_recent`` entries is returned unchanged. The kept blocks dominate the
    output, so length stops growing with history once past the window."""
    if not text or keep_recent < 0:
        return text
    # Split ONLY at real decision headers (not any `## ` — a body may contain
    # markdown sub-headers), so blocks == decisions and the count is exact.
    parts = re.split(r"(?m)^(?=##\s+\S+\s+—\s+Decision\s+#\d+:)", text)
    head, blocks = parts[0], parts[1:]
    if len(blocks) <= keep_recent:
        return text
    elided = blocks[:-keep_recent] if keep_recent else blocks
    kept = blocks[-keep_recent:] if keep_recent else []
    nums = [int(m.group("n")) for b in elided
            for m in [_DECISION_HDR_RE.match(b)] if m]
    span = (f" (#{min(nums)}–#{max(nums)})" if nums else "")
    summary = (
        f"## [{len(elided)} earlier decisions elided{span}]\n"
        f"- Older full entries omitted to keep stage-2 prompt cost flat; "
        f"their titles remain in the stage-1 context.\n\n")
    return head + summary + "".join(kept)


# ---------------------------------------------------------------------------
# Task 6 — Dashboard rendering
# ---------------------------------------------------------------------------


def _bar(frac: float, width: int = 20) -> str:
    """Render an ASCII progress bar."""
    frac = max(0.0, min(1.0, frac))
    fill = round(frac * width)
    return "[" + "#" * fill + "-" * (width - fill) + "]"


def render_dashboard(
    status: dict | None,
    now_epoch: int,
    last_step_epoch: int,
) -> str:
    """Render a text dashboard for the ralph supervisor status."""
    if not status:
        return "ralph — no supervisor running (status.json missing or empty)\n"

    current = status.get("current", "?")
    iteration = status.get("iteration", 0)
    total = float(status.get("total_cost", 0))
    budget = float(status.get("budget_total", 0)) or 1e-9
    running = status.get("running", False)
    dot = "●" if running else "○"
    since = max(0, now_epoch - last_step_epoch)

    lines: list[str] = [
        f"ralph eye  {dot}  current={current}  iter={iteration}  ({since}s since last step)",
        f"spend  ${total:.4f} / ${budget:.2f}  {_bar(total / budget)}",
        "",
    ]

    # Subject table — tracks (primary) or repos (deprecated). Track status
    # carries a per-subject model; repo status doesn't (shows "-").
    is_tracks = bool(status.get("subjects") or status.get("tracks"))
    subjects: dict = status.get("subjects") or status.get("tracks") or status.get("repos", {})
    label = "track" if is_tracks else "repo"
    lines.append("%-18s %-30s %5s  %-30s %8s" % (label, "model", "n", "last decision", "cost$"))
    for name in sorted(subjects):
        info = subjects[name]
        lines.append(
            "%-18s %-30.30s %5d  %-30.30s %8.4f"
            % (
                name,
                info.get("model", "-"),
                int(info.get("entries", 0)),
                info.get("last_title", ""),
                float(info.get("cost", 0)),
            )
        )

    recent: list[dict] = status.get("recent", [])
    if recent:
        lines.append("")
        lines.append("recent decisions:")
        for entry in recent[:5]:
            subj = entry.get("subject") or entry.get("repo", "?")
            lines.append(f"  [{subj}] {entry.get('date', '?')} — {entry.get('title', '?')}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# M1 (flow driver) — immutable hash-chained event log + live control state.
#   * The event log is the driver's state-of-record (status.json becomes a
#     derived cache). Append-only; each entry hash-chains the previous so the
#     run history is tamper-evident and replayable (the "immutable" theory).
#   * Control state is read live each tick from a control file (the "control"
#     theory: pause/resume, slow, step without restarting the driver).
# ---------------------------------------------------------------------------

import hashlib

GENESIS_HASH = "0" * 64


def _canon(payload: dict) -> str:
    """Canonical JSON of a payload (sorted keys, compact) — the bytes hashed."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def chain_hash(prev_hex: str, payload: dict) -> str:
    """sha256(prev_hash || canonical(payload)) — the link function."""
    return hashlib.sha256((prev_hex + _canon(payload)).encode("utf-8")).hexdigest()


def make_entry(prev_hex: str, seq: int, payload: dict) -> dict:
    """One hash-chained log entry. `prev_hex` is GENESIS_HASH for seq 0."""
    return {"seq": seq, "prev": prev_hex, "payload": payload,
            "hash": chain_hash(prev_hex, payload)}


def verify_chain(entries: list[dict]) -> bool:
    """True iff `entries` is a contiguous, untampered chain from genesis:
    seq is 0,1,2,…; each `prev` links the prior `hash`; each `hash` recomputes."""
    prev = GENESIS_HASH
    for i, e in enumerate(entries):
        if e.get("seq") != i:
            return False
        if e.get("prev") != prev:
            return False
        if e.get("hash") != chain_hash(prev, e.get("payload", {})):
            return False
        prev = e["hash"]
    return True


def longest_valid_prefix(entries: list[dict]) -> list[dict]:
    """The longest contiguous, untampered chain prefix of already-parsed
    ``entries`` — stops at the first entry whose seq/prev/hash breaks the chain.
    The boot-recovery counterpart of ``verify_chain``: a torn-tail crash leaves
    a valid prefix + an unverifiable suffix, and this returns the prefix."""
    out: list[dict] = []
    prev = GENESIS_HASH
    for i, e in enumerate(entries):
        if (e.get("seq") != i or e.get("prev") != prev
                or e.get("hash") != chain_hash(prev, e.get("payload", {}))):
            break
        out.append(e)
        prev = e["hash"]
    return out


@dataclass(frozen=True)
class Control:
    """Live driver control, read each tick. `interval=None` ⇒ use CLI default.
    `step` is one-shot: run a single tick even while paused, then stay paused."""
    paused: bool = False
    interval: float | None = None
    step: bool = False


def parse_control(d: dict | None) -> Control:
    """Normalize a control file dict into a Control (missing/empty ⇒ defaults)."""
    if not d:
        return Control()
    iv = d.get("interval")
    return Control(
        paused=bool(d.get("paused", False)),
        interval=float(iv) if iv is not None else None,
        step=bool(d.get("step", False)),
    )


# ---------------------------------------------------------------------------
# Ratify workflow — the human-in-the-loop leg. A ratification is a SEPARATE
# append (decision entries are never edited), so each verdict is one line in
# docs/decisions/<track>.ratify-log.md:
#   - <track>#<N> — **ratify** | **override** | **defer** — <reason> — @handle YYYY-MM-DD
# ---------------------------------------------------------------------------

_RATIFY_RE = re.compile(
    r"^-\s*(?P<id>[A-Za-z0-9._-]+#\d+)\s*—\s*"
    r"\*\*(?P<verdict>ratify|override|defer)\*\*\s*—\s*"
    r"(?P<reason>.+?)\s*—\s*@\S+\s+\d{4}-\d{2}-\d{2}\s*$"
)


def parse_ratify_line(line: str) -> "dict | None":
    """Parse one ratification line into ``{id, verdict, reason, score}`` —
    ``ratify`` → score 1, ``override``/``defer`` → 0 — or None if malformed."""
    m = _RATIFY_RE.match(line.strip())
    if not m:
        return None
    verdict = m.group("verdict")
    return {
        "id": m.group("id"),
        "verdict": verdict,
        "reason": m.group("reason").strip(),
        "score": 1 if verdict == "ratify" else 0,
    }


def ratify_rate(verdicts: list[str]) -> "float | None":
    """Ratify-rate = ratified / (ratified + overridden). ``defer`` is not yet
    acted on, so it's excluded from the denominator. None if nothing acted."""
    acted = [v for v in verdicts if v in ("ratify", "override")]
    if not acted:
        return None
    return sum(1 for v in acted if v == "ratify") / len(acted)
