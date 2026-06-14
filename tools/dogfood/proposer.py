"""dogfood.proposer — the PROPOSER half of the proposer/judge split.

A proposer mutates the in-scope working tree in place and returns its
*declared effects* (what it claims it changed). The kernel (the judge) then
checks those claims against the actual filesystem diff and the capability scope,
and only accepts a replay-stable transition.

Two proposers:

* ``stub_propose`` — deterministic, no model. Applies a caller-supplied edit map
  and returns a caller-supplied declared set. Lets the test suite force the
  negative cases (out-of-scope write, declared != actual) without a model.
* ``opencode_propose`` — runs ``opencode`` headless, driven by a local Ollama
  model, inside the tree. opencode edits files; we let the kernel derive actual
  effects from the filesystem (declared defaults to actual until Frida (M3)
  supplies independent observed effects). Requires opencode configured for the
  local Ollama provider — see README.
"""
from __future__ import annotations

import os
import subprocess


def stub_propose(root: str, edits: dict[str, "str | None"],
                 declared: dict | None = None) -> dict:
    """Apply ``edits`` ({rel: content} to write, {rel: None} to delete) under
    ``root``. Returns declared effects (``declared`` override, else the edits).
    """
    writes, deletes = [], []
    for rel, content in edits.items():
        full = os.path.join(root, rel)
        if content is None:
            if os.path.exists(full):
                os.remove(full)
            deletes.append(rel)
        else:
            os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            writes.append(rel)
    if declared is not None:
        return {"writes": sorted(declared.get("writes", [])),
                "deletes": sorted(declared.get("deletes", []))}
    return {"writes": sorted(writes), "deletes": sorted(deletes)}


def opencode_propose(root: str, intent: str, *,
                     model: str | None = None, timeout: int = 600) -> dict | None:
    """Run opencode headless in ``root`` to enact ``intent``. Returns ``None``
    declared effects (⇒ the kernel sets declared = actual). Raises on a non-zero
    opencode exit so a failed proposal never silently becomes an empty one.

    Model selection: ``model`` arg, else ``$DOGFOOD_OPENCODE_MODEL``. opencode
    must already be configured to reach the local Ollama OpenAI-compatible
    endpoint (see README — provider config + OLLAMA base url).
    """
    model = model or os.environ.get("DOGFOOD_OPENCODE_MODEL")
    cmd = ["opencode", "run"]
    if model:
        cmd += ["--model", model]
    cmd += [intent]
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                          timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"opencode exited {proc.returncode}: {proc.stderr.strip()[:400]}")
    return None   # declared unknown ⇒ kernel uses actual filesystem diff
