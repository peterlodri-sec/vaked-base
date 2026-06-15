"""panel.py — slice-4a reverser debate panel + judge (praetorian + anstetten).

Per function: a panel of diverse models (each a different OpenAIChatClient) independently
produces a candidate refined-C in parallel; the judge (anstetten) picks-or-merges.
Adaptive judge reasoning effort (the ~10x cost lever): easy/agreed/high-fidelity functions
skip the judge entirely. Pure stdlib (urllib + concurrent.futures). Graceful: a model
error drops only its candidate; the judge never crashes the round.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OUTSIDE_MODEL = "deepseek/deepseek-v4-flash"
REASONING_OUTSIDE_MODEL = "deepseek/deepseek-v4-pro"
FIDELITY_THRESHOLD = 0.75


class OpenAIChatClient:
    """OpenAI-chat client — local llama-server / ollama / litellm / OpenRouter, uniform."""

    def __init__(self, endpoint, model, key="", *, temperature=0,
                 reasoning_effort=None, extra_headers=None, timeout=180):
        self.endpoint, self.model, self.key = endpoint, model, key or ""
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.extra_headers = dict(extra_headers or {})
        self.timeout = timeout

    def _build_body(self, prompt, effort):
        body = {"model": self.model, "temperature": self.temperature,
                "messages": [{"role": "user", "content": prompt}]}
        if effort:
            body["reasoning"] = {"effort": effort}
        return body

    def __call__(self, prompt, *, reasoning_effort=None):
        eff = reasoning_effort if reasoning_effort is not None else self.reasoning_effort
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        headers.update(self.extra_headers)
        req = urllib.request.Request(self.endpoint, data=json.dumps(self._build_body(prompt, eff)).encode(),
                                     method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 (operator-configured endpoints)
            return json.load(r)["choices"][0]["message"]["content"]


@dataclass
class Panelist:
    name: str
    client: object   # callable(prompt) -> str


def candidate_prompt(fn, pseudo_c, context=""):
    parts = [f"Reverse-engineer the function `{fn}`. Below is decompiler pseudo-C.",
             "Rewrite it as clean, correct, idiomatic C. Reply with ONLY the C code, no prose."]
    if context:
        parts.append("Context (prior team knowledge / structural facts):\n" + context)
    parts.append("Pseudo-C:\n" + pseudo_c)
    return "\n\n".join(parts)


def run_panel(fn, pseudo_c, context, panelists, *, max_workers=4):
    """Parallel; one entry per panelist, sorted by name. Never raises (errors captured)."""
    def one(p):
        model = getattr(p.client, "model", None)
        try:
            return {"panelist": p.name, "model": model,
                    "refined_c": p.client(candidate_prompt(fn, pseudo_c, context)), "error": None}
        except Exception as e:  # noqa: BLE001
            return {"panelist": p.name, "model": model, "refined_c": None,
                    "error": f"{type(e).__name__}: {e}"[:200]}
    workers = max(1, min(max_workers, len(panelists) or 1))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        out = list(ex.map(one, panelists))
    return sorted(out, key=lambda d: d["panelist"])


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def select_effort(candidates, fidelities, *, threshold=FIDELITY_THRESHOLD):
    """none = skip judge (agreement / already-good); high = adjudicate; max = all weak."""
    texts = [c["refined_c"] for c in candidates if c.get("refined_c")]
    fids = [f for f in (fidelities or []) if f is not None]
    if not texts:
        return "none"
    if len({_norm(t) for t in texts}) == 1:    # panel agrees
        return "none"
    if fids and max(fids) >= threshold:         # already good enough
        return "none"
    if fids and max(fids) < 0.4:                # all weak -> think hard
        return "max"
    return "high"


def judge_prompt(fn, candidates, context=""):
    lines = [f"You are the judge. {len(candidates)} candidate reverse-engineerings of "
             f"`{fn}` follow. Pick the single best, or merge them into a better one.",
             'Reply with ONE JSON object: {"mode":"pick","index":<int>,"rationale":"..."} '
             'OR {"mode":"merge","refined_c":"<C>","drew_from":[<int>,...],"rationale":"..."}.']
    if context:
        lines.append("Context:\n" + context)
    for i, c in enumerate(candidates):
        lines.append(f"--- candidate {i} ({c['panelist']}) ---\n{c.get('refined_c') or '(none)'}")
    return "\n\n".join(lines)


def _best_candidate(candidates, fidelities):
    usable = [(i, c) for i, c in enumerate(candidates) if c.get("refined_c")]
    if not usable:
        return None
    def fid(i):
        return fidelities[i] if (fidelities and i < len(fidelities) and fidelities[i] is not None) else -1.0
    return max(usable, key=lambda ic: fid(ic[0]))[1]


def judge_candidates(fn, candidates, context, judge_client, *, effort="high", fidelities=None):
    usable = [c for c in candidates if c.get("refined_c")]
    if not usable:
        return {"mode": "empty", "index": None, "refined_c": "", "rationale": "no candidates",
                "drew_from": [], "effort": effort}
    try:
        raw = judge_client(judge_prompt(fn, candidates, context), reasoning_effort=effort)
        s, e = raw.find("{"), raw.rfind("}")
        if s < 0 or e <= s:
            raise ValueError("no JSON in judge reply")
        obj = json.loads(raw[s:e + 1])
        mode = obj.get("mode")
        if mode == "pick":
            idx = int(obj.get("index"))
            chosen = candidates[idx]
            if not chosen.get("refined_c"):
                raise ValueError("judge picked an empty candidate")
            return {"mode": "pick", "index": idx, "refined_c": chosen["refined_c"],
                    "rationale": str(obj.get("rationale", "")), "drew_from": [chosen["panelist"]],
                    "effort": effort}
        if mode == "merge":
            rc = obj.get("refined_c")
            if not rc:
                raise ValueError("merge without refined_c")
            drew = [candidates[i]["panelist"] for i in obj.get("drew_from", [])
                    if isinstance(i, int) and 0 <= i < len(candidates)]
            return {"mode": "merge", "index": None, "refined_c": rc,
                    "rationale": str(obj.get("rationale", "")), "drew_from": drew, "effort": effort}
        raise ValueError(f"bad judge mode {mode!r}")
    except Exception as ex:  # noqa: BLE001 — any judge failure -> deterministic fallback
        best = _best_candidate(candidates, fidelities) or usable[0]
        return {"mode": "fallback", "index": None, "refined_c": best["refined_c"],
                "rationale": f"judge fallback ({type(ex).__name__})", "drew_from": [best["panelist"]],
                "effort": effort}


def debate_function(fn, pseudo_c, context, panelists, judge_client, *,
                    score=None, ground_truth=None, max_workers=4):
    candidates = run_panel(fn, pseudo_c, context, panelists, max_workers=max_workers)
    fidelities = None
    if score and ground_truth is not None:
        fidelities = [score(c["refined_c"], ground_truth) if c.get("refined_c") else None
                      for c in candidates]
    effort = select_effort(candidates, fidelities)
    if effort == "none":                              # fast path — skip the judge LLM call
        best = _best_candidate(candidates, fidelities)
        chosen = best["refined_c"] if best else ""
        verdict = {"mode": "fast", "index": None, "refined_c": chosen,
                   "rationale": "fast-path: panel agreement or fidelity >= threshold",
                   "drew_from": [best["panelist"]] if best else [], "effort": "none"}
    else:
        verdict = judge_candidates(fn, candidates, context, judge_client,
                                   effort=effort, fidelities=fidelities)
        chosen = verdict["refined_c"]
    chosen_fid = score(chosen, ground_truth) if (score and ground_truth is not None and chosen) else None
    return {"candidates": candidates, "verdict": verdict, "chosen": chosen,
            "fidelity": chosen_fid, "effort": effort}


def load_roster(path):
    """Build (panelists, judge_client) from a roster JSON. key_env -> os.environ (drop +
    log if set-but-absent). A keyless judge falls back to the first available panelist."""
    spec = json.load(open(path))

    def build(e):
        key = ""
        if e.get("key_env"):
            key = os.environ.get(e["key_env"], "")
            if not key:
                print(f"panel: dropping {e.get('name')} — env {e['key_env']} not set", file=sys.stderr)
                return None
        return OpenAIChatClient(e["endpoint"], e["model"], key,
                                temperature=e.get("temperature", 0),
                                reasoning_effort=e.get("reasoning_effort"))
    panelists = []
    for e in spec.get("panelists", []):
        c = build(e)
        if c is not None:
            panelists.append(Panelist(name=e["name"], client=c))
    judge = build(spec["judge"]) if "judge" in spec else None
    if judge is None and panelists:
        judge = panelists[0].client
    return panelists, judge
