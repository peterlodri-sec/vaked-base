# vaked-oracle — onboarding

> *The oracle reads what the binary will not say.*

**vaked-oracle** is the reverse-engineering research subsystem of the Vaked
ecosystem. It applies LLM-assisted static decompilation (Ghidra +
llm4decompile-6.7B), dynamic instrumentation evidence (Frida userspace +
eBPF kernel watcher), and a fidelity score against open-source ground truth
— all woven through a budget-bounded, hash-chained ralph decision loop and
bridged to the vaked-aegis evidence seam.

> Vaked declares · Nix materializes · OTP supervises · Zig enforces · eBPF testifies · Aegis adjudicates · **Oracle reveals**.

This doc is everything you need to jump in: the mental model, the component
map, the quickstart, and the lane boundaries.

Spec: `docs/superpowers/specs/2026-06-15-vaked-oracle-design.md`.

---

## 1. Mental model (read this first)

**A decompiler-LLM reverse-engineers an inference-LLM.** The slice-1 target
is `llama-cli` — the FOSS llama.cpp inference runtime running on `dev-cx53`.
The decompiler is llm4decompile-6.7B, itself an LLM, served locally via
llama-server. The recursion is deliberate: the same machine that runs the
inference model is also the machine that reverse-engineers it.

```
llama-cli (nix-store, FOSS, MIT)
     │
     ├── Ghidra PyGhidra (CPython 3) ──→ pseudo-C per function
     │                                      │
     │                              llm4decompile-6.7B
     │                              (llama-server :8080)
     │                                      │
     ├── Frida (userspace, ptrace) ──→ call trace + timing
     │
     └── root eBPF watcher ──→ syscall histogram + GGUF mmap evidence
                                      │
                              fidelity score (vs llama.cpp source)
                                      │
                              finding record (hash-chained ledger)
                                      │
                              bridge → observed_effects → kernel seam
```

**FOSS ground truth is the key.** Because llama.cpp is MIT-licensed, every
decompiled function has a known-correct original — the exact commit that
produced the binary. Fidelity scoring (`fidelity.py`, Dice over token
multisets) produces an objective number; no human judgment is needed to
decide whether a refined-C rendering is plausible.

**The full loop.** `loop.py` runs a ralph-style decision loop over a set of
target functions. Each tick chooses an action (decompile, refine, observe,
finalize) by policy, runs it, appends a hash-chained ledger entry, and
stops when every function is above the confidence threshold or the iteration
budget is exhausted. The ledger is tamper-evident and replay-verifies via
`ralphcore.verify_chain`.

---

## 2. Component map (`tools/oracle/`)

| Module | One job |
|--------|---------|
| `oracle.py` | CLI entry point (`oracle run --target … --funcs …`), `persist_finding`, the `cmd_run` wiring that connects all producers |
| `loop.py` | Ralph-style decision loop — control file check → policy → run producer → ledger append; testable with fake callables |
| `policy.py` | Stateless policy: given `LoopState` (functions, results, iters, budget), returns the next action dict (`decompile`/`refine`/`observe`/`finalize`) |
| `ledger.py` | Thin wrapper over `ralphcore.py` — JSONL of hash-chained entries, one per decision; `verify()` and `valid_prefix()` |
| `schema.py` | Finding record constructors (`function_entry`, `build_finding`) and `validate_finding`; defines `FINDING_KIND`, `FINDING_V`, `FIDELITY_METHOD` |
| `fidelity.py` | `score(a, b)` — Dice coefficient over C token multisets (slice-1 method); comments stripped, whitespace collapsed |
| `ghidra_frontend.py` | `run_ghidra(binary, functions, pyghidra_python, ...)` — decompiles via PyGhidra (CPython 3), threads GHIDRA_INSTALL_DIR/JAVA_HOME/LD_LIBRARY_PATH env, returns `{func: pseudo_c}`; `parse_decomp` is pure and tested |
| `pyghidra_decompile.py` | PyGhidra headless decompiler script — invoked by `run_ghidra` via the `~/oracle/pgvenv` venv; requires `pyghidra` + `jpype1`; writes `{func: pseudo_c}` JSON to disk; validated on ghidra 12.0.4 / openjdk-21 / pyghidra 3.0.2 |
| `llm_refine.py` | `refine(fn, pseudo_c, server)` — builds the llm4decompile prompt (`PROMPT_PREFIX` + code + `PROMPT_SUFFIX`), POSTs to llama-server `/completion`, returns refined C; `build_prompt` and `parse_completion` are pure and tested |
| `dynamic_frida.py` | `run_frida(target_cmd, functions, frida_python)` — spawns the target via `frida_driver.py` using a frida-python-capable interpreter; aggregates `{fn: {calls, timing_ms}}`; `parse_frida_trace` is pure and tested |
| `frida_driver.py` | Frida-python driver — spawns target with `stdio="pipe"`, hooks named exports via `Module.findGlobalExportByName` (frida 17 API), waits for process detach, emits one JSON line per call; validated on dev-cx53 (frida 17.5.1) |
| `watcher_client.py` | Unprivileged client to the root watcher socket — `query_watcher(sock_path, pid, duration_s)` sends a JSON request, receives `{syscalls, mmaps, files}`; `encode_request` and `decode_response` are pure and tested |
| `watcher_daemon.py` | Root daemon served by `oracle-ebpf-watcher.nix` — accepts requests on the unix socket, runs a PID-scoped bpftrace program, parses and returns results; `parse_bpftrace` and `handle_request` are pure and tested |
| `bridge.py` | `to_observed_effects(finding, files_written, files_deleted)` — emits the `{writes, deletes}` shape the aegis kernel consumes; `attach_transition(finding, hash)` — links a finding to a kernel transition hash (wired in slice 2 via `dogfood_bridge.py`) |
| `dogfood_bridge.py` | Double-dogfood wire — `ground_finding(...)` records a finding as a real aegis kernel transition (reuses `tools/dogfood/kernel.judge`) and cross-links both hash chains; `verify_xref(...)` proves the bidirectional `transition_xref` link + that both chains verify independently. CLI: `oracle ground` / `oracle verify-xref` |
| `agent.py` | Slice-3 LLM-driven loop brain — `make_policy(llm_call)` picks the next action (decompile/refine/investigate/finalize) over the bounded set; `build_prompt`/`parse_action`; `LiteLLMClient` (local litellm `:4000`, temp=0); deterministic `policy.next_action` fallback on any parse failure |
| `investigate.py` | Slice-3 read-only structural lookup — `make_investigator(source_root, binary)` answers function queries from crabcc (C ground-truth source) with a binutils fallback; never raises |
| `oracle-ebpf-watcher.nix` | NixOS systemd service (root) for the eBPF watcher — `bpftrace` in the service path, unix socket at `/run/oracle-watcher.sock` with group `oracle-watcher` (`srw-rw----`), Python 3 interpreter, on-failure restart |

