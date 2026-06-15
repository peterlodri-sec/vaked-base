#!/usr/bin/env python3
"""vaked-oracle CLI: drive the RE ralph loop end-to-end on a target binary.

Usage:
  oracle run --target /path/to/llama-cli --funcs ggml_compute,llama_decode \
             --pyghidra-python <venv-python> --frida-python <frida-venv-python> \
             --server http://127.0.0.1:8080/completion \
             --source-dir <llama.cpp src> --watcher-sock /run/oracle-watcher.sock \
             --infer-cmd "llama-completion -m model.gguf -p hello -n 8"
Env vars for PyGhidra: GHIDRA_INSTALL_DIR, JAVA_HOME, ORACLE_LIBSTDCXX_DIR
(the Taskfile derives these from the nix store automatically).
Heavy work runs on dev-cx53; never on the M3.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge      # noqa: E402
import dogfood_bridge as ddb  # noqa: E402
import dynamic_frida as dfr  # noqa: E402
import fidelity    # noqa: E402
import ghidra_frontend as gf  # noqa: E402
import ledger      # noqa: E402
import llm_refine  # noqa: E402
import loop        # noqa: E402
import watcher_client as wc  # noqa: E402

ORACLE_DIR = os.environ.get("ORACLE_DIR", ".oracle")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="oracle")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--target", required=True)
    r.add_argument("--funcs", required=True, type=lambda s: [x for x in s.split(",") if x])
    r.add_argument("--pyghidra-python", default=os.environ.get("ORACLE_PYGHIDRA_PYTHON", "python3"))
    r.add_argument("--server", default=llm_refine.DEFAULT_SERVER)
    r.add_argument("--source-dir", default=None, help="llama.cpp source for fidelity ground truth")
    r.add_argument("--watcher-sock", default=wc.DEFAULT_SOCK)
    r.add_argument("--frida-python", default=os.environ.get("ORACLE_FRIDA_PYTHON", "python3"))
    r.add_argument("--infer-cmd", default=None, help="command to drive a live inference")
    r.add_argument("--watch-seconds", type=int, default=12,
                   help="eBPF watcher trace window (s); wide enough to catch the model-load mmap")
    r.add_argument("--budget-iters", type=int, default=50)
    r.add_argument("--control", default=None)

    g = sub.add_parser("ground", help="record a finding as an aegis kernel transition")
    g.add_argument("--finding", required=True)
    g.add_argument("--root", required=True, help="workspace root; scope is relative to it")
    g.add_argument("--scope", action="append", required=True, help="granted write-scope prefix (repeatable)")
    g.add_argument("--wal-path", default=None, help="eventd WAL (default: .aegis-wal sibling of root)")
    g.add_argument("--blobs", default=None, help="kernel blob store (default: .aegis-wal sibling of root)")
    g.add_argument("--ledger", default=os.path.join(ORACLE_DIR, "events.jsonl"))

    v = sub.add_parser("verify-xref", help="prove a finding's transition_xref link + both chains")
    v.add_argument("--finding", required=True)
    v.add_argument("--wal-path", required=True)
    v.add_argument("--ledger", required=True)
    return p.parse_args(argv)


def persist_finding(finding: dict, *, findings_dir: str) -> str:
    os.makedirs(findings_dir, exist_ok=True)
    h = hashlib.sha256(json.dumps(finding, sort_keys=True).encode()).hexdigest()
    path = os.path.join(findings_dir, f"{h}.json")
    with open(path, "w") as fh:
        json.dump(finding, fh, indent=2, sort_keys=True)
    return path


def _ground_truth(source_dir: str | None, fn: str) -> str | None:
    """Best-effort: grep the source tree for the function body. None if unavailable."""
    if not source_dir:
        return None
    import subprocess
    try:
        out = subprocess.run(["grep", "-rl", fn + "(", source_dir],
                             capture_output=True, text=True, timeout=30).stdout
        first = out.splitlines()[0] if out.strip() else None
        return open(first).read() if first else None
    except Exception:  # noqa: BLE001
        return None


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_run(ns: argparse.Namespace) -> int:
    decomp_map = gf.run_ghidra(binary=ns.target, functions=ns.funcs,
                               pyghidra_python=ns.pyghidra_python)

    def decompile(fn):
        pseudo_c = decomp_map.get(fn, "")
        refined = llm_refine.refine(pseudo_c, server=ns.server) if pseudo_c else None
        gt = _ground_truth(ns.source_dir, fn)
        fid = fidelity.score(refined or "", gt) if (refined and gt) else None
        return (pseudo_c, refined, fid)

    def refine_fn(fn, prev):
        base = prev or decomp_map.get(fn, "")
        refined = llm_refine.refine(base, server=ns.server) if base else None
        gt = _ground_truth(ns.source_dir, fn)
        fid = fidelity.score(refined or "", gt) if (refined and gt) else None
        return (refined, fid)

    def dynamic(fn):
        frida = ebpf = None
        if ns.infer_cmd:
            import subprocess
            proc = subprocess.Popen(ns.infer_cmd.split())
            try:
                ebpf = wc.query_watcher(ns.watcher_sock, pid=proc.pid, duration_s=ns.watch_seconds)
            except Exception:  # noqa: BLE001 (degrade)
                ebpf = None
            try:
                frida = dfr.run_frida(target_cmd=ns.infer_cmd.split(), functions=[fn], frida_python=ns.frida_python).get(fn)
            except Exception:  # noqa: BLE001
                frida = None
            finally:
                try:
                    proc.wait(timeout=60)
                except Exception:  # noqa: BLE001 (never let teardown crash the loop)
                    proc.kill()
        return (frida, ebpf)

    lg = ledger.Ledger(os.path.join(ORACLE_DIR, "events.jsonl"))
    finding = loop.run_loop(
        functions=ns.funcs,
        target={"path": ns.target, "sha256": _sha256_file(ns.target),
                "source_ref": ns.source_dir or "unknown"},
        decompiler_meta={"model": "llm4decompile-6.7b-v2", "model_sha256": "unknown", "temperature": 0},
        ledger_=lg, decompile=decompile, refine=refine_fn, dynamic=dynamic,
        budget_iters=ns.budget_iters, control_path=ns.control)
    finding["observed_effects"] = bridge.to_observed_effects(
        finding, files_written=[os.path.join(ORACLE_DIR, "findings")])
    path = persist_finding(finding, findings_dir=os.path.join(ORACLE_DIR, "findings"))
    print(f"finding: {path}  confidence={finding['confidence']}  chain_ok={lg.verify()}")
    return 0


def _sibling(root: str, name: str) -> str:
    """A path under a `.aegis-wal/` dir that is a SIBLING of root (never under it —
    the kernel snapshots the whole non-git root subtree)."""
    return os.path.join(os.path.dirname(os.path.abspath(root)), ".aegis-wal", name)


def cmd_ground(ns: argparse.Namespace) -> int:
    with open(ns.finding) as fh:
        finding = json.load(fh)
    root = os.path.abspath(ns.root)
    finding_rel = os.path.relpath(os.path.abspath(ns.finding), root)
    wal_path = ns.wal_path or _sibling(root, "wal.jsonl")
    blobs = ns.blobs or _sibling(root, "blobs")
    lg = ledger.Ledger(ns.ledger)
    res = ddb.ground_finding(finding=finding, finding_rel=finding_rel, root=root,
                             scope=ns.scope, wal_path=wal_path, blobs_dir=blobs,
                             oracle_ledger=lg)
    print(f"grounded: transition_xref={res['transition_xref']} "
          f"seq={res['verdict']['seq']} accepted={res['verdict']['accepted']}")
    return 0


def cmd_verify_xref(ns: argparse.Namespace) -> int:
    with open(ns.finding) as fh:
        finding = json.load(fh)
    lg = ledger.Ledger(ns.ledger)
    try:
        ddb.verify_xref(finding=finding, wal_path=ns.wal_path, oracle_ledger=lg)
    except Exception as e:  # noqa: BLE001
        print(f"verify-xref FAIL: {e}")
        return 1
    print("verify-xref OK")
    return 0


def main(argv: list[str]) -> int:
    ns = parse_args(argv)
    if ns.cmd == "run":
        return cmd_run(ns)
    if ns.cmd == "ground":
        return cmd_ground(ns)
    if ns.cmd == "verify-xref":
        return cmd_verify_xref(ns)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
