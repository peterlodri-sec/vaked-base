import importlib.util
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


_HOOK = os.path.join(ROOT, ".claude", "hooks", "arp_log.py")


def _load_hook():
    import importlib.util
    spec = importlib.util.spec_from_file_location("arp_log", _HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class HookHelpersTest(unittest.TestCase):
    def setUp(self):
        self.h = _load_hook()

    def test_is_substantial(self):
        h = self.h
        self.assertTrue(h.is_substantial("python3 build.py"))
        self.assertTrue(h.is_substantial("make test"))
        self.assertFalse(h.is_substantial("ls -la"))
        self.assertFalse(h.is_substantial("git status"))
        self.assertFalse(h.is_substantial("cat foo.txt"))
        self.assertFalse(h.is_substantial("python3 -m vakedc check x.vaked"))
        self.assertFalse(h.is_substantial(""))

    def test_extract_inputs(self):
        self.assertEqual(self.h.extract_inputs("cp src/a.txt dest/b.txt"),
                         ["src/a.txt", "dest/b.txt"])
        self.assertEqual(self.h.extract_inputs("echo hi"), [])

    def test_status_from_response(self):
        h = self.h
        self.assertEqual(h.status_from_response({"exit_code": 0}), "ok")
        self.assertEqual(h.status_from_response({}), "ok")
        self.assertTrue(h.status_from_response({"interrupted": True}).startswith("err"))
        self.assertTrue(
            h.status_from_response({"exit_code": 2, "stderr": "boom"}).startswith("err"))

    def test_render_block_validates(self):
        from tools.arp.verify_log import extract
        block = self.h.render_block("2026-06-15 10:30", "python3 build.py",
                                    ["build.py"], ["out/app"], "ok")
        blocks = extract(block)
        self.assertTrue(blocks, "render_block must emit a ```vaked fence")
        fd, tmp = tempfile.mkstemp(suffix=".vaked")
        os.close(fd)
        try:
            with open(tmp, "w") as fh:
                fh.write(blocks[0] + "\n")
            r = _run(["-m", "vakedc", "check", tmp])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            os.unlink(tmp)

    def test_render_block_multiline_command_validates(self):
        # multi-line commands (heredocs, ;-joined lines) must escape to a valid
        # single-line Vaked string, else vakedc check rejects the block.
        from tools.arp.verify_log import extract
        block = self.h.render_block(
            "2026-06-15 10:30",
            'python3 - <<EOF\nopen("x","w").write("hi")\nEOF',
            [], ["x"], "ok")
        blocks = extract(block)
        self.assertTrue(blocks)
        fd, tmp = tempfile.mkstemp(suffix=".vaked")
        os.close(fd)
        try:
            with open(tmp, "w") as fh:
                fh.write(blocks[0] + "\n")
            r = _run(["-m", "vakedc", "check", tmp])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            os.unlink(tmp)


class HookMainTest(unittest.TestCase):
    def _drive(self, command, gitmap):
        h = _load_hook()
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "docs"))
            log = os.path.join(d, "docs", "arp-log.md")
            with open(log, "w") as fh:
                fh.write("# ARP Event Log\n")
            payload = json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": command},
                "tool_response": {"exit_code": 0},
            })
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": d}), \
                 mock.patch.object(h, "git_status_map", lambda root: gitmap), \
                 mock.patch.object(h, "_load_stamp", lambda: {}), \
                 mock.patch.object(h, "_save_stamp", lambda m: None), \
                 mock.patch.object(sys, "stdin", io.StringIO(payload)):
                rc = h.main()
            with open(log) as fh:
                return rc, fh.read()

    def test_main_appends_for_substantial(self):
        rc, body = self._drive("python3 build.py src/main.py", {"out/app": "??"})
        self.assertEqual(rc, 0)
        self.assertIn("arp_event e_", body)
        self.assertIn('command = "python3 build.py src/main.py"', body)
        self.assertIn("out/app", body)

    def test_main_skips_trivial(self):
        rc, body = self._drive("ls -la", {})
        self.assertEqual(rc, 0)
        self.assertEqual(body, "# ARP Event Log\n")  # unchanged


if __name__ == "__main__":
    unittest.main()