---

## 3. Quickstart

```bash
# Step 1: run the unit suite (pure stdlib, M3 is fine, no dev-cx53 needed)
python3 tools/oracle/test_oracle.py
# → 33 passed, 0 failed

# Step 2: heavy runs go on dev-cx53 via the Taskfile
# (install go-task if not present: nix shell nixpkgs#go-task)

# run unit tests (same command, but from repo root via task)
task -t tools/oracle/Taskfile.yml test

# fetch the llm4decompile GGUF into ~/oracle/models (on dev-cx53)
ssh dev-cx53
task -t tools/oracle/Taskfile.yml model:fetch

# create the pyghidra venv (once; idempotent — safe to re-run)
task -t tools/oracle/Taskfile.yml pyghidra:setup

# start llama-server on :8080 (dev-cx53)
task -t tools/oracle/Taskfile.yml llm:serve &

# run the full RE loop on the default target
# (GHIDRA_INSTALL_DIR / JAVA_HOME / ORACLE_LIBSTDCXX_DIR derived from nix store automatically)
LLAMA_CPP_SRC=~/src/llama.cpp \
LLAMA_DEMO_MODEL=~/oracle/models/llm4decompile-6.7b-v2.gguf \
  task -t tools/oracle/Taskfile.yml run
```

The finding lands in `~/oracle/findings/<sha256>.json`. Verify the ledger:

```python
import sys, os; sys.path.insert(0, "tools/oracle")
import ledger, os
lg = ledger.Ledger(os.path.expanduser("~/oracle/events.jsonl"))
print(lg.verify())   # True
```

---

## 4. Lane boundaries

```
revdev (unprivileged)          root / kernel                other dev's lane
─────────────────────────────  ─────────────────────────    ─────────────────
oracle.py / loop.py / all      oracle-ebpf-watcher.nix      ARP IR (DSL)
python modules in tools/oracle  (watcher_daemon.py)          L2 eBPF-LSM
Frida (ptrace on own process)   bpftrace programs            agent dispatch
watcher_client.py               /run/oracle-watcher.sock     ralph shipping loop
                                                             tools/ralph/ source
```

Concrete rules:
- **revdev stays unprivileged.** eBPF evidence flows through the watcher
  socket only — `revdev` never acquires `CAP_BPF` or `CAP_PERFMON`.
- **Reuse `tools/ralph/` — never modify it.** Import `ralphcore.py` for
  chain primitives; the loop/ledger here are oracle-local.
- **Do not touch the execution ARP IR** or the L2 eBPF-LSM — those are
  another dev's lane. Oracle integrates via the kernel transition record
  (`bridge.py`) and its own finding artifact; the ARP-IR seam is a stub slot.
- **Heavy work on dev-cx53, never the M3.** Ghidra analysis, LLM inference,
  Frida instrumentation, and bpftrace runs all require Linux and significant
  RAM (the 6.7B GGUF alone is 5–8 GB). The M3 runs the unit suite and
  orchestrates via SSH/task; it does not run the heavy producers.
- **Sandbox untrusted targets.** Trusted targets (llama.cpp, FOSS) run directly under
  the frida-python driver. For untrusted samples, wrap the target command inside
  `sample-run` (bubblewrap, no-net) before passing it to `run_frida`; the driver
  itself does not sandbox.
