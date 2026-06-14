"""Standalone stdlib test runner for the dogfood verification kernel.

No pytest (matches tools/ralph/test_ralph.py discipline). Run:

    python3 tools/dogfood/test_kernel.py

Covers the four gates — capability (POLA), declared-vs-actual, observed>declared,
replay-stability — plus tamper detection, rollback-on-reject, and the
content-addressed hashing primitives. The negative cases are the point: they
exercise the ``used(p) ⊑ granted(p)`` use-check and effect-honesty gates that
are otherwise unimplemented on trunk.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import capability               # noqa: E402
import kernel                   # noqa: E402
import proposer as P            # noqa: E402
import transition as T          # noqa: E402
import wal as W                 # noqa: E402


# --- fixtures ---------------------------------------------------------------

def _sandbox():
    """A temp root with an in-scope 'sandbox/' dir holding one base file."""
    d = tempfile.mkdtemp(prefix="dogfood-test-")
    os.makedirs(os.path.join(d, "sandbox"))
    with open(os.path.join(d, "sandbox", "a.txt"), "w") as f:
        f.write("base\n")
    with open(os.path.join(d, "untouched.txt"), "w") as f:
        f.write("outside-base\n")
    return d


def _judge(root, scope, edits, *, declared=None, observed=None):
    return kernel.judge(
        root, scope, "test intent",
        lambda r, s, i: P.stub_propose(r, edits, declared),
        wal_path=os.path.join(".dogfood", "wal", "t.jsonl"),
        blobs_dir=os.path.join(".dogfood", "blobs"),
        observed=observed)


# --- capability unit tests --------------------------------------------------

def test_in_scope_prefix_boundary():
    assert capability.in_scope("tools/dogfood/x", ["tools/dogfood"])
    assert not capability.in_scope("tools/dogfood-evil/x", ["tools/dogfood"])


def test_in_scope_rejects_abs_and_traversal():
    assert not capability.in_scope("/etc/passwd", ["tools/dogfood"])
    assert not capability.in_scope("../secrets", ["tools/dogfood"])
    assert not capability.in_scope("tools/dogfood/../../etc", ["tools/dogfood"])


# --- hashing primitives -----------------------------------------------------

def test_tree_hash_order_independent():
    a = {"x": "1", "y": "2"}
    b = {"y": "2", "x": "1"}
    assert T.tree_hash(a) == T.tree_hash(b)
    assert T.tree_hash(a) != T.tree_hash({"x": "1", "y": "3"})


# --- the four gates ---------------------------------------------------------

def test_accept_in_scope_replay_stable():
    root = _sandbox()
    v = _judge(root, ["sandbox"], {"sandbox/a.txt": "changed\n"})
    assert v["accepted"], v["reasons"]
    assert v["replayed_state_hash"] == v["state_hash_after"]
    assert v["seq"] == 0                       # first WAL entry
    # file actually changed and persisted
    assert open(os.path.join(root, "sandbox", "a.txt")).read() == "changed\n"


def test_reject_out_of_scope_capability():
    root = _sandbox()
    v = _judge(root, ["sandbox"], {"outside.txt": "evil\n"})
    assert not v["accepted"]
    assert any("capability" in r for r in v["reasons"])
    # rolled back: the out-of-scope file is gone
    assert not os.path.exists(os.path.join(root, "outside.txt"))


def test_reject_declared_not_actual():
    root = _sandbox()
    v = _judge(root, ["sandbox"], {"sandbox/a.txt": "changed\n"},
               declared={"writes": ["sandbox/b.txt"]})
    assert not v["accepted"]
    assert any("declared!=actual" in r for r in v["reasons"])
    # rolled back to base
    assert open(os.path.join(root, "sandbox", "a.txt")).read() == "base\n"


def test_reject_observed_exceeds_declared():
    root = _sandbox()
    v = _judge(root, ["sandbox"], {"sandbox/a.txt": "changed\n"},
               observed={"writes": ["sandbox/a.txt", "sandbox/secret.key"]})
    assert not v["accepted"]
    assert any("observed>declared" in r for r in v["reasons"])


def test_observed_subset_accepts():
    root = _sandbox()
    v = _judge(root, ["sandbox"], {"sandbox/a.txt": "changed\n"},
               observed={"writes": ["sandbox/a.txt"]})
    assert v["accepted"], v["reasons"]


# --- replay gate (direct) ---------------------------------------------------

def test_replay_hash_deterministic_and_discriminating():
    blobs = tempfile.mkdtemp(prefix="dogfood-blobs-")
    # two post-images
    pa = os.path.join(blobs, "src_a"); open(pa, "w").write("AAA")
    pb = os.path.join(blobs, "src_b"); open(pb, "w").write("BBB")
    sha_a = T.store_blob(blobs, pa)
    sha_b = T.store_blob(blobs, pb)
    h1 = kernel._replay_state_hash({}, blobs, {"sandbox/x": sha_a}, [])
    h2 = kernel._replay_state_hash({}, blobs, {"sandbox/x": sha_a}, [])
    h3 = kernel._replay_state_hash({}, blobs, {"sandbox/x": sha_b}, [])
    assert h1 == h2          # deterministic
    assert h1 != h3          # discriminating: different content ⇒ different hash


# --- WAL: append + verify + tamper ------------------------------------------

def test_wal_append_and_verify():
    root = _sandbox()
    _judge(root, ["sandbox"], {"sandbox/a.txt": "v1\n"})
    _judge(root, ["sandbox"], {"sandbox/a.txt": "v2\n"})
    wal_path = os.path.join(root, ".dogfood", "wal", "t.jsonl")
    with W.EventLog(wal_path) as log:
        summary = W.replay_summary(log)
        assert len(log) == 2
    assert summary["transitions"] == 2


def test_wal_tamper_detected():
    root = _sandbox()
    _judge(root, ["sandbox"], {"sandbox/a.txt": "v1\n"})
    wal_path = os.path.join(root, ".dogfood", "wal", "t.jsonl")
    # corrupt the chain: flip a byte in the payload of the only entry
    lines = open(wal_path).read().splitlines()
    obj = json.loads(lines[0]); obj["payload"]["intent"] = "TAMPERED"
    open(wal_path, "w").write(json.dumps(obj) + "\n")
    raised = False
    try:
        W.EventLog(wal_path)
    except W.TamperError:
        raised = True
    assert raised, "tampered WAL must raise TamperError on open"


# --- git-mode rollback safety (regression: must never delete tracked files) --

def _git_init(d):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", "-C", d] + cmd, env=env, check=True,
                       capture_output=True)


def test_git_reject_preserves_tracked_out_of_scope():
    """A rejected out-of-scope write to a TRACKED file must restore it, never
    delete it (guards the _git_restore destructive-remove bug)."""
    root = _sandbox()
    # a committed, tracked file outside the granted scope
    with open(os.path.join(root, "important.txt"), "w") as f:
        f.write("precious\n")
    _git_init(root)
    v = kernel.judge(
        root, ["sandbox"], "tamper outside scope",
        lambda r, s, i: P.stub_propose(r, {"important.txt": "clobbered\n"}, None),
        wal_path=os.path.join(".dogfood", "wal", "t.jsonl"),
        blobs_dir=os.path.join(".dogfood", "blobs"))
    assert not v["accepted"]
    assert any("capability" in r for r in v["reasons"])
    p = os.path.join(root, "important.txt")
    assert os.path.exists(p), "tracked out-of-scope file was destroyed"
    assert open(p).read() == "precious\n", "tracked file not restored to HEAD"


# --- runner -----------------------------------------------------------------

def _run():
    tests = sorted((n, f) for n, f in globals().items()
                   if n.startswith("test_") and callable(f))
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception as e:          # noqa: BLE001
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
