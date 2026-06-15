import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _run(args, **kw):
    return subprocess.run([sys.executable, *args], cwd=ROOT,
                          capture_output=True, text=True, **kw)


class VerifyLogTest(unittest.TestCase):
    def test_verify_log_extracts_and_checks(self):
        with tempfile.TemporaryDirectory() as d:
            md = os.path.join(d, "log.md")
            with open(md, "w") as fh:
                fh.write(
                    "# log\n\n## 2026-06-15 10:30 — build\n\n"
                    "```vaked\n"
                    "arp_event e_1 {\n"
                    '  ts = "2026-06-15 10:30"\n'
                    '  command = "python3 build.py"\n'
                    '  status = "ok"\n'
                    "}\n"
                    "```\n"
                )
            r = _run(["-m", "tools.arp.verify_log", md])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
