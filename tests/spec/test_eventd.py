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

# Shared payload vectors — exercise unicode, nesting, key order, numbers,
# plus the hostile canonicalization cases the cross-language hash contract
# must pin down (core.py dialect speclet): -0.0, shortest-round-trip floats,
# big ints, precomposed vs combining unicode (NOT normalized — by design).
_VECTORS = [
    {"event": "boot", "runtime": "agent-field"},
    {"b": 2, "a": 1, "nested": {"y": [1, 2, 3], "x": None}},
    {"text": "víg kedélyű 🦀", "n": -3.5},
    {"kind": "dependency_registration", "consumer": "beta", "producer": "alpha",
     "consumer_step": 7, "producer_step": 2,
     "producer_step_hash": "ab" * 32, "topology_epoch": 1},
    {"x": -0.0},
    {"x": 1.0},
    {"x": 1e-6},
    {"x": 100000000000000000000},
    {"x": "é"},                  # U+00E9 precomposed
    {"x": "é"},            # e + combining acute — a DIFFERENT payload
    {"b": 1, "a": 2},
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
    # precomposed vs combining MUST hash differently (no normalization)
    if canonical_json({"x": "é"}) == canonical_json({"x": "é"}):
        ok = False
        lines.append("  FAIL parity: unicode normalization leaked into "
                     "canonical_json")
    # NaN/Infinity are rejected (stricter than ralphcore's invalid-JSON output)
    try:
        canonical_json({"x": float("nan")})
        ok = False
        lines.append("  FAIL parity: NaN was not rejected")
    except ValueError:
        pass
    if ok:
        lines.append(f"  format-parity: {len(_VECTORS)} vectors (incl. -0.0, "
                     f"1e-6, bigint, é vs e+combining) — identical entries, "
                     f"cross-verified chains; NaN rejected")
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
        # malformed line (torn write / byte tamper) ⇒ SAME hard-error path,
        # never a raw JSONDecodeError (Codex P2, PR #31)
        open(path, "w", encoding="utf-8").write(raw + "{not json\n")
        try:
            EventLog(path)
            ok = False
            lines.append("  FAIL log: malformed line did NOT raise TamperError")
        except TamperError:
            pass
        # writer-open on a refused log must release the lock (Codex P1 round 2:
        # the writer locks FIRST, then loads/verifies under the lock; a refusal
        # must not leave the lock held)
        try:
            EventLog(path, writer=True)
            ok = False
            lines.append("  FAIL log: writer open on tampered log did NOT "
                         "raise TamperError")
        except TamperError:
            pass
        open(path, "w", encoding="utf-8").write(raw)   # restore good log
        try:
            with EventLog(path, writer=True) as w:
                w.append({"event": "post-recovery"})
        except (TamperError, WriterLockError) as e:
            ok = False
            lines.append(f"  FAIL log: lock not released after refused "
                         f"writer open: {e}")
        # crash-tail: a truncated final record (torn write) is TAMPER —
        # refused by default; repair is a future explicit operator command
        raw2 = open(path, encoding="utf-8").read()
        open(path, "w", encoding="utf-8").write(raw2 + '{"seq": 99, "pre')
        try:
            EventLog(path)
            ok = False
            lines.append("  FAIL log: truncated tail did NOT raise "
                         "TamperError")
        except TamperError:
            pass
        open(path, "w", encoding="utf-8").write(raw2)
        # single-writer across PROCESSES (the production risk is competing
        # daemon instances, not two handles in one process)
        holder = subprocess.Popen(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r)\n"
             "from eventd import EventLog\n"
             "log = EventLog(%r, writer=True)\n"
             "print('locked', flush=True)\n"
             "import time; time.sleep(30)" % (REPO, path)],
            stdout=subprocess.PIPE, text=True)
        try:
            if holder.stdout.readline().strip() != "locked":
                ok = False
                lines.append("  FAIL log: cross-process lock holder did not "
                             "start")
            else:
                try:
                    EventLog(path, writer=True)
                    ok = False
                    lines.append("  FAIL log: writer in a second PROCESS was "
                                 "NOT refused")
                except WriterLockError:
                    pass
        finally:
            holder.terminate()
            holder.wait()
        if ok:
            lines.append("  log-discipline: append+fsync, reopen verifies, "
                         "tamper/malformed/truncated-tail ⇒ hard error, "
                         "second writer refused (in-process + cross-process)")
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

        # explicit recovery re-admits an evicted consumer (Codex P2 round 2,
        # RFC §6): a fresh registration/checkpoint logged AFTER the eviction
        # clears it from the fold — its new anchor constrains compaction again
        path = os.path.join(tmp, "recovered.jsonl")
        with EventLog(path, writer=True) as log:
            log.append({"agent": "alpha", "event": "step", "n": 0})
            anchored = log.append({"agent": "alpha", "event": "step", "n": 1})
            log.append(consumer_checkpoint(
                "gamma", "alpha", min_required_step=0,
                consumer_checkpoint_step=4, topology_epoch=1,
                last_heartbeat_at="2026-06-12T16:00:00Z"))
            log.append(consumer_evicted("gamma", "lease expired", 1))
            log.append(dependency_registration(
                "gamma", "alpha", consumer_step=0, producer_step=1,
                producer_step_hash=anchored["hash"], topology_epoch=2))
            recovered = log.entries
        idx = DependencyIndex.from_entries(recovered)
        if idx.gc_floor("alpha") != 1:
            ok = False
            lines.append(f"  FAIL statedep: recovered consumer should pin "
                         f"floor at its new anchor (1), got "
                         f"{idx.gc_floor('alpha')}")
        if idx.verify_cold_start("gamma", recovered) is not None:
            ok = False
            lines.append("  FAIL statedep: recovered consumer with a fresh "
                         "valid anchor should be RUNNING")

        # an ordinary checkpoint from the dead process does NOT undo eviction
        # (Codex P1 on #33): re-admission requires a fresh registration
        path = os.path.join(tmp, "ghost-checkpoint.jsonl")
        with EventLog(path, writer=True) as log:
            log.append({"agent": "alpha", "event": "step", "n": 0})
            anchored = log.append({"agent": "alpha", "event": "step", "n": 1})
            log.append(dependency_registration(
                "gamma", "alpha", consumer_step=0, producer_step=1,
                producer_step_hash=anchored["hash"], topology_epoch=1))
            log.append(consumer_evicted("gamma", "lease expired", 1))
            log.append(consumer_checkpoint(          # delayed ghost write
                "gamma", "alpha", min_required_step=0,
                consumer_checkpoint_step=9, topology_epoch=1,
                last_heartbeat_at="2026-06-12T16:10:00Z"))
            ghost = log.entries
        idx = DependencyIndex.from_entries(ghost)
        if idx.gc_floor("alpha") is not None:
            ok = False
            lines.append(f"  FAIL statedep: ghost checkpoint re-admitted an "
                         f"evicted consumer (floor {idx.gc_floor('alpha')})")
        if idx.verify_cold_start("gamma", ghost) is None:
            ok = False
            lines.append("  FAIL statedep: evicted consumer with only a ghost "
                         "checkpoint must stay PAUSED")

        # a BACKWARDS checkpoint (lower min_required_step) is latest-wins —
        # it moves the floor DOWN, the conservative direction
        path = os.path.join(tmp, "backwards.jsonl")
        with EventLog(path, writer=True) as log:
            log.append(consumer_checkpoint(
                "beta", "alpha", min_required_step=10,
                consumer_checkpoint_step=0, topology_epoch=1,
                last_heartbeat_at="2026-06-12T16:00:00Z"))
            log.append(consumer_checkpoint(
                "beta", "alpha", min_required_step=5,
                consumer_checkpoint_step=1, topology_epoch=1,
                last_heartbeat_at="2026-06-12T16:01:00Z"))
            backwards = log.entries
        if DependencyIndex.from_entries(backwards).gc_floor("alpha") != 5:
            ok = False
            lines.append("  FAIL statedep: backwards checkpoint should be "
                         "latest-wins (floor 5)")

        # re-registration is a NEW GENERATION: after a rewind voids the old
        # anchor, a fresh registration on surviving history runs again
        path = os.path.join(tmp, "regen.jsonl")
        with EventLog(path, writer=True) as log:
            base = log.append({"agent": "alpha", "event": "step", "n": 0})
            anchored = log.append({"agent": "alpha", "event": "step", "n": 1})
            log.append(dependency_registration(
                "beta", "alpha", consumer_step=0, producer_step=1,
                producer_step_hash=anchored["hash"], topology_epoch=1))
            log.append(rewind_event("alpha", rewind_to_step=0,
                                    rewind_to_hash=base["hash"],
                                    topology_epoch=2))
            log.append(dependency_registration(
                "beta", "alpha", consumer_step=1, producer_step=0,
                producer_step_hash=base["hash"], topology_epoch=2))
            regen = log.entries
        if DependencyIndex.from_entries(regen) \
                .verify_cold_start("beta", regen) is not None:
            ok = False
            lines.append("  FAIL statedep: re-registration (new generation) "
                         "on surviving history should be RUNNING")

        # eviction is voided PER EDGE (Codex round 3): re-anchoring alpha
        # must not revive the stale beta anchor — and beta's floor must not
        # be constrained by the dead edge
        path = os.path.join(tmp, "per-edge.jsonl")
        with EventLog(path, writer=True) as log:
            a0 = log.append({"agent": "alpha", "event": "step", "n": 0})
            b0 = log.append({"agent": "beta", "event": "step", "n": 0})
            log.append(dependency_registration(
                "gamma", "alpha", consumer_step=0, producer_step=0,
                producer_step_hash=a0["hash"], topology_epoch=1))
            log.append(dependency_registration(
                "gamma", "beta", consumer_step=0, producer_step=1,
                producer_step_hash=b0["hash"], topology_epoch=1))
            log.append(consumer_evicted("gamma", "lease expired", 1))
            log.append(dependency_registration(      # re-anchor ALPHA only
                "gamma", "alpha", consumer_step=1, producer_step=0,
                producer_step_hash=a0["hash"], topology_epoch=2))
            per_edge = log.entries
        idx = DependencyIndex.from_entries(per_edge)
        if idx.gc_floor("alpha") != 0:
            ok = False
            lines.append(f"  FAIL statedep: re-anchored alpha edge should pin "
                         f"floor 0, got {idx.gc_floor('alpha')}")
        if idx.gc_floor("beta") is not None:
            ok = False
            lines.append(f"  FAIL statedep: dead beta edge must not constrain "
                         f"compaction, got {idx.gc_floor('beta')}")
        stale = idx.verify_cold_start("gamma", per_edge)
        if stale is None or stale.producer != "beta":
            ok = False
            lines.append(f"  FAIL statedep: unrecovered beta edge should "
                         f"pause gamma, got {stale}")

        # statedep payloads ban floats in step/epoch fields
        try:
            dependency_registration("b", "a", 0, 1.5, "x" * 64, 1)
            ok = False
            lines.append("  FAIL statedep: float producer_step was accepted")
        except TypeError:
            pass

        # an UNACKNOWLEDGED registration pins the floor at its own anchor —
        # §4 condition 1: no checkpoint yet ⇒ no truncation through it
        # (Codex P1, PR #31)
        path = os.path.join(tmp, "unacked.jsonl")
        with EventLog(path, writer=True) as log:
            log.append({"agent": "alpha", "event": "step", "n": 0})
            anchored = log.append({"agent": "alpha", "event": "step", "n": 1})
            log.append(dependency_registration(
                "beta", "alpha", consumer_step=0, producer_step=1,
                producer_step_hash=anchored["hash"], topology_epoch=1))
            unacked = log.entries
        idx = DependencyIndex.from_entries(unacked)
        if idx.gc_floor("alpha") != 1:
            ok = False
            lines.append(f"  FAIL statedep: unacknowledged registration should "
                         f"pin floor at 1, got {idx.gc_floor('alpha')}")

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

        # exit codes are STABLE ORACLE CONTRACT (eventd/__main__.py table):
        # 0 ok/RUNNING · 2 usage · 3 stale_dependency · 4 tampered · 5 locked
        cases = [
            (("verify", good), 0),
            (("coldstart", good, "beta"), 0),
            (("coldstart", rewound, "beta"), 3),
            (("floor", good, "alpha"), 0),
        ]
        for args, want in cases:
            r = run(*args)
            if r.returncode != want:
                ok = False
                lines.append(f"  FAIL cli: {' '.join(args)} → exit "
                             f"{r.returncode}, want {want}: {r.stderr.strip()}")
        # tampered log: every command must refuse with exit 4
        raw = open(good, encoding="utf-8").read()
        open(good, "w", encoding="utf-8").write(raw.replace("step", "step!", 1))
        r = run("verify", good)
        if r.returncode != 4:
            ok = False
            lines.append(f"  FAIL cli: verify on tampered log → exit "
                         f"{r.returncode}, want 4")
        if ok:
            lines.append("  cli: frozen exit-code table holds "
                         "(0 ok / 3 stale / 4 tampered)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


# --------------------------------------------------------------------------- #
# 6. lowering wiring (#18/#24/#27) — the runtime-plane emitters
# --------------------------------------------------------------------------- #
# `vakedc lower` on the daily-use target system emits the workflow spec, the
# memory store config, and the per-runtime eventd log contract — presence-
# gated, byte-deterministic, with the AOT depth precomputed.

_AF_EXAMPLE = os.path.join("vaked", "examples", "agentfield-swe.vaked")


def _test_lowering_wiring(lines):
    ok = True
    tmp = tempfile.mkdtemp(prefix="eventd-spec-")
    try:
        outs = []
        for run_dir in ("l1", "l2"):
            out = os.path.join(tmp, run_dir)
            r = subprocess.run(
                [sys.executable, "-m", "vakedc", "lower", _AF_EXAMPLE,
                 "--out", out],
                capture_output=True, text=True, cwd=REPO)
            if r.returncode != 0:
                lines.append(f"  FAIL lowering: vakedc lower failed: "
                             f"{r.stderr.strip()}")
                return False
            outs.append(out)

        want = ["gen/eventd.json", "gen/memory/palace.json",
                "gen/workflow/swe_af.json"]
        for rel in want:
            if not os.path.exists(os.path.join(outs[0], rel)):
                ok = False
                lines.append(f"  FAIL lowering: missing artifact {rel}")
        if not ok:
            return False

        wf = json.load(open(os.path.join(outs[0], "gen/workflow/swe_af.json")))
        if wf.get("depth") != 4 or len(wf.get("steps", [])) != 4 \
                or len(wf.get("edges", [])) != 3:
            ok = False
            lines.append(f"  FAIL lowering: workflow spec shape wrong "
                         f"(depth={wf.get('depth')}, "
                         f"steps={len(wf.get('steps', []))}, "
                         f"edges={len(wf.get('edges', []))})")
        ev = json.load(open(os.path.join(outs[0], "gen/eventd.json")))
        mem = json.load(open(os.path.join(outs[0], "gen/memory/palace.json")))
        if not (ev["log"] == mem["log"] == wf["log"]
                == "var/lib/agent-field/eventd/log.jsonl"):
            ok = False
            lines.append("  FAIL lowering: log paths inconsistent across "
                         "eventd/memory/workflow artifacts")
        if ev.get("verify_on_boot") is not True:
            ok = False
            lines.append("  FAIL lowering: eventd.json must mandate "
                         "verify_on_boot")

        # byte-determinism across the two runs, every emitted file
        for rel in want:
            b1 = open(os.path.join(outs[0], rel), "rb").read()
            b2 = open(os.path.join(outs[1], rel), "rb").read()
            if b1 != b2:
                ok = False
                lines.append(f"  FAIL lowering: {rel} not byte-identical "
                             f"across runs")

        # provenance inputsHash covers STEP/EDGE inputs (Codex P2 on #33):
        # two workflows identical at the record level but wired differently
        # must produce different inputsHash values
        hashes = []
        for variant, edge in (("wa", "a -> b"), ("wb", "b -> a")):
            src = ('runtime "t" {\n  systems = ["x86_64-linux"]\n'
                   '  workflow w {\n    node a { agent = m.x }\n'
                   '    node b { agent = m.y }\n    %s\n  }\n}\n' % edge)
            vp = os.path.join(tmp, variant + ".vaked")
            open(vp, "w", encoding="utf-8").write(src)
            out = os.path.join(tmp, variant)
            r = subprocess.run(
                [sys.executable, "-m", "vakedc", "lower", vp, "--out", out],
                capture_output=True, text=True, cwd=REPO)
            if r.returncode != 0:
                ok = False
                lines.append(f"  FAIL lowering: variant {variant} failed: "
                             f"{r.stderr.strip()}")
                break
            prov = json.load(open(os.path.join(out, "provenance.json")))
            hashes.append(
                prov["artifacts"]["gen/workflow/w.json"][0]["inputsHash"])
        if len(hashes) == 2 and hashes[0] == hashes[1]:
            ok = False
            lines.append("  FAIL lowering: rewiring the DAG did not change "
                         "the workflow inputsHash")

        # list-valued memory sources survive into the store config (Codex
        # round 3): source = [stream.a, stream.b] must emit both
        msrc = ('runtime "t" {\n  systems = ["x86_64-linux"]\n'
                '  stream a { source = agentpipe.a  type = Agent.T }\n'
                '  stream b { source = agentpipe.b  type = Agent.T }\n'
                '  memory m { source = [stream.a, stream.b] }\n}\n')
        mp = os.path.join(tmp, "multisrc.vaked")
        open(mp, "w", encoding="utf-8").write(msrc)
        mout = os.path.join(tmp, "multisrc")
        r = subprocess.run(
            [sys.executable, "-m", "vakedc", "lower", mp, "--out", mout],
            capture_output=True, text=True, cwd=REPO)
        if r.returncode != 0:
            ok = False
            lines.append(f"  FAIL lowering: multi-source memory failed: "
                         f"{r.stderr.strip()}")
        else:
            mcfg = json.load(open(os.path.join(mout, "gen/memory/m.json")))
            if mcfg.get("source") != ["stream.a", "stream.b"]:
                ok = False
                lines.append(f"  FAIL lowering: list source dropped/mangled: "
                             f"{mcfg.get('source')!r}")
        if ok:
            lines.append("  lowering-wiring: workflow spec (depth 4, 4 steps, "
                         "3 edges) + memory store + eventd contract emitted, "
                         "log paths consistent, byte-deterministic")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def run():
    lines = []
    ok = True
    for fn in (_test_format_parity, _test_log_discipline, _test_determinism,
               _test_statedep, _test_cli, _test_lowering_wiring):
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
