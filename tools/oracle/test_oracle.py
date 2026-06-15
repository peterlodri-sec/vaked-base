#!/usr/bin/env python3
"""vaked-oracle unit tests (stdlib only; run: python3 tools/oracle/test_oracle.py)."""
import os
import sys

# allow `import schema` etc. when run from repo root or tools/oracle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# --- tests are added below by later tasks ---


if __name__ == "__main__":
    def _run():
        tests = sorted((n, f) for n, f in dict(globals()).items()
                       if n.startswith("test_") and callable(f))
        passed = failed = 0
        for name, fn in tests:
            try:
                fn()
                print(f"PASS  {name}")
                passed += 1
            except Exception as e:
                print(f"FAIL  {name}: {type(e).__name__}: {e}")
                failed += 1
        print(f"\n{passed} passed, {failed} failed")
        return 1 if failed else 0
    raise SystemExit(_run())
