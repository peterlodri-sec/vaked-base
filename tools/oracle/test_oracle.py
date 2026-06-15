#!/usr/bin/env python3
"""vaked-oracle unit tests (stdlib only; run: python3 tools/oracle/test_oracle.py)."""
import json
import os
import sys

# allow `import schema` etc. when run from repo root or tools/oracle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# --- tests are added below by later tasks ---

import schema  # noqa: E402


def test_function_entry_defaults_nullable_dynamic():
    e = schema.function_entry(name="sample_fn", addr="0x1000",
                              pseudo_c_sha="ab" * 32, refined_c="int f(){}")
    assert e["name"] == "sample_fn"
    assert e["fidelity"] == {"score": None, "method": schema.FIDELITY_METHOD}
    assert e["dynamic"] == {"frida": None, "ebpf": None}


def test_build_finding_shape_and_kind():
    fn = schema.function_entry(name="f", addr="0x1", pseudo_c_sha="0" * 64, refined_c="x")
    fdg = schema.build_finding(
        target={"path": "/p", "sha256": "0" * 64, "source_ref": "v1"},
        decompiler={"model": "llm4decompile-6.7b-v2", "model_sha256": "0" * 64, "temperature": 0},
        functions=[fn], confidence=0.5)
    assert fdg["kind"] == "oracle_finding" and fdg["v"] == 1
    assert fdg["observed_effects"] == {"writes": [], "deletes": []}
    assert fdg["transition_xref"] is None
    assert fdg["functions"][0]["name"] == "f"


def test_validate_rejects_bad_kind():
    bad = {"kind": "nope", "v": 1}
    try:
        schema.validate_finding(bad)
        assert False, "expected ValueError"
    except ValueError:
        pass


import fidelity  # noqa: E402


def test_fidelity_identical_is_one():
    src = "int add(int a, int b) { return a + b; }"
    assert fidelity.score(src, src) == 1.0


def test_fidelity_unrelated_is_low():
    a = "int add(int a, int b) { return a + b; }"
    b = "while (true) { printf(\"zzz\"); }"
    assert fidelity.score(a, b) < 0.4


def test_fidelity_handles_empty():
    assert fidelity.score("", "") == 0.0
    assert fidelity.score("int x;", "") == 0.0


import ledger  # noqa: E402
import tempfile  # noqa: E402


def test_ledger_append_and_verify():
    with tempfile.TemporaryDirectory() as d:
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))
        e0 = lg.append({"kind": "decision", "action": "decompile", "fn": "f"})
        e1 = lg.append({"kind": "finding", "confidence": 0.9})
        assert e0["seq"] == 0 and e0["prev"] == ledger.GENESIS_HASH
        assert e1["seq"] == 1 and e1["prev"] == e0["hash"]
        assert lg.verify() is True


def test_ledger_detects_tamper():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "events.jsonl")
        lg = ledger.Ledger(path)
        lg.append({"kind": "decision", "n": 1})
        lg.append({"kind": "decision", "n": 2})
        # corrupt the first entry's payload on disk
        lines = open(path).read().splitlines()
        lines[0] = lines[0].replace('"n": 1', '"n": 999')
        open(path, "w").write("\n".join(lines) + "\n")
        lg2 = ledger.Ledger(path)
        assert lg2.verify() is False
        assert len(lg2.valid_prefix()) == 0


import llm_refine  # noqa: E402


def test_build_prompt_inserts_pseudo_c():
    p = llm_refine.build_prompt("int f(){return 1;}")
    assert "int f(){return 1;}" in p
    assert p.endswith(llm_refine.PROMPT_SUFFIX)


def test_parse_completion_extracts_content():
    # llama.cpp native /completion returns {"content": "..."}
    assert llm_refine.parse_completion({"content": "int f(){...}"}) == "int f(){...}"


def test_parse_completion_missing_content_raises():
    try:
        llm_refine.parse_completion({"oops": 1})
        assert False, "expected KeyError"
    except KeyError:
        pass


import ghidra_frontend as gf  # noqa: E402


def test_parse_decomp_reads_json_map():
    blob = '{"sample_fn": "int sample_fn(void){return 0;}", "g": "void g(){}"}'
    got = gf.parse_decomp(blob)
    assert got["sample_fn"].startswith("int sample_fn")
    assert set(got) == {"sample_fn", "g"}


