#!/usr/bin/env python3
"""Smoke suite — 3 fast tests that must always pass (<60s).

  grammar_selfcontained   EBNF is self-contained (no external refs)
  examples_parse          every vaked/ example derives from the grammar
  doc_links               all RFC/doc cross-links resolve

Run from the repo root:
    python3 tests/smoke.py
"""
import os
import sys
import time

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec")
sys.path.insert(0, HERE)

import test_grammar_selfcontained as t_grammar
import test_examples_parse as t_examples
import test_doc_links as t_links

MODULES = [
    ("grammar_selfcontained", t_grammar),
    ("examples_parse",        t_examples),
    ("doc_links",             t_links),
]


def main():
    print("=" * 60)
    print("Vaked smoke suite — tests/smoke.py")
    print("=" * 60)

    results = []
    for name, mod in MODULES:
        t0 = time.time()
        try:
            ok, lines = mod.run()
            err = None
        except Exception as e:
            ok, lines, err = False, [], f"{type(e).__name__}: {e}"
        dt = time.time() - t0

        print(f"\n## {name}")
        for ln in lines:
            print(ln)
        if err:
            print(f"  ERROR: {err}")
        print(f"  ({'PASS' if ok else 'FAIL'} in {dt * 1000:.0f} ms)")
        results.append((name, ok, dt))

    print("\n" + "=" * 60)
    n_pass = sum(1 for _, ok, _ in results if ok)
    all_ok = n_pass == len(results)
    for name, ok, dt in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  ({dt * 1000:.0f} ms)")
    print(f"\n  {n_pass}/{len(results)} passed — {'SMOKE GREEN' if all_ok else 'SMOKE RED'}")
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
