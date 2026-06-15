// Frida hook: attach to the functions named in ORACLE_HOOK_FUNCS (comma list),
// emit one JSON line per call with wall-clock duration. Resolve by export symbol;
// functions not exported are skipped (slice 1 hooks exported symbols only).
// NOTE (integration open-item): how the function list reaches the script (env var
// vs frida script parameters) must be confirmed against the installed frida version
// on dev-cx53; parse_frida_trace consumes stdout JSON lines regardless.
const wanted = (Process.env && Process.env.ORACLE_HOOK_FUNCS
                ? Process.env.ORACLE_HOOK_FUNCS : "").split(",").filter(Boolean);

wanted.forEach(function (fn) {
  const addr = Module.findExportByName(null, fn);
  if (!addr) { return; }
  Interceptor.attach(addr, {
    onEnter() { this._start = Date.now(); },
    onLeave() {
      const durNs = (Date.now() - this._start) * 1e6;
      send(JSON.stringify({ fn: fn, dur_ns: durNs }));
    },
  });
});
