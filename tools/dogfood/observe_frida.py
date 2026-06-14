"""dogfood.observe_frida — L1 ADVISORY evidence observer (Linux container only).

Runs a command under Frida dynamic instrumentation and records the file paths it
actually opens for write / deletes, emitting an ``observed_effects`` JSON record
the kernel's *observed* gate compares against the proposer's *declared* effects.

THIS IS NOT ENFORCEMENT. Per `prompts/carcerd-defense-sandbox-sprint.md`,
LD_PRELOAD / Frida are advisory, bypassable, evidence-only (a static binary or a
direct `syscall()` evades them). The real boundary is L2 (eBPF/seccomp), owned by
the daemon track. This observer exists to make declared-vs-observed *checkable*,
not to contain anything.

Platform: Linux + glibc only (macOS has no LD_PRELOAD/equivalent here and Frida
attach differs). Run it inside the colima container (see docs/dogfood/
l1-frida-evidence.md), never on the M1 host.

Usage (inside the container):
    python3 tools/dogfood/observe_frida.py --out /tmp/observed.json -- \\
        python3 tools/dogfood/kernel.py propose --scope ... --proposer opencode
Then feed /tmp/observed.json into the judge's observed gate.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Intercept the glibc entry points that create/truncate or unlink files. Frida's
# Interceptor reads the path + flags at call time; the Python side classifies.
_JS = r"""
const WR = 0x1 | 0x2 | 0x40 | 0x200 | 0x400; // O_WRONLY|O_RDWR|O_CREAT|O_TRUNC|O_APPEND
function hook(name, pathArg, flagArg, kind) {
  const f = Module.findExportByName(null, name);
  if (!f) return;
  Interceptor.attach(f, {
    onEnter(args) {
      try {
        const path = args[pathArg].readUtf8String();
        if (kind === 'unlink') { send({ev:'delete', path}); return; }
        const flags = flagArg >= 0 ? args[flagArg].toInt32() : WR;
        if (flags & WR) send({ev:'write', path});
      } catch (e) {}
    }
  });
}
hook('open',   0, 1, 'open');
hook('open64', 0, 1, 'open');
hook('openat', 1, 2, 'open');   // openat(dirfd, path, flags)
hook('creat',  0, -1, 'open');
hook('unlink', 0, -1, 'unlink');
hook('unlinkat', 1, -1, 'unlink');
"""


def observe(cmd: list[str], cwd: str | None = None) -> dict:
    """Spawn ``cmd`` under Frida; return ``{"writes":[...], "deletes":[...]}`` of
    the real, repo-relative paths it opened for write / removed."""
    import frida  # lazy: only present in the Linux container

    root = os.path.abspath(cwd or ".")
    writes: set[str] = set()
    deletes: set[str] = set()

    def _rel(p: str) -> str | None:
        ap = os.path.abspath(os.path.join(root, p))
        if ap.startswith(root + os.sep):
            return os.path.relpath(ap, root)
        return None   # outside the repo — not part of the tree under judgement

    def on_message(msg, _data):
        if msg.get("type") != "send":
            return
        p = msg["payload"]
        rel = _rel(p.get("path", ""))
        if rel is None or rel.startswith(".git") or rel.startswith(".dogfood"):
            return
        (writes if p["ev"] == "write" else deletes).add(rel)

    pid = frida.spawn(cmd, cwd=root)
    session = frida.attach(pid)
    script = session.create_script(_JS)
    script.on("message", on_message)
    script.load()
    frida.resume(pid)
    # wait for the child to exit
    try:
        frida.get_local_device().get_process(pid)
        import time
        while True:
            time.sleep(0.2)
            try:
                frida.get_local_device().get_process(pid)
            except frida.ProcessNotFoundError:
                break
    finally:
        try:
            session.detach()
        except Exception:
            pass
    return {"writes": sorted(writes), "deletes": sorted(deletes)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="observe_frida")
    ap.add_argument("--out", help="write observed_effects JSON here (else stdout)")
    ap.add_argument("--cwd", default=".")
    ap.add_argument("cmd", nargs=argparse.REMAINDER,
                    help="-- command to run under instrumentation")
    args = ap.parse_args(argv)
    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd
    if not cmd:
        ap.error("provide a command after --")
    observed = observe(cmd, args.cwd)
    out = json.dumps(observed, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
