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


# --- slice 3: agentic reverser ---------------------------------------------
import agent as _agent  # noqa: E402
import investigate as _inv  # noqa: E402


def _state(functions=("a", "b"), results=None, iters=0, budget=20, observations=None):
    return policy.LoopState(functions=list(functions), results=results or {},
                            iters=iters, budget_iters=budget,
                            observations=observations or [])


def test_agent_decide_parses_llm_action():
    decide = _agent.make_policy(lambda p: '{"action":"decompile","fn":"a","rationale":"start"}')
    act = decide(_state())
    assert act["action"] == "decompile" and act["fn"] == "a" and act["rationale"] == "start"


def test_agent_decide_falls_back_on_garbage():
    decide = _agent.make_policy(lambda p: "not json at all")
    assert decide(_state()) == policy.next_action(_state())   # deterministic fallback


def test_agent_decide_rejects_out_of_menu():
    d1 = _agent.make_policy(lambda p: '{"action":"rm","fn":"a"}')
    assert d1(_state()) == policy.next_action(_state())          # bad action -> fallback
    d2 = _agent.make_policy(lambda p: '{"action":"decompile","fn":"zzz"}')
    assert d2(_state()) == policy.next_action(_state())          # fn not in functions -> fallback


def test_investigate_crabcc_adapter_parses():
    def fake_runner(cmd, timeout=30):
        assert cmd[:5] == ["crabcc", "--root", "SRC", "lookup", "sym"]
        return 0, '[{"name":"ggml_compute_forward","signature":"int ggml_compute_forward(int)"}]'
    investigate = _inv.make_investigator(source_root="SRC", runner=fake_runner)
    obs = investigate({"kind": "sym", "name": "ggml_compute_forward"})
    assert obs["provider"] == "crabcc" and obs["result"][0]["name"] == "ggml_compute_forward"


def test_investigate_binutils_fallback():
    def fake_runner(cmd, timeout=30):
        return (0, "0000000000001234 T ggml_compute_forward\n") if cmd[0] == "nm" else (1, "")
    investigate = _inv.make_investigator(binary="/lib/libggml.so", runner=fake_runner)
    obs = investigate({"kind": "sym", "name": "ggml_compute_forward"})
    assert obs["provider"] == "binutils" and obs["result"]["found"] is True


def test_investigate_never_raises_returns_none():
    def boom(cmd, timeout=30):
        raise RuntimeError("crabcc exploded")
    investigate = _inv.make_investigator(source_root="SRC", runner=boom)
    assert investigate({"kind": "sym", "name": "x"})["provider"] == "none"


def test_investigate_crabcc_missing_falls_through_to_binutils():
    """crabcc not installed (FileNotFoundError) + binary set => binutils, not 'none'."""
    def runner(cmd, timeout=30):
        if cmd[0] == "crabcc":
            raise FileNotFoundError("crabcc not installed")
        return 0, "0000000000001234 T ggml_compute_forward\n"
    investigate = _inv.make_investigator(source_root="SRC", binary="/lib/libggml.so", runner=runner)
    obs = investigate({"kind": "sym", "name": "ggml_compute_forward"})
    assert obs["provider"] == "binutils" and obs["result"]["found"] is True


