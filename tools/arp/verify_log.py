#!/usr/bin/env python3
"""Extract ```vaked blocks from a markdown file, concat to a temp .vaked, run vakedc check.

Exit 0 = every block parses + checks against builtins (incl. schema arp_event).
This is the dogfood gate: Vaked validates its own ARP session log.
"""
import os
import re
import subprocess
import sys
import tempfile

_FENCE = re.compile(r"```vaked\n(.*?)```", re.S)


def extract(md: str) -> list[str]:
    return [b.strip() for b in _FENCE.findall(md)]


def main(argv: list[str]) -> int:
    path = argv[0] if argv else "docs/arp-log.md"
    with open(path, encoding="utf-8") as fh:
        blocks = extract(fh.read())
    if not blocks:
        print("verify_log: no vaked blocks found")
        return 0
    src = "\n\n".join(blocks) + "\n"
    fd, tmp = tempfile.mkstemp(suffix=".vaked")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(src)
        r = subprocess.run([sys.executable, "-m", "vakedc", "check", tmp])
        return r.returncode
    finally:
        os.unlink(tmp)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