def test_parse_decomp_bad_json_raises():
    try:
        gf.parse_decomp("not json")
        assert False, "expected ValueError"
    except ValueError:
        pass


import dynamic_frida as dfr  # noqa: E402


def test_parse_frida_aggregates_calls():
    # frida_driver.py emits one JSON line per call event
    lines = [
        '{"fn": "ggml_compute", "dur_ns": 1000}',
        '{"fn": "ggml_compute", "dur_ns": 3000}',
        '{"fn": "llama_decode", "dur_ns": 500}',
    ]
    got = dfr.parse_frida_trace("\n".join(lines))
    assert got["ggml_compute"]["calls"] == 2
    assert got["ggml_compute"]["timing_ms"] == 0.004  # (1000+3000)ns -> ms, rounded
    assert got["llama_decode"]["calls"] == 1


def test_parse_frida_ignores_noise_lines():
    got = dfr.parse_frida_trace('garbage\n{"fn":"f","dur_ns":1000}\n[frida] log')
    assert got["f"]["calls"] == 1


import watcher_client as wc  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402


def test_encode_decode_roundtrip():
    req = wc.encode_request(pid=1234, duration_s=5)
    assert json.loads(req.decode())["pid"] == 1234
    resp = wc.decode_response(json.dumps(
        {"ok": True, "syscalls": {"openat": 3}, "mmaps": ["model.gguf"], "files": []}).encode())
    assert resp["syscalls"]["openat"] == 3


def test_decode_response_error_raises():
    try:
        wc.decode_response(json.dumps({"ok": False, "error": "no such pid"}).encode())
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "no such pid" in str(e)


def test_query_watcher_against_fake_socket():
    with tempfile.TemporaryDirectory() as d:
        sock_path = os.path.join(d, "w.sock")
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(sock_path); srv.listen(1)

        def serve():
            conn, _ = srv.accept()
            conn.recv(4096)
            conn.sendall(json.dumps({"ok": True, "syscalls": {"mmap": 1},
                                     "mmaps": [], "files": []}).encode())
            conn.close()
        t = threading.Thread(target=serve, daemon=True); t.start()
        out = wc.query_watcher(sock_path, pid=42, duration_s=1)
        assert out["syscalls"]["mmap"] == 1
        srv.close()


import watcher_daemon as wd  # noqa: E402


def test_parse_bpftrace_syscall_counts():
    # bpftrace prints @syscalls[name]: count maps after exit
    out = "@syscalls[openat]: 4\n@syscalls[mmap]: 2\n@files[/m/model.gguf]: 1\n"
    parsed = wd.parse_bpftrace(out)
    assert parsed["syscalls"] == {"openat": 4, "mmap": 2}
    assert parsed["files"] == ["/m/model.gguf"]


def test_handle_request_bad_pid_returns_error():
    resp = wd.handle_request({"pid": -1, "duration_s": 1}, run=lambda pid, dur: {})
    assert resp["ok"] is False and "pid" in resp["error"]


def test_parse_bpftrace_strips_tracepoint_prefix():
    out = ("@syscalls[tracepoint:syscalls:sys_enter_openat]: 4\n"
           "@syscalls[mmap]: 2\n")
    parsed = wd.parse_bpftrace(out)
    assert parsed["syscalls"] == {"openat": 4, "mmap": 2}


import bridge  # noqa: E402


def test_bridge_emits_observed_effects_shape():
    fdg = schema.build_finding(
        target={"path": "/p", "sha256": "0" * 64, "source_ref": "v"},
        decompiler={"model": "m", "model_sha256": "0" * 64, "temperature": 0},
        functions=[], confidence=0.0)
    oe = bridge.to_observed_effects(fdg, files_written=["/p/notes.md"])
    assert oe == {"writes": ["/p/notes.md"], "deletes": []}


def test_bridge_attaches_transition_xref():
    fdg = schema.build_finding(
        target={"path": "/p", "sha256": "0" * 64, "source_ref": "v"},
        decompiler={"model": "m", "model_sha256": "0" * 64, "temperature": 0},
        functions=[], confidence=0.0)
    out = bridge.attach_transition(fdg, "deadbeef" * 8)
    assert out["transition_xref"] == "deadbeef" * 8
    assert out is not fdg  # non-mutating