def test_loop_agentic_drives_to_finalize():
    with tempfile.TemporaryDirectory() as d:
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))
        script = iter([
            '{"action":"investigate","query":{"kind":"sym","name":"a"},"rationale":"scout"}',
            '{"action":"decompile","fn":"a","rationale":"go"}',
            '{"action":"finalize","rationale":"done"}',
        ])
        decide = _agent.make_policy(lambda p: next(script))
        investigate = _inv.make_investigator(source_root="SRC",
            runner=lambda cmd, timeout=30: (0, '[{"name":"a"}]'))
        finding = loop.run_loop(
            functions=["a"],
            target={"path": "/bin/x", "sha256": "0" * 64, "source_ref": "v"},
            decompiler_meta={"model": "m", "model_sha256": "0" * 64, "temperature": 0},
            ledger_=lg,
            decompile=lambda fn: ("p", "int a(){}", 0.9),
            refine=lambda fn, prev: ("int a(){}", 0.95),
            dynamic=lambda fn: (None, None),
            budget_iters=10, decide=decide, investigate=investigate)
        assert finding["kind"] == "oracle_finding"
        payloads = [e["payload"] for e in lg.entries()]
        kinds = [p["kind"] for p in payloads]
        assert "observation" in kinds and "finding" in kinds
        decs = [p for p in payloads if p["kind"] == "decision"]
        assert any(p.get("rationale") == "go" and p.get("model") for p in decs)
        assert lg.verify()


def test_loop_default_brain_unchanged():
    """No decide/investigate => identical finding + ledger to explicit policy.next_action."""
    def run(d, **extra):
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))
        f = loop.run_loop(
            functions=["a", "b"],
            target={"path": "/bin/x", "sha256": "0" * 64, "source_ref": "v"},
            decompiler_meta={"model": "m", "model_sha256": "0" * 64, "temperature": 0},
            ledger_=lg,
            decompile=lambda fn: ("p", f"int {fn}(){{}}", 0.9),
            refine=lambda fn, prev: (f"int {fn}(){{}}", 0.95),
            dynamic=lambda fn: (None, None),
            budget_iters=20, **extra)
        return f, [e["payload"] for e in lg.entries()]
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        f_default, led_default = run(d1)
        f_explicit, led_explicit = run(d2, decide=policy.next_action)
        assert f_default == f_explicit and led_default == led_explicit


def test_loop_agentic_budget_hard_gate():
    """A stubborn LLM that always returns a valid action still terminates at budget."""
    with tempfile.TemporaryDirectory() as d:
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))
        decide = _agent.make_policy(lambda p: '{"action":"investigate","query":{"kind":"sym","name":"a"}}')
        investigate = _inv.make_investigator(source_root="SRC",
            runner=lambda cmd, timeout=30: (0, '[]'))
        finding = loop.run_loop(
            functions=["a"],
            target={"path": "/bin/x", "sha256": "0" * 64, "source_ref": "v"},
            decompiler_meta={"model": "m", "model_sha256": "0" * 64, "temperature": 0},
            ledger_=lg,
            decompile=lambda fn: ("p", "int a(){}", 0.9),
            refine=lambda fn, prev: ("int a(){}", 0.95),
            dynamic=lambda fn: (None, None),
            budget_iters=5, decide=decide, investigate=investigate)
        assert finding["kind"] == "oracle_finding"
        payloads = [e["payload"] for e in lg.entries()]
        assert sum(1 for p in payloads if p["kind"] == "observation") == 5  # exactly budget
        assert any(p.get("reason") == "budget_exhausted"
                   for p in payloads if p["kind"] == "decision")
        assert lg.verify()


def test_parse_args_agent_flags():
    ns = oracle_cli.parse_args(["run", "--target", "/bin/x", "--funcs", "a",
                                "--agent", "--crabcc-root", "/src", "--llm-model", "m7"])
    assert ns.agent is True and ns.crabcc_root == "/src" and ns.llm_model == "m7"


# --- slice 4a: reverser debate-panel team -----------------------------------
import panel as _panel  # noqa: E402
import team as _team  # noqa: E402
import memory as _mem  # noqa: E402


def test_panel_runs_all_candidates_order_stable():
    ps = [_panel.Panelist("zeta", lambda p: "Z"), _panel.Panelist("alpha", lambda p: "A")]
    out = _panel.run_panel("fn", "pseudo", "", ps)
    assert [o["panelist"] for o in out] == ["alpha", "zeta"]
    assert all(o["refined_c"] for o in out)


