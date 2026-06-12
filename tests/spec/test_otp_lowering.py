#!/usr/bin/env python3
"""test_otp_lowering.py — the otp.supervision emitter (#19, Track C).

Asserts the design contract
(docs/superpowers/specs/2026-06-12-otp-supervision-lowering-design.md)
over the daily-use target system, structure + bytes (CI has no Erlang;
``task otp-smoke`` in the devshell is the runnability gate):

1. **artifacts.** `vakedc lower` on agentfield-swe emits
   ``gen/otp/agent_field_sup.erl`` (module name == filename slug — OTP rule)
   and ``gen/otp/vaked_fiber_worker.erl``.
2. **structure.** One child per `parallel … supervisor = otp` member, in
   declaration order: 'transcriptMiner' (fiber, gen/zig config path) and
   'fieldView' (surface, config => none); v0 strategy is ``one_for_one``
   (no positional restart coupling — RFC 0004 carries downstream
   consistency); worker module declares gen_server callbacks.
3. **gating.** A runtime whose parallel has a non-otp supervisor emits no
   gen/otp artifacts.
4. **determinism.** Two lowers ⇒ byte-identical .erl files.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)

_AF_EXAMPLE = os.path.join("vaked", "examples", "agentfield-swe.vaked")
SUP_REL = "gen/otp/agent_field_sup.erl"
WORKER_REL = "gen/otp/vaked_fiber_worker.erl"


def _lower(out, src=_AF_EXAMPLE):
    return subprocess.run(
        [sys.executable, "-m", "vakedc", "lower", src, "--out", out],
        capture_output=True, text=True, cwd=REPO)


def _test_artifacts_structure(lines):
    ok = True
    tmp = tempfile.mkdtemp(prefix="otp-spec-")
    try:
        out = os.path.join(tmp, "o1")
        r = _lower(out)
        if r.returncode != 0:
            lines.append(f"  FAIL otp: lower failed: {r.stderr.strip()}")
            return False
        sup_p = os.path.join(out, SUP_REL)
        worker_p = os.path.join(out, WORKER_REL)
        for p, rel in ((sup_p, SUP_REL), (worker_p, WORKER_REL)):
            if not os.path.exists(p):
                lines.append(f"  FAIL otp: missing artifact {rel}")
                return False
        sup = open(sup_p, encoding="utf-8").read()
        worker = open(worker_p, encoding="utf-8").read()

        # module name == filename slug (OTP rule)
        if "-module(agent_field_sup)." not in sup:
            ok = False
            lines.append("  FAIL otp: sup module name != filename slug")
        if "-module(vaked_fiber_worker)." not in worker:
            ok = False
            lines.append("  FAIL otp: worker module name wrong")

        # v0 strategy: one_for_one, never positional coupling (check the
        # CODE only — the header comment legitimately mentions rest_for_one
        # as the edge-aware follow-up)
        sup_code = "\n".join(l for l in sup.splitlines()
                             if not l.startswith("%%"))
        if "strategy => one_for_one" not in sup_code \
                or "rest_for_one" in sup_code:
            ok = False
            lines.append("  FAIL otp: v0 strategy must be one_for_one")

        # one child per member, declared order, kinds + config paths
        ids = re.findall(r"#\{id => '([^']+)'", sup)
        if ids != ["transcriptMiner", "fieldView"]:
            ok = False
            lines.append(f"  FAIL otp: children {ids} != "
                         f"['transcriptMiner', 'fieldView']")
        if 'config => "gen/zig/transcriptMiner.json"' not in sup:
            ok = False
            lines.append("  FAIL otp: fiber child missing zig config path")
        if "kind => surface" not in sup or "config => none" not in sup:
            ok = False
            lines.append("  FAIL otp: surface child missing kind/none config")

        # worker is a real gen_server skeleton
        for needle in ("-behaviour(gen_server).", "handle_info(tick",
                       "erlang:send_after"):
            if needle not in worker:
                ok = False
                lines.append(f"  FAIL otp: worker missing {needle!r}")

        # provenance entries registry-tagged
        prov = json.load(open(os.path.join(out, "provenance.json")))
        for rel in (SUP_REL, WORKER_REL):
            ents = prov["artifacts"].get(rel, [])
            if not ents or any(e["emitter"] != "otp.supervision"
                               for e in ents):
                ok = False
                lines.append(f"  FAIL otp: provenance for {rel} not tagged "
                             f"otp.supervision")
        if ok:
            lines.append("  artifacts+structure: sup module (2 children, "
                         "declared order, one_for_one) + gen_server worker, "
                         "provenance tagged")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def _test_slug(lines):
    """Slugs are strictly [a-z][a-z0-9_]* — pure ASCII, whatever the runtime
    name throws at them (Unicode digits/letters must not leak into module
    names; erlc rejects them)."""
    from vakedc.lower import _otp_slug
    pat = re.compile(r"^[a-z][a-z0-9_]*$")
    cases = ["agent-field", "operator-field", "٣", "Łódź-9", "9lives",
             "", "agent.field v2"]
    bad = [(n, _otp_slug(n)) for n in cases
           if not (pat.match(_otp_slug(n)) and _otp_slug(n).isascii())]
    if bad:
        lines.append(f"  FAIL otp-slug: illegal slugs: {bad}")
        return False
    if _otp_slug("agent-field") != "agent_field":
        lines.append(f"  FAIL otp-slug: agent-field → "
                     f"{_otp_slug('agent-field')!r}")
        return False
    lines.append("  slug: hostile names (unicode digits/letters, leading "
                 "digit, empty) all lower to [a-z][a-z0-9_]*")
    return True


def _test_duplicate_members(lines):
    """A repeated member (within a list or across otp groups) must emit ONE
    child spec — OTP rejects duplicate child ids at boot
    ({error,{start_spec,{duplicate_child_name,_}}})."""
    tmp = tempfile.mkdtemp(prefix="otp-spec-")
    try:
        src = ('runtime "t" {\n  systems = ["x86_64-linux"]\n'
               '  engine e { package = nix.derivation }\n'
               '  stream s { source = agentpipe.s  type = Agent.T }\n'
               '  fiber f { engine = e  input = stream.s  output = artifacts.x }\n'
               '  parallel "p" {\n    fibers = [f, f]\n'
               '    strategy = "supervised-dag"\n    supervisor = otp\n  }\n'
               '  parallel "q" {\n    fibers = [f]\n'
               '    strategy = "supervised-dag"\n    supervisor = otp\n  }\n}\n')
        vp = os.path.join(tmp, "dup.vaked")
        open(vp, "w", encoding="utf-8").write(src)
        out = os.path.join(tmp, "out")
        r = _lower(out, src=vp)
        if r.returncode != 0:
            lines.append(f"  FAIL otp-dup: lower failed: {r.stderr.strip()}")
            return False
        sup = open(os.path.join(out, "gen/otp/t_sup.erl"),
                   encoding="utf-8").read()
        ids = re.findall(r"#\{id => '([^']+)'", sup)
        if ids != ["f"]:
            lines.append(f"  FAIL otp-dup: expected one deduped child ['f'], "
                         f"got {ids}")
            return False
        lines.append("  duplicate-members: repeated member (in-list + "
                     "cross-group) emits exactly one child spec")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _test_gating(lines):
    tmp = tempfile.mkdtemp(prefix="otp-spec-")
    try:
        src = ('runtime "t" {\n  systems = ["x86_64-linux"]\n'
               '  engine e { package = nix.derivation }\n'
               '  stream s { source = agentpipe.s  type = Agent.T }\n'
               '  fiber f { engine = e  input = stream.s  output = artifacts.x }\n'
               '  parallel "p" {\n    fibers = [f]\n'
               '    strategy = "supervised-dag"\n    supervisor = beam2\n  }\n}\n')
        vp = os.path.join(tmp, "nonotp.vaked")
        open(vp, "w", encoding="utf-8").write(src)
        out = os.path.join(tmp, "out")
        r = _lower(out, src=vp)
        if r.returncode != 0:
            lines.append(f"  FAIL otp-gating: lower failed: {r.stderr.strip()}")
            return False
        if os.path.exists(os.path.join(out, "gen", "otp")):
            lines.append("  FAIL otp-gating: non-otp supervisor emitted "
                         "gen/otp artifacts")
            return False
        lines.append("  gating: non-otp supervisor emits no gen/otp artifacts")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _test_colmena(lines):
    """#51: host decls lower to gen/colmena/hive.nix — node per host with
    targetHost/system; `deploy = "local"` flips to allowLocalDeployment;
    no hosts => no gen/colmena; byte-deterministic."""
    ok = True
    tmp = tempfile.mkdtemp(prefix="otp-spec-")
    try:
        # agentfield-swe declares host vps (ssh form)
        outs = []
        for d in ("c1", "c2"):
            out = os.path.join(tmp, d)
            r = _lower(out)
            if r.returncode != 0:
                lines.append(f"  FAIL colmena: lower failed: {r.stderr.strip()}")
                return False
            outs.append(out)
        hive_p = os.path.join(outs[0], "gen/colmena/hive.nix")
        if not os.path.exists(hive_p):
            lines.append("  FAIL colmena: hive.nix not emitted for host decl")
            return False
        hive = open(hive_p, encoding="utf-8").read()
        for needle in ('"vps" = { ... }: {',
                       'deployment.targetHost = "root@vps";',
                       'nixpkgs.system = "x86_64-linux";',
                       "nixpkgs = <nixpkgs>;",   # PATH form (per-node system honored)
                       "imports = [ ../../nixos/agent-field.nix ];"):
            if needle not in hive:
                ok = False
                lines.append(f"  FAIL colmena: hive missing {needle!r}")
        b1 = open(hive_p, "rb").read()
        b2 = open(os.path.join(outs[1], "gen/colmena/hive.nix"), "rb").read()
        if b1 != b2:
            ok = False
            lines.append("  FAIL colmena: hive.nix not byte-identical across runs")

        # local-deploy variant + provenance tagging
        src = ('runtime "t" {\n  systems = ["x86_64-linux"]\n'
               '  host box { system = "x86_64-linux"  deploy = "local" }\n}\n')
        vp = os.path.join(tmp, "local.vaked")
        open(vp, "w", encoding="utf-8").write(src)
        lout = os.path.join(tmp, "local")
        r = _lower(lout, src=vp)
        lhive = open(os.path.join(lout, "gen/colmena/hive.nix"),
                     encoding="utf-8").read()
        if "deployment.allowLocalDeployment = true;" not in lhive \
                or "deployment.targetHost = null;" not in lhive:
            ok = False
            lines.append("  FAIL colmena: local deploy form wrong "
                         "(needs allowLocalDeployment + targetHost = null)")
        prov = json.load(open(os.path.join(lout, "provenance.json")))
        ents = prov["artifacts"].get("gen/colmena/hive.nix", [])
        if not ents or any(e["emitter"] != "colmena.hive" for e in ents):
            ok = False
            lines.append("  FAIL colmena: provenance not tagged colmena.hive")

        # injection: ${ antiquotation / quote / backslash in deploy must be
        # neutralized (issue #7 splice class) — no active ${ } in the output
        src = ('runtime "t" {\n  systems = ["x86_64-linux"]\n'
               '  host h { system = "x86_64-linux"  deploy = "a${pwn}b" }\n}\n')
        vp = os.path.join(tmp, "inject.vaked")
        open(vp, "w", encoding="utf-8").write(src)
        iout = os.path.join(tmp, "inject")
        _lower(iout, src=vp)
        ihive = open(os.path.join(iout, "gen/colmena/hive.nix"),
                     encoding="utf-8").read()
        # emitted form is a single backslash before ${ : \${pwn}
        if "${pwn}" in ihive.replace("\${pwn}", ""):
            ok = False
            lines.append("  FAIL colmena: ${ } antiquotation not neutralized")

        # multi-host: two hosts emit two nodes in declaration order
        src = ('runtime "t" {\n  systems = ["x86_64-linux"]\n'
               '  host alpha { system = "x86_64-linux"  deploy = "ssh://root@a" }\n'
               '  host beta  { system = "aarch64-linux" deploy = "ssh://root@b" }\n}\n')
        vp = os.path.join(tmp, "multi.vaked")
        open(vp, "w", encoding="utf-8").write(src)
        mout = os.path.join(tmp, "multi")
        _lower(mout, src=vp)
        mhive = open(os.path.join(mout, "gen/colmena/hive.nix"),
                     encoding="utf-8").read()
        ia, ib = mhive.find('"alpha"'), mhive.find('"beta"')
        if ia < 0 or ib < 0 or ia > ib:
            ok = False
            lines.append("  FAIL colmena: two hosts not both present in "
                         "declaration order")

        # gating: hostless runtime emits no gen/colmena
        src = ('runtime "t" {\n  systems = ["x86_64-linux"]\n'
               '  stream s { source = agentpipe.s  type = Agent.T }\n}\n')
        vp = os.path.join(tmp, "nohost.vaked")
        open(vp, "w", encoding="utf-8").write(src)
        nout = os.path.join(tmp, "nohost")
        _lower(nout, src=vp)
        if os.path.exists(os.path.join(nout, "gen", "colmena")):
            ok = False
            lines.append("  FAIL colmena: hostless runtime emitted gen/colmena")
        if ok:
            lines.append("  colmena: hive per host (ssh + local forms), "
                         "gated on presence, provenance tagged, deterministic")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def _test_determinism(lines):
    tmp = tempfile.mkdtemp(prefix="otp-spec-")
    try:
        blobs = []
        for d in ("a", "b"):
            out = os.path.join(tmp, d)
            r = _lower(out)
            if r.returncode != 0:
                lines.append(f"  FAIL otp-determinism: lower failed: "
                             f"{r.stderr.strip()}")
                return False
            blobs.append(tuple(open(os.path.join(out, rel), "rb").read()
                               for rel in (SUP_REL, WORKER_REL)))
        if blobs[0] != blobs[1]:
            lines.append("  FAIL otp-determinism: .erl files differ across runs")
            return False
        lines.append("  determinism: both .erl files byte-identical across runs")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run():
    lines = []
    ok = True
    for fn in (_test_artifacts_structure, _test_slug,
               _test_duplicate_members, _test_gating, _test_colmena,
               _test_determinism):
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
    print("== test_otp_lowering ==")
    for ln in lines:
        print(ln)
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