import policy  # noqa: E402


def test_policy_decompiles_unprocessed_function_first():
    state = policy.LoopState(functions=["a", "b"], results={}, iters=0, budget_iters=10)
    act = policy.next_action(state)
    assert act == {"action": "decompile", "fn": "a"}


def test_policy_refines_low_fidelity():
    state = policy.LoopState(
        functions=["a"],
        results={"a": {"fidelity": 0.2, "refined": True, "refine_passes": 0}},
        iters=1, budget_iters=10)
    assert policy.next_action(state) == {"action": "refine", "fn": "a"}


def test_policy_finalizes_when_all_above_threshold():
    state = policy.LoopState(
        functions=["a"],
        results={"a": {"fidelity": 0.95, "refined": True, "refine_passes": 0}},
        iters=1, budget_iters=10)
    assert policy.next_action(state) == {"action": "finalize"}


def test_policy_finalizes_when_budget_exhausted():
    state = policy.LoopState(functions=["a", "b"], results={}, iters=10, budget_iters=10)
    assert policy.next_action(state) == {"action": "finalize"}


def test_policy_stops_refining_after_max_passes():
    state = policy.LoopState(
        functions=["a"],
        results={"a": {"fidelity": 0.2, "refined": True, "refine_passes": policy.MAX_REFINE}},
        iters=5, budget_iters=10)
    assert policy.next_action(state) == {"action": "finalize"}


def test_policy_skips_refine_when_fidelity_unknown():
    # no ground truth -> fidelity None -> can't improve an unmeasurable score -> finalize
    state = policy.LoopState(
        functions=["a"],
        results={"a": {"fidelity": None, "refined": True, "refine_passes": 0}},
        iters=1, budget_iters=10)
    assert policy.next_action(state) == {"action": "finalize"}


import loop  # noqa: E402


def test_loop_runs_to_finalize_with_fakes():
    with tempfile.TemporaryDirectory() as d:
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))

        def fake_decompile(fn):  # returns (pseudo_c, refined_c, fidelity)
            return (f"pseudo {fn}", f"int {fn}(){{}}", 0.9)

        def fake_refine(fn, prev):
            return (f"int {fn}(){{}} // refined", 0.95)

        def fake_dynamic(fn):
            return ({"calls": 1, "timing_ms": 0.1}, {"syscalls": {"mmap": 1}, "mmaps": [], "files": []})

        result = loop.run_loop(
            functions=["a", "b"],
            target={"path": "/bin/llama-cli", "sha256": "0" * 64, "source_ref": "vX"},
            decompiler_meta={"model": "llm4decompile-6.7b-v2", "model_sha256": "0" * 64, "temperature": 0},
            ledger_=lg,
            decompile=fake_decompile, refine=fake_refine, dynamic=fake_dynamic,
            budget_iters=20, control_path=None)

        assert result["kind"] == "oracle_finding"
        assert len(result["functions"]) == 2
        assert all(f["fidelity"]["score"] >= 0.75 for f in result["functions"])
        # ledger has decision entries + a final finding entry, and verifies
        kinds = [e["payload"]["kind"] for e in lg.entries()]
        assert "finding" in kinds and lg.verify() is True


import oracle as oracle_cli  # noqa: E402


def test_persist_finding_writes_hashed_file():
    with tempfile.TemporaryDirectory() as d:
        fdg = schema.build_finding(
            target={"path": "/p", "sha256": "0" * 64, "source_ref": "v"},
            decompiler={"model": "m", "model_sha256": "0" * 64, "temperature": 0},
            functions=[], confidence=0.0)
        path = oracle_cli.persist_finding(fdg, findings_dir=d)
        assert os.path.exists(path) and path.endswith(".json")
        assert json.load(open(path))["kind"] == "oracle_finding"


def test_parse_args_funcs_splits_csv():
    ns = oracle_cli.parse_args(["run", "--target", "/bin/x", "--funcs", "a,b,c"])
    assert ns.funcs == ["a", "b", "c"] and ns.target == "/bin/x"


