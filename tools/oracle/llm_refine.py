"""Refine Ghidra pseudo-C into source-like C via llm4decompile-6.7B on llama-server.

The prompt template follows the llm4decompile decompile-refine convention; confirm
the exact wording against the chosen GGUF's model card at implementation time
(open item in the spec). build_prompt/parse_completion are pure and tested; refine()
is the thin HTTP runner (integration-verified on dev-cx53 with llama-server up).
"""
from __future__ import annotations

import json
import urllib.request

# llm4decompile refine template: pseudo-C in, source C out.
PROMPT_PREFIX = "# This is the decompiled pseudo-code:\n"
PROMPT_SUFFIX = "\n# What is the original source code?\n"

DEFAULT_SERVER = "http://127.0.0.1:8080/completion"  # llama-server native endpoint


def build_prompt(pseudo_c: str) -> str:
    return f"{PROMPT_PREFIX}{pseudo_c}{PROMPT_SUFFIX}"


def parse_completion(resp: dict) -> str:
    """Extract generated text from a llama.cpp /completion response."""
    return resp["content"]


def refine(pseudo_c: str, *, server: str = DEFAULT_SERVER, n_predict: int = 1024,
           timeout: float = 600.0) -> str:
    """POST to llama-server, temperature=0 for determinism. Impure."""
    body = json.dumps({
        "prompt": build_prompt(pseudo_c),
        "temperature": 0,
        "n_predict": n_predict,
        "stop": ["# This is", "# What is"],
    }).encode()
    req = urllib.request.Request(server, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_completion(json.loads(r.read().decode())).strip()
