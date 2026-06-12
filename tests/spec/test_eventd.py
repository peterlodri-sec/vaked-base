#!/usr/bin/env python3
"""test_eventd.py — the eventd reference implementation (#18, RFC 0004).

Five groups:

1. **format-parity.** eventd.core and tools/ralph/ralphcore produce identical
   entries (hash + canonical form) on shared vectors, and each verifies the
   other's chains — the "format frozen verbatim" guarantee of the eventd
   design. Any drift between the two is a failure here.
2. **log-discipline.** Append + reopen verifies; a flipped byte makes reopen
   raise TamperError (boot-time tamper check is a hard error); a second
   writer is refused (single-writer flock).
3. **determinism.** The same payload sequence produces byte-identical log
   files across two runs.
4. **statedep.** RFC 0004 semantics: the GC floor is the min over live
   consumers' checkpoints (§4) and explicit eviction lifts it (§4.2); the
   cold-start verifier (§6) returns RUNNING for a fresh anchor and the exact
   StaleDependency record when a rewind voids it (§3.3) or the consumer was
   evicted.
5. **cli.** verify/floor/coldstart exit codes on a good, a stale, and a
   tampered log.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools", "ralph"))

import ralphcore  # noqa: E402  (tools/ralph — the proven format reference)
from eventd import (  # noqa: E402
    DependencyIndex, EventLog, TamperError, WriterLockError,
    consumer_checkpoint, consumer_evicted, dependency_registration,
    rewind_event, verify_chain,
)
from eventd.core import canonical_json, make_entry  # noqa: E402

# Shared payload vectors — exercise unicode, nesting, key order, numbers.
_VECTORS = [
    {"event": "boot", "runtime": "agent-field"},
    {"b": 2, "a": 1, "nested": {"y": [1, 2, 3], "x": None}},
    {"text": "víg kedélyű 🦀", "n": -3.5},
    {"kind": "dependency_registration", "consumer": "beta", "producer": "alpha",
     "consumer_step": 7, "producer_step": 2,
     "producer_step_hash": "ab" * 32, "topology_epoch": 1},
]


def _test_format_parity(lines):
    ok = True
    prev_e = prev_r = ralphcore.GENESIS_HASH
    ours, theirs = [], []
    for i, payload in enumerate(_VECTORS):
        e = make_entry(prev_e, i, payload)
        r = ralphcore.make_entry(prev_r, i, payload)
        if e != r:
            ok = False
            lines.append(f"  FAIL parity: entry {i} differs: {e} vs {r}")
        if canonical_json(payload) != ralphcore._canon(payload):
            ok = False
            lines.append(f"  FAIL parity: canonical_json differs on vector {i}")
        ours.append(e)
        theirs.append(r)
        prev_e, prev_r = e["hash"], r["hash"]
    if not (verify_chain(theirs) and ralphcore.verify_chain(ours)):
        ok = False
        lines.append("  FAIL parity: cross-verification failed "
                     "(eventd↔ralphcore chains)")
    if ok:
        lines.append(f"  format-parity: {len(_VECTORS)} vectors — identical "
                     f"entries, cross-verified chains (format frozen)")
    return ok


def _test_log_discipline(lines):
    ok = True
    tmp = tempfile.mkdtemp(prefix="eventd-spec-")
    try:
        path = os.path.join(tmp, "log.jsonl")
        with EventLog(path, writer=True) as log:
            for p in _VECTORS:
                log.append(p)
            # second writer refused while the first holds the flock
            try:
                EventLog(path, writer=True)
                ok = False
                lines.append("  FAIL log: second writer was NOT refused")
            except WriterLockError:
                pass
        reopened = EventLog(path)
        if len(reopened) != len(_VECTORS):
            ok = False
            lines.append(f"  FAIL log: reopen lost entries "
                         f"({len(reopened)}/{len(_VECTORS)})")
        # tamper: flip one byte of the payload region ⇒ boot must hard-error
        raw = open(path, encoding="utf-8").read()
        bad = raw.replace("boot", "b00t", 1)
        open(path, "w", encoding="utf-8").write(bad)
        try:
            EventLog(path)
            ok = False
            lines.append("  FAIL log: tampered log did NOT raise TamperError")
        except TamperError:
            pass
        if ok:
            lines.append("  log-discipline: append+fsync, reopen verifies, "
                         "tamper ⇒ hard error, second writer refused")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def _test_determinism(lines):
    tmp = tempfile.mkdtemp(prefix="eventd-spec-")
    try:
        files = []
        for run in ("a", "b"):
            path = os.path.join(tmp, f"{run}.jsonl")
            with EventLog(path, writer=True) as log:
                for p in _VECTORS:
                    log.append(p)
            files.append(open(path, "rb").read())
        if files[0] != files[1]:
            lines.append("  FAIL determinism: same payloads produced "
                         "different log bytes")
            return False
        lines.append(f"  determinism: two runs ⇒ byte-identical logs "
                     f"({len(files[0])} bytes)")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _mk_statedep_log(path, *, rewind=False, evict=False):
    """Producer alpha emits two steps; beta registers an anchor on step 1,
    checkpoints; gamma checkpoints shallower (it pins the floor)."""
    with EventLog(path, writer=True) as log:
        log.append({"agent": "alpha", "event": "step", "n": 0})       # seq 0
        anchored = log.append({"agent": "alpha", "event": "step", "n": 1})  # seq 1
        log.append(dependency_registration(
            "beta", "alpha", consumer_step=0, producer_step=1,
            producer_step_hash=anchored["hash"], topology_epoch=1))   # seq 2
        log.append(consumer_checkpoint(
            "beta", "alpha", min_required_step=1, consumer_checkpoint_step=0,
            topology_epoch=1, last_heartbeat_at="2026-06-12T16:00:00Z"))
        log.append(consumer_checkpoint(
            "gamma", "alpha", min_required_step=0, consumer_checkpoint_step=4,
            topology_epoch=1, last_heartbeat_at="2026-06-12T16:00:00Z"))
        if rewind:
            log.append(rewind_event("alpha", rewind_to_step=0,
                                    rewind_to_hash=log.entries[0]["hash"],
                                    topology_epoch=1))
        if evict:
            log.append(consumer_evicted("gamma", "lease expired", 1))
        return log.entries


def _test_statedep(lines):
    ok = True
    tmp = tempfile.mkdtemp(prefix="eventd-spec-")
    try:
        # fresh anchors ⇒ RUNNING; gamma pins the floor at 0
        entries = _mk_statedep_log(os.path.join(tmp, "fresh.jsonl"))
        idx = DependencyIndex.from_entries(entries)
        if idx.gc_floor("alpha") != 0:
            ok = False
            lines.append(f"  FAIL statedep: floor should be 0 (gamma pins), "
                         f"got {idx.gc_floor('alpha')}")
        if idx.verify_cold_start("beta", entries) is not None:
            ok = False
            lines.append("  FAIL statedep: fresh anchor should be RUNNING")

        # explicit eviction lifts the floor to beta's min_required_step (§4.2)
        entries = _mk_statedep_log(os.path.join(tmp, "evict.jsonl"), evict=True)
        idx = DependencyIndex.from_entries(entries)
        if idx.gc_floor("alpha") != 1:
            ok = False
            lines.append(f"  FAIL statedep: post-eviction floor should be 1, "
                         f"got {idx.gc_floor('alpha')}")

        # a rewind below the anchor voids it ⇒ StaleDependency (§3.3/§6)
        entries = _mk_statedep_log(os.path.join(tmp, "rewound.jsonl"),
                                   rewind=True)
        idx = DependencyIndex.from_entries(entries)
        stale = idx.verify_cold_start("beta", entries)
        if stale is None:
            ok = False
            lines.append("  FAIL statedep: rewound anchor should be stale")
        else:
            want = ("alpha", 1, entries[1]["hash"], entries[-1]["seq"], 1)
            got = (stale.producer, stale.expected_step, stale.expected_hash,
                   stale.observed_tip, stale.topology_epoch)
            if got != want:
                ok = False
                lines.append(f"  FAIL statedep: StaleDependency fields "
                             f"{got} != {want}")
        if ok:
            lines.append("  statedep: floor min/eviction per §4; rewind voids "
                         "anchor ⇒ exact StaleDependency; fresh ⇒ RUNNING")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def _test_cli(lines):
    ok = True
    tmp = tempfile.mkdtemp(prefix="eventd-spec-")
    try:
        good = os.path.join(tmp, "good.jsonl")
        _mk_statedep_log(good)
        rewound = os.path.join(tmp, "rewound.jsonl")
        _mk_statedep_log(rewound, rewind=True)

        def run(*args):
            return subprocess.run([sys.executable, "-m", "eventd", *args],
                                  capture_output=True, text=True, cwd=REPO)

        cases = [
            (("verify", good), 0),
            (("coldstart", good, "beta"), 0),
            (("coldstart", rewound, "beta"), 1),
            (("floor", good, "alpha"), 0),
        ]
        for args, want in cases:
            r = run(*args)
            if r.returncode != want:
                ok = False
                lines.append(f"  FAIL cli: {' '.join(args)} → exit "
                             f"{r.returncode}, want {want}: {r.stderr.strip()}")
        # tampered log: every command must refuse with exit 1
        raw = open(good, encoding="utf-8").read()
        open(good, "w", encoding="utf-8").write(raw.replace("step", "step!", 1))
        r = run("verify", good)
        if r.returncode != 1:
            ok = False
            lines.append(f"  FAIL cli: verify on tampered log → exit "
                         f"{r.returncode}, want 1")
        if ok:
            lines.append("  cli: verify/coldstart/floor exit codes correct; "
                         "tampered log refused")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def run():
    lines = []
    ok = True
    for fn in (_test_format_parity, _test_log_discipline, _test_determinism,
               _test_statedep, _test_cli):
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
    print("== test_eventd ==")
    for ln in lines:
        print(ln)
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
