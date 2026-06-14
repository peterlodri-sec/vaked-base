#!/usr/bin/env python3
"""test_float_repr — guard the float-repr conformance corpus against Python drift.

The Zig canonical writer (`json_canon.writeFloat`) must reproduce
`json.dumps(x, ensure_ascii=False)` byte-for-byte. The shared contract lives in
``tests/spec/float_repr_corpus.txt`` (also inlined in the Zig test). This module
asserts that the *running* Python's ``json.dumps`` still produces each expected
string — so if a future Python changes float formatting, this fails here rather
than silently diverging from the Zig side.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "float_repr_corpus.txt")


def _pairs():
    with open(CORPUS, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line or line.lstrip().startswith("#"):
                continue
            value_str, expected = line.split("\t", 1)
            yield value_str, expected


def run():
    lines = []
    ok = True
    n = 0
    for value_str, expected in _pairs():
        got = json.dumps(float(value_str), ensure_ascii=False)
        n += 1
        if got != expected:
            ok = False
            lines.append(f"  MISMATCH {value_str!r}: python={got!r} expected={expected!r}")
    lines.append(f"  {n} float-repr pairs checked against json.dumps "
                 f"({'all match' if ok else 'MISMATCHES present'})")
    return ok, lines


if __name__ == "__main__":
    ok, lines = run()
    print("\n".join(lines))
    raise SystemExit(0 if ok else 1)
