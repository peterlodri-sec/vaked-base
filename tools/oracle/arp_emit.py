"""arp_emit — emit oracle findings as typed `arp_event` Vaked declarations.

One `arp_event` per reverse-engineered function, appended to a dedicated ARP trace
(`docs/oracle/arp-trace.md`), verifiable via `vakedc check` (tools/arp/verify_log.py).
The oracle is a one-way PRODUCER of arp_event blocks conforming to the builtin
`arp_event` schema — it never touches the execution ARP IR. Pure stdlib.
"""
from __future__ import annotations

import hashlib
import os
import re


def _slug(name, refined_c):
    base = re.sub(r"\W", "_", name)
    h = hashlib.sha256((refined_c or "").encode()).hexdigest()[:12]
    return "oracle_%s_%s" % (base, h)


def _status(score):
    if score is None:
        return "no-ground-truth"
    if score < 0.4:
        return "low-fidelity"
    return "ok"


def _vstr(s):
    return '"%s"' % str(s).replace("\\", "\\\\").replace('"', '\\"')


def _vlist(xs):
    return "[" + ", ".join(_vstr(x) for x in xs) + "]"


def finding_to_events(finding):
    """One arp_event dict per analyzed function in the finding."""
    tgt = (finding.get("target") or {}).get("path", "?")
    out = []
    for fe in finding.get("functions", []):
        name = fe.get("name", "?")
        rc = fe.get("refined_c")
        score = (fe.get("fidelity") or {}).get("score")
        refined_sha = hashlib.sha256((rc or "").encode()).hexdigest()[:12] if rc else "none"
        out.append({
            "slug": _slug(name, rc),
            "command": "oracle RE %s" % name,
            "inputs": [tgt, name],
            "outputs": ["refined_sha:%s" % refined_sha,
                        "fidelity:%s" % ("none" if score is None else score)],
            "status": _status(score),
        })
    return out


def render_arp_block(ev, *, ts):
    """The fenced ```vaked arp_event block for one event. Slug is an IDENT (unquoted)."""
    lines = ["```vaked", "arp_event %s {" % ev["slug"],
             "  ts      = %s" % _vstr(ts),
             "  command = %s" % _vstr(ev["command"])]
    if ev.get("inputs"):
        lines.append("  inputs  = %s" % _vlist(ev["inputs"]))
    if ev.get("outputs"):
        lines.append("  outputs = %s" % _vlist(ev["outputs"]))
    lines.append("  status  = %s" % _vstr(ev["status"]))
    lines += ["}", "```", ""]
    return "\n".join(lines)


_HEADER = ("# vaked-oracle ARP trace\n\nPer-function `arp_event` declarations emitted from "
           "oracle findings (`tools/oracle/arp_emit.py`). Verify: "
           "`python3 tools/arp/verify_log.py docs/oracle/arp-trace.md`.\n\n")


def emit(finding, *, path, ts):
    """Append one `## ts — command` heading + arp_event block per function. Header once."""
    events = finding_to_events(finding)
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write(_HEADER)
        for ev in events:
            f.write("## %s — %s\n\n%s\n" % (ts, ev["command"], render_arp_block(ev, ts=ts)))
    return len(events)
