#!/usr/bin/env python3
"""Frida dynamic-evidence driver (frida-python, frida 17 API).

Spawns a target, hooks the named exported functions, emits one {"fn","dur_ns"} JSON
line per call to stdout (consumed by dynamic_frida.parse_frida_trace). Child stdout is
piped away so only event JSON reaches stdout. Run via a python with frida-python
installed. Validated on dev-cx53 (frida 17.5.1).

Usage: frida_driver.py <comma,funcs> <target> [args...]   env: FRIDA_MAX_WAIT (seconds)
"""
import json
import os
import sys
import threading

import frida


def main():
    funcs = [f for f in sys.argv[1].split(",") if f]
    target = sys.argv[2:]
    max_wait = float(os.environ.get("FRIDA_MAX_WAIT", "90"))
    dev = frida.get_local_device()
    pid = dev.spawn(target, stdio="pipe")
    dev.on("output", lambda p, fd, data: None)   # discard child stdout/stderr
    ses = dev.attach(pid)
    done = threading.Event()
    ses.on("detached", lambda *a: done.set())
    js = "\n".join(
        "(function(){var a=Module.findGlobalExportByName('%s');"
        "if(a)Interceptor.attach(a,{onEnter:function(){this.t=Date.now();},"
        "onLeave:function(){send({fn:'%s',dur_ns:(Date.now()-this.t)*1e6});}});})();" % (f, f)
        for f in funcs)
    scr = ses.create_script(js)
    out = []
    scr.on("message", lambda m, d: out.append(m["payload"]) if m.get("type") == "send"
           else sys.stderr.write((str(m)[:200]) + "\n"))
    scr.load()
    dev.resume(pid)
    done.wait(max_wait)
    try:
        dev.kill(pid)
    except Exception:
        pass
    for e in out:
        if e:
            print(json.dumps(e))


if __name__ == "__main__":
    main()