def test_smoke_end_to_end_with_fakes_persists_and_verifies():
    """Full loop -> finding -> persist -> reload, all with fakes (no ghidra/llm/frida)."""
    import oracle as oc
    with tempfile.TemporaryDirectory() as d:
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))
        finding = loop.run_loop(
            functions=["main"],
            target={"path": "/bin/true", "sha256": "0" * 64, "source_ref": "vX"},
            decompiler_meta={"model": "m", "model_sha256": "0" * 64, "temperature": 0},
            ledger_=lg,
            decompile=lambda fn: ("pseudo", "int main(){return 0;}", 0.99),
            refine=lambda fn, prev: ("int main(){return 0;}", 0.99),
            dynamic=lambda fn: (None, None),
            budget_iters=10, control_path=None)
        path = oc.persist_finding(finding, findings_dir=os.path.join(d, "findings"))
        reloaded = json.load(open(path))
        schema.validate_finding(reloaded)
        assert reloaded["confidence"] >= 0.75 and lg.verify()


# --- slice 2: double-dogfood transition_xref wire -------------------------------
import dogfood_bridge as ddb  # noqa: E402


def _fixture_finding():
    fn = schema.function_entry(name="llama_decode", addr="0x1000",
                               pseudo_c_sha="ab" * 32, refined_c="int llama_decode(){}",
                               fidelity_score=0.81)
    return schema.build_finding(
        target={"path": "/usr/lib/libllama.so.0", "sha256": "0" * 64, "source_ref": "b9190"},
        decompiler={"model": "llm4decompile-6.7b-v2", "model_sha256": "0" * 64, "temperature": 0},
        functions=[fn], confidence=0.81)


def _ground_in(d, finding, finding_rel="findings/f.json", scope=("findings",)):
    """Ground a finding in a clean workspace under tmpdir `d`. WAL/blobs are
    SIBLINGS of root (never under it). Returns (result, root, wal_path, lg)."""
    root = os.path.join(d, "ws")
    os.makedirs(root, exist_ok=True)
    wal_path = os.path.join(d, "aegis-wal", "wal.jsonl")
    blobs = os.path.join(d, "aegis-wal", "blobs")
    lg = ledger.Ledger(os.path.join(d, "events.jsonl"))
    res = ddb.ground_finding(finding=finding, finding_rel=finding_rel, root=root,
                             scope=list(scope), wal_path=wal_path, blobs_dir=blobs,
                             oracle_ledger=lg)
    return res, root, wal_path, lg


def test_ground_attaches_real_wal_hash():
    from eventd import EventLog
    with tempfile.TemporaryDirectory() as d:
        res, root, wal_path, lg = _ground_in(d, _fixture_finding())
        xref = res["transition_xref"]
        assert isinstance(xref, str) and len(xref) == 64 and xref != "0" * 64
        assert res["linked_finding"]["transition_xref"] == xref
        assert os.path.exists(os.path.join(root, "findings", "f.json"))
        with EventLog(wal_path) as log:
            entries = list(log.entries)
        assert len(entries) == 1
        assert entries[0]["payload"]["actual_effects"]["writes"] == ["findings/f.json"]
        assert entries[0]["hash"] == xref
        assert lg.verify()


def test_ground_respects_capability_scope():
    with tempfile.TemporaryDirectory() as d:
        try:
            _ground_in(d, _fixture_finding(), finding_rel="outside/f.json", scope=("findings",))
            assert False, "expected RuntimeError (out-of-scope write)"
        except RuntimeError:
            pass
        assert not os.path.exists(os.path.join(d, "aegis-wal", "wal.jsonl"))
        assert not os.path.exists(os.path.join(d, "ws", "outside", "f.json"))


def test_verify_xref_resolves_bidirectionally():
    with tempfile.TemporaryDirectory() as d:
        res, root, wal_path, lg = _ground_in(d, _fixture_finding())
        assert ddb.verify_xref(finding=res["linked_finding"], wal_path=wal_path,
                               oracle_ledger=lg) is True


def test_verify_xref_rejects_missing_wal_entry():
    with tempfile.TemporaryDirectory() as d:
        res, root, wal_path, lg = _ground_in(d, _fixture_finding())
        forged = dict(res["linked_finding"])
        forged["transition_xref"] = "00" * 32
        try:
            ddb.verify_xref(finding=forged, wal_path=wal_path, oracle_ledger=lg)
            assert False, "expected ValueError (missing WAL entry)"
        except ValueError:
            pass