def test_panel_panelist_error_degrades():
    def boom(p):
        raise RuntimeError("down")
    out = _panel.run_panel("fn", "pc", "", [_panel.Panelist("a", lambda p: "A"), _panel.Panelist("b", boom)])
    d = {o["panelist"]: o for o in out}
    assert d["a"]["refined_c"] == "A"
    assert d["b"]["refined_c"] is None and d["b"]["error"]


def test_select_effort_none_on_agreement():
    cands = [{"refined_c": "int f(){}"}, {"refined_c": "int f(){}"}]
    assert _panel.select_effort(cands, None) == "none"


def test_select_effort_high_max_none_by_fidelity():
    cands = [{"refined_c": "a"}, {"refined_c": "bbb"}]
    assert _panel.select_effort(cands, [0.5, 0.6]) == "high"
    assert _panel.select_effort(cands, [0.1, 0.2]) == "max"
    assert _panel.select_effort(cands, [0.9, 0.1]) == "none"   # max fidelity >= threshold


def test_openai_client_reasoning_and_temp():
    c = _panel.OpenAIChatClient("http://x/v1", "mymodel", temperature=1.0, reasoning_effort="high")
    b = c._build_body("hi", c.reasoning_effort)
    assert b["temperature"] == 1.0 and b["reasoning"] == {"effort": "high"} and b["model"] == "mymodel"
    assert "reasoning" not in c._build_body("hi", None)


def test_judge_pick_parses():
    cands = [{"panelist": "a", "refined_c": "AAA"}, {"panelist": "b", "refined_c": "BBB"}]
    judge = lambda prompt, reasoning_effort=None: '{"mode":"pick","index":1,"rationale":"b"}'
    v = _panel.judge_candidates("fn", cands, "", judge, effort="high")
    assert v["mode"] == "pick" and v["refined_c"] == "BBB" and v["drew_from"] == ["b"]


def test_judge_merge_parses():
    cands = [{"panelist": "a", "refined_c": "AAA"}, {"panelist": "b", "refined_c": "BBB"}]
    judge = lambda prompt, reasoning_effort=None: '{"mode":"merge","refined_c":"MERGED","drew_from":[0,1],"rationale":"x"}'
    v = _panel.judge_candidates("fn", cands, "", judge)
    assert v["mode"] == "merge" and v["refined_c"] == "MERGED" and v["drew_from"] == ["a", "b"]


def test_judge_fallback_on_garbage():
    cands = [{"panelist": "a", "refined_c": "AAA"}, {"panelist": "b", "refined_c": "BBB"}]
    judge = lambda prompt, reasoning_effort=None: "not json"
    v = _panel.judge_candidates("fn", cands, "", judge, fidelities=[0.2, 0.7])
    assert v["mode"] == "fallback" and v["refined_c"] == "BBB"   # best fidelity


def test_debate_function_end_to_end():
    ps = [_panel.Panelist("a", lambda p: "int f(){}"), _panel.Panelist("b", lambda p: "int f(){return 1;}")]
    judge = lambda prompt, reasoning_effort=None: '{"mode":"pick","index":0,"rationale":"a"}'
    r = _panel.debate_function("f", "pc", "", ps, judge, score=lambda c, gt: 0.5, ground_truth="src")
    assert r["chosen"] == "int f(){}" and r["effort"] == "high"
    assert "candidates" in r and r["verdict"]["mode"] == "pick"


def test_load_roster_keyenv_degrade():
    with tempfile.TemporaryDirectory() as d:
        rp = os.path.join(d, "roster.json")
        json.dump({"panelists": [
            {"name": "local", "endpoint": "http://x/v1", "model": "m", "key_env": None},
            {"name": "paid", "endpoint": "http://y/v1", "model": "m2", "key_env": "NOPE_KEY_XYZ"}],
            "judge": {"name": "j", "endpoint": "http://z/v1", "model": "jm", "key_env": None}},
            open(rp, "w"))
        os.environ.pop("NOPE_KEY_XYZ", None)
        ps, judge = _panel.load_roster(rp)
        names = [p.name for p in ps]
        assert "local" in names and "paid" not in names and judge is not None


