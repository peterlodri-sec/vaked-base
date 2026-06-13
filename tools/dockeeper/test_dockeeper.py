#!/usr/bin/env python3
"""Stdlib tests for doc-keeper. Run: python3 tools/dockeeper/test_dockeeper.py"""
import os
import tempfile
import unittest

import dockeeper as dk


def _w(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


class RfcRefs(unittest.TestCase):
    def test_in_range_gap_is_error_beyond_is_warn(self):
        with tempfile.TemporaryDirectory() as root:
            _w(root, "protocol/rfcs/0001-a.md", "# A\n")
            _w(root, "protocol/rfcs/0003-c.md", "# C\n")  # max existing = 3
            f = _w(root, "protocol/x.md", "see RFC 0001, RFC 0002, and RFC 0009\n")
            errs, warns = dk.check_rfc_refs(root, [f])
            self.assertEqual([e[2].split()[1] for e in errs], ["0002"])  # in-range gap
            self.assertEqual([w[2].split()[1] for w in warns], ["0009"])  # forward ref

    def test_external_rfc_numbers_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            _w(root, "protocol/rfcs/0001-a.md", "# A\n")
            f = _w(root, "protocol/x.md", "per RFC 9110 (HTTP semantics)\n")
            errs, warns = dk.check_rfc_refs(root, [f])
            self.assertEqual((errs, warns), ([], []))  # no leading zero → not ours


class PathRefs(unittest.TestCase):
    def test_resolves_vs_dangling_vs_template(self):
        with tempfile.TemporaryDirectory() as root:
            _w(root, "vakedc/lower.py", "x = 1\n")
            _w(root, "docs/language/0012-lowering.md", "# lowering\n")  # design doc exists
            f = _w(
                root,
                "README.md",
                "real `vakedc/lower.py`; dead `vakedc/ghost.rs`; tmpl `vakedc/<name>/x.py`; "
                "example `src/auth.rs:42`; design `0012-lowering.md`\n",
            )
            msgs = " ".join(e[2] for e in dk.check_path_refs(root, [f]))
            self.assertIn("vakedc/ghost.rs", msgs)       # top-dir exists, file missing → flagged
            self.assertNotIn("vakedc/lower.py", msgs)    # resolves
            self.assertNotIn("<name>", msgs)             # template excluded
            self.assertNotIn("src/auth.rs", msgs)        # 'src' not a top-level dir
            self.assertNotIn("0012-lowering.md", msgs)   # design doc resolves by tree search
            # a design-doc ref that truly doesn't exist IS flagged:
            f2 = _w(root, "docs/x.md", "see `9999-nope.md`\n")
            self.assertIn("9999-nope.md", " ".join(e[2] for e in dk.check_path_refs(root, [f2])))

    def test_forward_looking_dirs_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            f = _w(root, "docs/superpowers/plans/p.md", "will create `tools/future/thing.rs`\n")
            self.assertEqual(dk.check_path_refs(root, [f]), [])


class StubFreshness(unittest.TestCase):
    def test_flags_stub_readme_with_code(self):
        with tempfile.TemporaryDirectory() as root:
            _w(root, "daemons/README.md", "Currently empty — slot for daemons.\n")
            _w(root, "daemons/eventd/main.zig", "pub fn main() void {}\n")
            warns = dk.check_stub_freshness(root)
            self.assertTrue(any("daemons" in w[2] for w in warns))

    def test_clean_stub_not_flagged(self):
        with tempfile.TemporaryDirectory() as root:
            _w(root, "daemons/README.md", "Currently empty — slot for daemons.\n")
            _w(root, "daemons/.gitkeep", "")
            self.assertEqual(dk.check_stub_freshness(root), [])


if __name__ == "__main__":
    unittest.main()