def test_verify_xref_rejects_finding_not_in_writes():
    with tempfile.TemporaryDirectory() as d:
        res, root, wal_path, lg = _ground_in(d, _fixture_finding(),
                                             finding_rel="findings/a.json")
        forged = dict(res["linked_finding"])
        forged["observed_effects"] = {"writes": ["findings/b.json"], "deletes": []}
        try:
            ddb.verify_xref(finding=forged, wal_path=wal_path, oracle_ledger=lg)
            assert False, "expected ValueError (finding not in transition writes)"
        except ValueError:
            pass


def test_chains_verify_independently():
    from eventd import EventLog, TamperError
    with tempfile.TemporaryDirectory() as d:
        res, root, wal_path, lg = _ground_in(d, _fixture_finding())
        linked = res["linked_finding"]
        # (a) tamper the oracle ledger ⇒ verify_xref fails at the ledger gate.
        led_path = os.path.join(d, "events.jsonl")
        rows = open(led_path).read().splitlines()
        bad = json.loads(rows[-1]); bad["payload"]["confidence"] = 0.0
        rows[-1] = json.dumps(bad, sort_keys=True)
        open(led_path, "w").write("\n".join(rows) + "\n")
        tampered_lg = ledger.Ledger(led_path)
        assert tampered_lg.verify() is False
        try:
            ddb.verify_xref(finding=linked, wal_path=wal_path, oracle_ledger=tampered_lg)
            assert False, "expected ValueError (tampered ledger)"
        except ValueError:
            pass
        # (b) tamper the WAL bytes ⇒ EventLog open raises; the ledger is unaffected.
        wrows = open(wal_path).read().splitlines()
        wbad = json.loads(wrows[0]); wbad["payload"]["intent"] = "FORGED"
        wrows[0] = json.dumps(wbad, sort_keys=True)
        open(wal_path, "w").write("\n".join(wrows) + "\n")
        try:
            with EventLog(wal_path) as log:
                list(log.entries)
            assert False, "expected TamperError (tampered WAL)"
        except TamperError:
            pass
        # verify_xref must also surface the WAL tamper (not silently pass).
        # lg's in-memory chain is still clean, so step 1 passes; the WAL open raises.
        try:
            ddb.verify_xref(finding=linked, wal_path=wal_path, oracle_ledger=lg)
            assert False, "expected verify_xref to raise on tampered WAL"
        except Exception:
            pass


def test_ground_strips_stale_xref_from_artifact():
    """Re-grounding a finding that already carries an xref must hash WITHOUT it."""
    with tempfile.TemporaryDirectory() as d:
        stale = dict(_fixture_finding())
        stale["transition_xref"] = "ff" * 32   # pretend previously linked
        res, root, wal_path, lg = _ground_in(d, stale)
        art = json.load(open(os.path.join(root, "findings", "f.json")))
        assert art.get("transition_xref") is None   # the hashed artifact carries no xref
        assert ddb.verify_xref(finding=res["linked_finding"], wal_path=wal_path,
                               oracle_ledger=lg) is True


def test_cli_ground_then_verify_roundtrip():
    import oracle as oc
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "ws"); os.makedirs(os.path.join(root, "findings"))
        fpath = os.path.join(root, "findings", "f.json")
        json.dump(_fixture_finding(), open(fpath, "w"), sort_keys=True)
        wal_path = os.path.join(d, "aegis-wal", "wal.jsonl")
        blobs = os.path.join(d, "aegis-wal", "blobs")
        led = os.path.join(d, "events.jsonl")
        rc = oc.main(["ground", "--finding", fpath, "--root", root, "--scope", "findings",
                      "--wal-path", wal_path, "--blobs", blobs, "--ledger", led])
        assert rc == 0
        last = json.loads(open(led).read().splitlines()[-1])
        linked_path = os.path.join(d, "linked.json")
        json.dump(last["payload"], open(linked_path, "w"))
        rc2 = oc.main(["verify-xref", "--finding", linked_path,
                       "--wal-path", wal_path, "--ledger", led])
        assert rc2 == 0


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
