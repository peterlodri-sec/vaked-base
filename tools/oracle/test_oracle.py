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
    # hook.js emits one JSON line per call event
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
