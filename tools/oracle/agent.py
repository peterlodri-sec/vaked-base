"""Agentic brain for the oracle loop — an LLM picks the next action (slice 3).

Replaces policy.next_action's fixed round-robin with an LLM decision over the same
bounded action set {decompile, refine, investigate, finalize}. Deterministic at the
action layer; the LLM only selects among recorded primitives. Any parse/validation
failure falls back to policy.next_action, so a flaky model can never derail or
unbound the loop. temperature=0 => replayable.
"""
from __future__ import annotations

import json
import os
import urllib.request

import policy

ACTIONS = ("decompile", "refine", "investigate", "finalize")


def build_prompt(state, *, threshold=0.75, max_refine=2) -> str:
    lines = ["You are a reverse-engineering planner. Pick ONE next action.",
             f"Functions under analysis: {state.functions}",
             "Current results (fn -> fidelity / refine_passes / has_dynamic):"]
    for fn in state.functions:
        r = state.results.get(fn)
        if r is None:
            lines.append(f"  {fn}: not yet decompiled")
        else:
            lines.append(f"  {fn}: fidelity={r.get('fidelity')} "
                         f"refine_passes={r.get('refine_passes', 0)} "
                         f"has_dynamic={bool(r.get('frida') or r.get('ebpf'))}")
    obs = getattr(state, "observations", []) or []
    if obs:
        lines.append("Recent investigations:")
        lines += [f"  {json.dumps(o)[:300]}" for o in obs[-5:]]
    lines.append(f"Budget: iter {state.iters}/{state.budget_iters}.")
    lines.append(f"Rules: decompile a function before refining it; refine only functions "
                 f"below fidelity {threshold} with < {max_refine} refine passes; use "
                 f"investigate to learn a function's signature/callers/refs; finalize when "
                 f"no useful action remains or budget is low.")
    lines.append('Reply with ONE JSON object only, e.g. '
                 '{"action":"decompile","fn":"NAME","rationale":"..."} or '
                 '{"action":"investigate","query":{"kind":"sym","name":"NAME"},"rationale":"..."} or '
                 '{"action":"finalize","rationale":"..."}. action in ' + str(list(ACTIONS)) + ".")
    return "\n".join(lines)


def parse_action(raw: str, state) -> dict:
    """Extract + validate the first JSON action object. Raises ValueError on any
    violation (caller falls back to the deterministic policy)."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in LLM reply")
    obj = json.loads(raw[start:end + 1])
    act = obj.get("action")
    if act not in ACTIONS:
        raise ValueError(f"action {act!r} not in {ACTIONS}")
    rationale = str(obj.get("rationale", ""))
    if act in ("decompile", "refine"):
        fn = obj.get("fn")
        if fn not in state.functions:
            raise ValueError(f"fn {fn!r} not in functions")
        return {"action": act, "fn": fn, "rationale": rationale}
    if act == "investigate":
        q = obj.get("query")
        if not isinstance(q, dict) or "kind" not in q or "name" not in q:
            raise ValueError("investigate needs query{kind,name}")
        return {"action": "investigate",
                "query": {"kind": str(q["kind"]), "name": str(q["name"])},
                "rationale": rationale}
    return {"action": "finalize", "rationale": rationale}


def make_policy(llm_call, *, model="?", threshold=0.75, max_refine=2):
    """decide(state) -> action using llm_call(prompt)->str. Deterministic fallback."""
    def decide(state):
        try:
            raw = llm_call(build_prompt(state, threshold=threshold, max_refine=max_refine))
            act = parse_action(raw, state)
            act["model"] = model
            return act
        except Exception:  # noqa: BLE001 — any failure => deterministic policy
            return policy.next_action(state)
    return decide


class LiteLLMClient:
    """Thin OpenAI-chat client for the local litellm gateway (revdev `oq`, :4000)."""

    def __init__(self, *, endpoint="http://127.0.0.1:4000/v1/chat/completions",
                 model="qwen2.5-coder:7b", key=None, timeout=120):
        self.endpoint, self.model = endpoint, model
        self.key = key or os.environ.get("LITELLM_KEY", "")
        self.timeout = timeout

    def __call__(self, prompt: str) -> str:
        body = json.dumps({"model": self.model, "temperature": 0,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(self.endpoint, data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {self.key}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 (loopback gateway)
            return json.load(r)["choices"][0]["message"]["content"]