def test_memory_remember_recall_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        m = _mem.TeamMemory(os.path.join(d, "dossier.jsonl"))
        m.remember(run_id="r", fn="llama_decode", kind="finding", text="llama_decode calls decode_impl", tags=["llama_decode"])
        m.remember(run_id="r", fn="other", kind="finding", text="unrelated", tags=["other"])
        hits = m.recall("decode")
        assert hits and hits[0]["fn"] == "llama_decode"


def test_memory_recall_empty_safe():
    with tempfile.TemporaryDirectory() as d:
        m = _mem.TeamMemory(os.path.join(d, "dossier.jsonl"))
        assert m.recall("anything") == [] and m.inject("fn", "fn") == ""


def test_memory_recall_survives_corrupt_line():
    """A partial/corrupt dossier line (interrupted write) must not crash recall."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "dossier.jsonl")
        m = _mem.TeamMemory(p)
        m.remember(run_id="r", fn="llama_decode", kind="finding", text="decode info", tags=["llama_decode"])
        with open(p, "a") as f:
            f.write('{"partial": tru')   # corrupt/partial line
        assert m.recall("llama_decode")[0]["fn"] == "llama_decode"


def test_memory_tags_boost():
    with tempfile.TemporaryDirectory() as d:
        m = _mem.TeamMemory(os.path.join(d, "dossier.jsonl"))
        m.remember(run_id="r", fn="x", kind="k", text="nothing relevant here", tags=["decode"])
        m.remember(run_id="r", fn="y", kind="k", text="decode appears in body", tags=[])
        assert m.recall("decode")[0]["fn"] == "x"   # tag weight 2 > body weight 1


def test_investigate_ctags_provider_parses():
    def runner(cmd, timeout=30):
        if cmd[0] == "ctags":
            return 0, '{"_type":"tag","name":"llama_decode","kind":"function","signature":"(ctx)","path":"x.cpp","line":10}\n'
        return 1, ""
    obs = _inv.make_investigator(source_root="SRC", runner=runner)({"kind": "sym", "name": "llama_decode"})
    assert obs["provider"] == "ctags" and obs["result"][0]["name"] == "llama_decode"


def test_investigate_chain_crabcc_ctags_binutils():
    o1 = _inv.make_investigator(source_root="S", runner=lambda cmd, timeout=30: (0, '[{"name":"f"}]') if cmd[0] == "crabcc" else (1, ""))({"kind": "sym", "name": "f"})
    assert o1["provider"] == "crabcc"

    def r2(cmd, timeout=30):
        if cmd[0] == "ctags":
            return 0, '{"_type":"tag","name":"f","kind":"function"}'
        return 1, ""
    assert _inv.make_investigator(source_root="S", runner=r2)({"kind": "sym", "name": "f"})["provider"] == "ctags"

    def r3(cmd, timeout=30):
        return (0, "0001 T f\n") if cmd[0] == "nm" else (1, "")
    assert _inv.make_investigator(source_root="S", binary="/lib/x.so", runner=r3)({"kind": "sym", "name": "f"})["provider"] == "binutils"


def test_run_team_drives_and_records():
    with tempfile.TemporaryDirectory() as d:
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))
        mem = _mem.TeamMemory(os.path.join(d, "dossier.jsonl"))
        ps = [_panel.Panelist("a", lambda p: "int x(){}"), _panel.Panelist("b", lambda p: "int y(){}")]
        judge = lambda prompt, reasoning_effort=None: '{"mode":"pick","index":0,"rationale":"a"}'
        finding = _team.run_team(
            functions=["f1", "f2"],
            target={"path": "/bin/x", "sha256": "0" * 64, "source_ref": "v"},
            decompiler_meta={"model": "team", "model_sha256": "0" * 64, "temperature": 0},
            ledger_=lg, decompile=lambda fn: "pseudo " + fn,
            panelists=ps, judge_client=judge,
            score=lambda c, gt: 0.5, ground_truth=lambda fn: "src", memory=mem, budget_calls=60)
        assert finding["kind"] == "oracle_finding" and len(finding["functions"]) == 2
        kinds = [e["payload"]["kind"] for e in lg.entries()]
        assert kinds.count("candidate") == 4 and kinds.count("verdict") == 2 and "finding" in kinds
        assert lg.verify() and mem.recall("f1")


def test_run_team_budget_calls_stops():
    with tempfile.TemporaryDirectory() as d:
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))
        ps = [_panel.Panelist("a", lambda p: "A"), _panel.Panelist("b", lambda p: "B")]
        judge = lambda prompt, reasoning_effort=None: '{"mode":"pick","index":0}'
        finding = _team.run_team(
            functions=["f1", "f2", "f3"],
            target={"path": "/b", "sha256": "0" * 64, "source_ref": "v"},
            decompiler_meta={"model": "t", "model_sha256": "0" * 64, "temperature": 0},
            ledger_=lg, decompile=lambda fn: "p", panelists=ps, judge_client=judge, budget_calls=3)
        payloads = [e["payload"] for e in lg.entries()]
        assert any(p.get("reason") == "budget_exhausted" for p in payloads)
        assert finding["kind"] == "oracle_finding"


def test_run_team_uses_recall_context():
    seen = {}
    def client(p):
        seen["prompt"] = p
        return "int f(){}"
    with tempfile.TemporaryDirectory() as d:
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))
        mem = _mem.TeamMemory(os.path.join(d, "dossier.jsonl"))
        mem.remember(run_id="r", fn="f1", kind="finding", text="f1 calls helper_42", tags=["f1"])
        judge = lambda prompt, reasoning_effort=None: '{"mode":"pick","index":0}'
        _team.run_team(functions=["f1"], target={"path": "/b", "sha256": "0" * 64, "source_ref": "v"},
            decompiler_meta={"model": "t", "model_sha256": "0" * 64, "temperature": 0},
            ledger_=lg, decompile=lambda fn: "pseudo", panelists=[_panel.Panelist("a", client)],
            judge_client=judge, memory=mem, budget_calls=10)
        assert "helper_42" in seen["prompt"]


def test_parse_args_team_flags():
    ns = oracle_cli.parse_args(["team", "--target", "/b", "--funcs", "a,b", "--panel", "/p.json",
                                "--budget-calls", "12", "--memory", "/m.jsonl"])
    assert ns.cmd == "team" and ns.panel == "/p.json" and ns.budget_calls == 12
    assert ns.funcs == ["a", "b"] and ns.memory == "/m.jsonl"


# ---- slice 4b thread 1: team-in-vaked ----
def _team_graph():
    """A minimal lowered-LPG fixture mirroring oracle-team.vaked (numbers are strings)."""
    def s(v): return {"lit": "string", "value": v}
    def num(v): return {"lit": "number", "value": v}
    def cap(ref): return {"ref": ref}
    return {"version": 1, "nodes": [
        {"kind": "node", "name": "operator", "props": {
            "role": s("control-plane"), "capabilities": [cap("fs.repo_rw"), cap("network.egress"), cap("mem.admin")]}},
        {"kind": "node", "name": "coordinator", "props": {
            "role": s("coordinate"), "capabilities": [cap("fs.repo_rw"), cap("network.loopback")], "budgetCalls": num("30")}},
        {"kind": "node", "name": "infralight", "props": {
            "role": s("panelist"), "model": s("qwen2.5-coder-3b-instruct"),
            "capabilities": [cap("network.loopback")],
            "endpoint": s("http://127.0.0.1:8091/v1/chat/completions"), "temperature": num("0")}},
        {"kind": "node", "name": "feketecs", "props": {
            "role": s("panelist"), "model": s("deepseek/deepseek-v4-flash"),
            "capabilities": [cap("network.egress")],
            "endpoint": s("https://openrouter.ai/api/v1/chat/completions"),
            "keyEnv": s("OPENROUTER_API_KEY"), "temperature": num("1")}},
        {"kind": "node", "name": "anstetten", "props": {
            "role": s("judge"), "model": s("deepseek/deepseek-v4-pro"),
            "capabilities": [cap("network.egress")],
            "endpoint": s("https://openrouter.ai/api/v1/chat/completions"),
            "keyEnv": s("OPENROUTER_API_KEY"), "temperature": num("1"), "reasoningEffort": s("high")}},
        {"kind": "network", "name": "feketecsCordon", "props": {
            "principal": s("feketecs"), "default": s("deny"),
            "allow": [{"ref": "egress", "args": [s("openrouter.ai"), num("443")]}]}},
        {"kind": "network", "name": "anstettenCordon", "props": {
            "principal": s("anstetten"), "default": s("deny"),
            "allow": [{"ref": "egress", "args": [s("openrouter.ai"), num("443")]}]}},
    ]}


def test_roster_from_vaked_extracts_panelists_judge_budget():
    import os
    import roster_from_vaked as rfv
    os.environ["OPENROUTER_API_KEY"] = "test-key-not-real"
    try:
        panelists, judge, budget = rfv.load_roster_from_graph(_team_graph())
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)
    names = sorted(p.name for p in panelists)
    assert names == ["feketecs", "infralight"]
    assert getattr(judge, "model", None) == "deepseek/deepseek-v4-pro"
    assert budget == 30
    feke = next(p for p in panelists if p.name == "feketecs")
    assert feke.client.temperature == 1.0
    assert judge.reasoning_effort == "high"


def test_roster_from_vaked_drops_node_with_absent_key_env():
    import os
    import roster_from_vaked as rfv
    os.environ.pop("OPENROUTER_API_KEY", None)
    panelists, judge, budget = rfv.load_roster_from_graph(_team_graph())
    names = sorted(p.name for p in panelists)
    assert names == ["infralight"]
    assert judge is panelists[0].client


def test_egress_check_clean_graph_has_no_violations():
    import roster_from_vaked as rfv
    assert rfv.check_roster_egress(_team_graph()) == []


def test_egress_check_loopback_endpoint_needs_no_membrane():
    import roster_from_vaked as rfv
    g = _team_graph()
    # drop both cordons; loopback nodes still clean, egress nodes now violate
    g["nodes"] = [n for n in g["nodes"] if n.get("kind") != "network"]
    names = sorted(v["node"] for v in rfv.check_roster_egress(g))
    assert names == ["anstetten", "feketecs"]            # loopback infralight is clean


def test_egress_check_endpoint_outside_allow_set_is_a_violation():
    import roster_from_vaked as rfv
    g = _team_graph()
    # point feketecs at an undeclared host
    for n in g["nodes"]:
        if n.get("name") == "feketecs":
            n["props"]["endpoint"] = {"lit": "string", "value": "https://evil.example/v1/chat/completions"}
    viol = rfv.check_roster_egress(g)
    assert [v["node"] for v in viol] == ["feketecs"]
    assert viol[0]["host"] == "evil.example"
    assert viol[0]["port"] == 443


def test_egress_check_port_mismatch_is_a_violation():
    import roster_from_vaked as rfv
    g = _team_graph()
    # feketecs cordon allows openrouter.ai:443; endpoint dials :8443 (right host, wrong port)
    for n in g["nodes"]:
        if n.get("name") == "feketecs":
            n["props"]["endpoint"] = {"lit": "string", "value": "https://openrouter.ai:8443/v1/chat/completions"}
    viol = rfv.check_roster_egress(g)
    assert [v["node"] for v in viol] == ["feketecs"]
    assert viol[0]["port"] == 8443


def test_team_from_vaked_parses():
    import oracle
    ns = oracle.parse_args(["team", "--target", "/bin/true", "--funcs", "f",
                            "--from-vaked", "graph.json"])
    assert ns.from_vaked == "graph.json"
    assert ns.panel is None


def test_team_panel_and_from_vaked_mutually_exclusive():
    import oracle
    try:
        oracle.parse_args(["team", "--target", "/bin/true", "--funcs", "f",
                           "--panel", "p.json", "--from-vaked", "graph.json"])
        assert False, "expected SystemExit (mutually exclusive)"
    except SystemExit:
        pass


def test_team_requires_one_roster_source():
    import oracle
    try:
        oracle.parse_args(["team", "--target", "/bin/true", "--funcs", "f"])
        assert False, "expected SystemExit (one of --panel/--from-vaked required)"
    except SystemExit:
        pass


def _ebpf_policy_doc():
    # the exact shape vakedc lower emits for oracle-team: loopback cordon gets a real
    # IP rule; the OpenRouter cordon's DNS host is DROPPED at lower -> allow [].
    return {"runtime": "oracle-team", "version": 1, "membranes": [
        {"membrane": "infralightCordon", "principal": "infralight", "grant": "network.loopback",
         "default": "deny", "allow": [
             {"proto": "tcp", "host": "127.0.0.1", "cidr": "127.0.0.1/32", "port": 8091}]},
        {"membrane": "feketecsCordon", "principal": "feketecs", "grant": "network.egress",
         "default": "deny", "allow": []},      # DNS host dropped at lower -> deny-all
    ]}


def test_ebpf_manifest_loads_and_decides():
    import os
    import json
    import tempfile
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # repo root for agent_guardd
    from agent_guardd import policy as agp
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(_ebpf_policy_doc(), f)
        path = f.name
    pol = agp.load_policy(path)
    loop = pol.membrane_for("infralight")
    feke = pol.membrane_for("feketecs")
    # loopback IP rule -> enforceable (fully eBPF-attestable)
    assert agp.decide(loop, "127.0.0.1", 8091)[0] == "allow"
    assert agp.decide(loop, "127.0.0.1", 9999)[0] == "deny"
    # OpenRouter cordon -> deny-all (DNS dropped at lower; also non-IP at decide). The
    # documented gap: packet-layer egress to OpenRouter is un-attestable; the tool-layer
    # check_roster_egress is the only enforcement.
    assert agp.decide(feke, "openrouter.ai", 443)[0] == "deny"
    os.unlink(path)


# ---- outside-model prompt dogfeed ----
def test_dogfeed_sink_outside_model_only_and_leakfree():
    import os, json, tempfile
    import urllib.request as U
    import panel
    class _Resp:
        def __init__(self, d): self._d = d
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(self._d).encode()
    fake = {"choices": [{"message": {"content": "PONG"}}],
            "usage": {"completion_tokens": 7, "cost": 0.0009}}
    orig = U.urlopen
    U.urlopen = lambda req, timeout=None: _Resp(fake)
    log = tempfile.mktemp(suffix=".jsonl")
    os.environ["ORACLE_DOGFEED_LOG"] = log
    try:
        out = panel.OpenAIChatClient("https://openrouter.ai/x", "deepseek/deepseek-v4-pro",
                                     "sekret-key", reasoning_effort="high")
        assert out("Reverse-engineer fn foo\npseudo-c body") == "PONG"
        recs = [json.loads(l) for l in open(log) if l.strip()]
        assert len(recs) == 1
        r = recs[0]
        assert r["model"] == "deepseek/deepseek-v4-pro"
        assert r["completion_tokens"] == 7 and r["cost"] == 0.0009 and r["reasoning"] is True
        assert r["first_line"] == "Reverse-engineer fn foo"
        assert len(r["prompt_sha"]) == 64
        assert "sekret-key" not in json.dumps(r)
        os.remove(log)
        loc = panel.OpenAIChatClient("http://127.0.0.1:8091/x", "qwen", "")
        assert loc("hi there") == "PONG"
        assert (not os.path.exists(log)) or sum(1 for _ in open(log)) == 0
    finally:
        U.urlopen = orig
        os.environ.pop("ORACLE_DOGFEED_LOG", None)
        if os.path.exists(log): os.remove(log)


def test_dogfeed_sink_noop_when_env_unset():
    import os, json
    import urllib.request as U
    import panel
    class _Resp:
        def __init__(self, d): self._d = d
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(self._d).encode()
    orig = U.urlopen
    U.urlopen = lambda req, timeout=None: _Resp({"choices": [{"message": {"content": "X"}}], "usage": {}})
    os.environ.pop("ORACLE_DOGFEED_LOG", None)
    try:
        c = panel.OpenAIChatClient("https://openrouter.ai/x", "m", "k")
        assert c("p") == "X"
    finally:
        U.urlopen = orig


def test_dogfeed_load_records_skips_corrupt():
    import dogfeed_prompts as dp, tempfile, os
    p = tempfile.mktemp(suffix=".jsonl")
    open(p, "w").write('{"model":"a"}\nNOT JSON\n\n{"model":"b"}\n')
    recs = dp.load_records(p)
    assert [r["model"] for r in recs] == ["a", "b"]
    os.remove(p)


def test_dogfeed_summarize_math():
    import dogfeed_prompts as dp
    recs = [{"model": "a", "completion_tokens": 10, "cost": 0.001},
            {"model": "a", "completion_tokens": 5, "cost": 0.002},
            {"model": "b", "completion_tokens": 3, "cost": None}]
    s = dp.summarize(recs)
    assert s["n"] == 3
    assert s["by_model"]["a"] == {"calls": 2, "tokens": 15, "cost": 0.003}
    assert s["by_model"]["b"]["tokens"] == 3
    assert abs(s["total_cost"] - 0.003) < 1e-9


def test_dogfeed_build_comment_cap_and_leakfree():
    import dogfeed_prompts as dp
    recs = [{"model": "deepseek/deepseek-v4-pro", "prompt_sha": "a" * 64,
             "first_line": "Reverse-engineer fn x", "completion_tokens": 100,
             "cost": 0.002, "reasoning": True} for _ in range(3)]
    c = dp.build_comment(recs, run_id="r1", cap=2)
    assert "deepseek/deepseek-v4-pro" in c
    assert "| 3 |" in c
    assert "more (capped)" in c
    assert "Bearer" not in c and "sekret" not in c


def test_dogfeed_find_or_create_returns_existing():
    import dogfeed_prompts as dp, json
    calls = []
    def fake_gh(args):
        calls.append(args)
        if args[1] == "list":
            return json.dumps([{"number": 42, "title": dp.ISSUE_TITLE}])
        raise AssertionError("must not create when issue exists")
    assert dp.find_or_create_issue(dp.ISSUE_TITLE, repo="o/r", gh=fake_gh) == 42
    assert all(a[1] != "create" for a in calls)


def test_dogfeed_find_or_create_creates_when_absent():
    import dogfeed_prompts as dp
    def fake_gh(args):
        if args[1] == "list": return "[]"
        if args[1] == "create": return "https://github.com/o/r/issues/77\n"
        raise AssertionError
    assert dp.find_or_create_issue(dp.ISSUE_TITLE, repo="o/r", gh=fake_gh) == 77


def test_dogfeed_post_appends_comment():
    import dogfeed_prompts as dp, json
    calls = []
    def fake_gh(args):
        calls.append(args)
        if args[1] == "list": return json.dumps([{"number": 5, "title": dp.ISSUE_TITLE}])
        return ""
    n = dp.post([{"model": "m", "completion_tokens": 1, "cost": 0.0,
                  "prompt_sha": "x" * 64, "first_line": "hi"}],
                repo="o/r", run_id="r", gh=fake_gh)
    assert n == 5
    assert any(a[0] == "issue" and a[1] == "comment" and a[2] == "5" for a in calls)


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
