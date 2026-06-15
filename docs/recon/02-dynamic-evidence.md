# 02 — Frida dynamic-evidence producer

**Date:** 2026-06-15
**Status:** validated on dev-cx53 (frida 17.5.1)

---

## Recipe

The dynamic-evidence producer hooks named exported functions in a live process using
**frida-python** (not the `frida` CLI). The driver lives at `tools/oracle/frida_driver.py`.

```bash
# Install frida-python in the oracle venv (dev-cx53 only)
~/oracle/pgvenv/bin/pip install frida

# Invoke directly (for manual testing):
FRIDA_MAX_WAIT=90 ~/oracle/pgvenv/bin/python \
  tools/oracle/frida_driver.py \
  llama_decode,llama_model_load_from_file \
  llama-completion -m /path/to/model.gguf -p "hello" -n 8
```

Or via oracle.py:

```bash
oracle run ... --frida-python ~/oracle/pgvenv/bin/python \
               --infer-cmd "llama-completion -m model.gguf -p hello -n 8"
```

The env var `ORACLE_FRIDA_PYTHON` can substitute for `--frida-python` to avoid
repeating the venv path.

---

## Key findings from dev-cx53 validation

### 1. `Module.findExportByName(null, …)` removed in frida 17

Frida 17 removed the two-argument form `Module.findExportByName(null, name)` that
searched across all loaded modules. The correct frida-17 API is:

```javascript
Module.findGlobalExportByName('llama_decode')
```

`frida_driver.py` uses `findGlobalExportByName` exclusively; `hook.js` used the
removed form and is deleted.

### 2. `Process.env` does not exist in frida JS

`hook.js` read function names from `Process.env.ORACLE_HOOK_FUNCS`. `Process.env` is
not part of the frida JavaScript runtime. The driver inlines the function list
directly into the generated JavaScript, avoiding any env-var injection into the
script.

### 3. `stdio="pipe"` keeps event JSON clean

When frida spawns a process with `stdio` unset, child stdout/stderr can intermix with
frida `send()` output. Setting `stdio="pipe"` on `dev.spawn()` and discarding child
output via `dev.on("output", lambda …: None)` ensures only event JSON reaches the
driver's stdout, which is consumed by `parse_frida_trace()`.

### 4. `llama-completion`, not `llama-cli`

`llama-cli` is now interactive by default (the `-no-cnv` flag was removed in recent
llama.cpp). Using it as a target without a controlling TTY hangs. The correct
non-interactive inference binary is `llama-completion` (available in the same nix
derivation on dev-cx53).

### 5. Detach-wait, not fixed sleep

The driver calls `done.wait(max_wait)` on a `threading.Event` set by the
`session.on("detached", …)` callback. This exits as soon as the process exits rather
than sleeping for a fixed duration, so short inferences don't waste wall time.

### 6. `ptrace_scope=1` is compatible

`dev-cx53` has `ptrace_scope=1` (restricted). Frida's `-f` / `dev.spawn()` uses a
different ptrace flow (parent-child) that is allowed under scope 1, so no kernel
override is needed.

### 7. Validated capture

On a real `llama-completion` inference:

| Function | Calls | Approx duration |
|---|---|---|
| `llama_model_load_from_file` | 1 | 1.45 s |
| `llama_decode` | 9 | varies (~30 ms/call) |

`parse_frida_trace` aggregated both correctly from the driver's stdout.

---

## Second producer: eBPF watcher

The root eBPF watcher is the second dynamic-evidence producer. It runs as a systemd
service (`oracle-ebpf-watcher.nix`), listens on `/run/oracle-watcher.sock`, and
accepts requests from the unprivileged `watcher_client.py`:

```bash
# Manual test (watcher must be running):
python3 tools/oracle/watcher_client.py --pid <pid> --duration 5
```

The `--pid` CLI was added alongside the frida_driver migration.

## validated in a finding (2026-06-15, run3 `caa53b79…`)
`oracle.py run --funcs llama_decode --infer-cmd "llama-completion -m <gguf> -p hi -n 4"`
— both producers landed in one finding (chain_ok=True):
```
frida: {calls: 1, timing_ms: 788.0}                       # llama_decode hooked live
ebpf : syscalls{futex:885, write:15, openat:8, read:5, close:4}, files:8
```
Notes: watcher socket was ad-hoc `chmod 666` (production = `oracle-watcher` group via the nix module).
`futex`-heavy = inference threading. `mmaps:[]` — the GGUF mmap happens during the *load* phase;
the 5s PID-scoped trace + `sys_enter_*` attach latency can miss it (widen `duration_s` / trace the
load window to catch the weight mmap). One `llama-completion` run threw `std::runtime_error: this
custom template is not supported, try using --jinja` — add `--jinja` for chat-template models;
oracle degraded gracefully and still recorded both blobs.

---

## Double-dogfood grounding (slice 2)

A finding produced here can be **grounded** into the vaked-aegis kernel: `oracle
ground` records it as an eventd-WAL transition, `oracle verify-xref` proves the
bidirectional `transition_xref` link + both hash chains. On-box acceptance
(2026-06-15, dev-cx53/revdev, python 3.13) on the static finding `81ff9c4f…`:
`transition_xref=c15ef2f2…cfda` (WAL seq 0), `actual_effects.writes ==
observed_effects.writes == ["findings/f.json"]`, `capability_ok=True`,
`verify-xref OK`. See `docs/oracle/v0.md` + `docs/oracle/integration.md` §2.
