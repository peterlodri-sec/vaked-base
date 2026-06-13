#!/usr/bin/env python3
"""test_agentfield_lowering.py — the SECOND frozen lowering golden.

`vaked/examples/lowering/` freezes `operator-field.vaked` (fibers / indexes /
surface / parallel). It does NOT exercise the runtime-plane + deployment
emitters added later — `workflow.spec`, `memory.store`, `eventd.config`,
`otp.supervision`, `colmena.hive` — which had only structural unit tests.

This module freezes `vaked/examples/agentfield-swe.vaked` (the daily-use target
system) byte-for-byte, so those emitters gain the same #15 Zig-port parity
contract: same validated graph ⇒ byte-identical artifacts + manifest. A change
to any of those emitters must regenerate this golden deliberately, exactly like
the operator-field one.

Three checks (mirroring test_vakedc_lower's golden discipline):
1. Golden tree — lower the example and byte-compare EVERY emitted file against
   `vaked/examples/lowering-agentfield/`.
2. Determinism — two lowers produce byte-identical trees.
3. Emitter coverage — assert the new emitters are actually present (guards
   against silently dropping one and the golden going stale-but-passing).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)

from vakedc.parser import parse_source     # noqa: E402
from vakedc.resolve import build_graph      # noqa: E402
from vakedc import lower as lower_mod        # noqa: E402

EXAMPLE = os.path.join(REPO, "vaked", "examples", "agentfield-swe.vaked")
EXAMPLE_REL = "vaked/examples/agentfield-swe.vaked"
GOLDEN_DIR = os.path.join(REPO, "vaked", "examples", "lowering-agentfield")

# emitters this golden exists to lock (absent from the operator-field golden).
_REQUIRED_EMITTERS = {
    "workflow.spec", "memory.store", "eventd.config", "otp.supervision",
    "colmena.hive",
}


def _lower():
    src = open(EXAMPLE, encoding="utf-8").read()
    items = parse_source(src, EXAMPLE_REL)
    graph = build_graph(items, EXAMPLE_REL)
    result = lower_mod.lower(graph, items)
    tree = dict(result.files)
    tree["provenance.json"] = lower_mod.provenance_json_text(result.provenance)
    return tree, result


def _disk_tree():
    out = {}
    for root, _d, names in os.walk(GOLDEN_DIR):
        for n in names:
            full = os.path.join(root, n)
            rel = os.path.relpath(full, GOLDEN_DIR).replace(os.sep, "/")
            out[rel] = open(full, encoding="utf-8").read()
    return out


def _test_golden_tree(lines):
    ok = True
    emitted, _ = _lower()
    disk = _disk_tree()
    if set(emitted) != set(disk):
        ok = False
        miss = sorted(set(disk) - set(emitted))
        extra = sorted(set(emitted) - set(disk))
        if miss:
            lines.append(f"  FAIL golden: not emitted: {miss}")
        if extra:
            lines.append(f"  FAIL golden: emitted but not a fixture: {extra}")
    n = 0
    for rel in sorted(set(emitted) & set(disk)):
        got = emitted[rel]
        if isinstance(got, bytes):
            got = got.decode("utf-8")
        if got == disk[rel]:
            n += 1
            continue
        ok = False
        at = next((i for i, (a, b) in enumerate(zip(got, disk[rel]))
                   if a != b), min(len(got), len(disk[rel])))
        lines.append(f"  FAIL golden: {rel} differs at byte {at} "
                     f"(emitted {len(got)}B vs fixture {len(disk[rel])}B)")
    if ok:
        lines.append(f"  golden tree: {n} files byte-identical to "
                     f"lowering-agentfield/")
    return ok


def _test_determinism(lines):
    t1, _ = _lower()
    t2, _ = _lower()
    if t1 != t2:
        lines.append("  FAIL determinism: two lowers differ")
        return False
    lines.append(f"  determinism: {len(t1)} files byte-identical across lowers")
    return True


def _test_emitter_coverage(lines):
    _, result = _lower()
    seen = {e.emitter for e in result.entries}
    missing = sorted(_REQUIRED_EMITTERS - seen)
    if missing:
        lines.append(f"  FAIL coverage: golden no longer exercises {missing}")
        return False
    lines.append(f"  emitter coverage: all {len(_REQUIRED_EMITTERS)} "
                 f"runtime-plane/deploy emitters present")
    return True


def run():
    lines = []
    ok = True
    for fn in (_test_golden_tree, _test_determinism, _test_emitter_coverage):
        try:
            ok = fn(lines) and ok
        except Exception as e:
            import traceback
            ok = False
            lines.append(f"    ERROR in {fn.__name__}: {type(e).__name__}: {e}")
            lines.append(traceback.format_exc())
    return ok, lines


if __name__ == "__main__":
    ok, lines = run()
    print("== test_agentfield_lowering ==")
    for ln in lines:
        print(ln)
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
