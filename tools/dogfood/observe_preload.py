"""dogfood.observe_preload — run a command under the LD_PRELOAD observer and emit
the observed_effects record (Linux/glibc only; validated on dev-cx53).

Companion to observe_preload.c. Sets LD_PRELOAD + DOGFOOD_OBSERVE_LOG, runs the
command in the repo root, then folds the shim's append-only log into the
``observed_effects`` shape the dogfood kernel's declared-vs-observed gate consumes
(identical shape to observe_frida.py). Advisory/evidence-only — LD_PRELOAD is
bypassable; the real boundary is L2 (eBPF/seccomp).

Build the .so first (on the Linux box):
  clang -shared -fPIC -O2 -o observe_preload.so observe_preload.c -ldl
Use:
  python3 observe_preload.py --so ./observe_preload.so --out /tmp/observed.json -- \\
      <command that applies the transition>
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile


def observe(so: str, cmd: list[str], cwd: str) -> dict:
    root = os.path.abspath(cwd)
    fd, logpath = tempfile.mkstemp(prefix="dogfood-obs-", suffix=".log")
    os.close(fd)
    try:
        env = {**os.environ, "LD_PRELOAD": os.path.abspath(so),
               "DOGFOOD_OBSERVE_LOG": logpath}
        subprocess.run(cmd, cwd=root, env=env, check=False)
        writes: set[str] = set()
        deletes: set[str] = set()
        with open(logpath, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "\t" not in line:
                    continue
                kind, path = line.rstrip("\n").split("\t", 1)
                rel = _rel(root, path)
                if rel is None or rel.startswith(".git") or rel.startswith(".dogfood"):
                    continue
                (writes if kind == "W" else deletes).add(rel)
        return {"writes": sorted(writes), "deletes": sorted(deletes)}
    finally:
        os.unlink(logpath)


def _rel(root: str, path: str) -> "str | None":
    ap = os.path.abspath(os.path.join(root, path))
    if ap == root or ap.startswith(root + os.sep):
        return os.path.relpath(ap, root)
    return None   # outside the repo — not part of the tree under judgement


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observe_preload")
    ap.add_argument("--so", required=True, help="path to observe_preload.so")
    ap.add_argument("--cwd", default=".")
    ap.add_argument("--out", help="write observed_effects JSON here (else stdout)")
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="-- command to observe")
    args = ap.parse_args(argv)
    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd
    if not cmd:
        ap.error("provide a command after --")
    observed = observe(args.so, cmd, args.cwd)
    out = json.dumps(observed, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
