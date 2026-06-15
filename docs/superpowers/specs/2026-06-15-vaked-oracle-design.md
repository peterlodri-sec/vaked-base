# vaked-oracle — design (slice 1)

**Date:** 2026-06-15
**Status:** approved (brainstorm) → ready for implementation plan
**Branch:** `feat/vaked-oracle` (off `origin/main`)
**Substrate:** the `revdev` cell on `dev-cx53` (NixOS, tailnet `100.105.72.88`)

> *The oracle reads what the binary will not say.*

## 1. Context

**vaked-oracle** is the reverse-engineering research subsystem of the Vaked
ecosystem — the side-research line whose north stars are LLM4Decompile, OGhidra,
and reverser_ai: **LLM-assisted reverse engineering** combining static
decompilation, dynamic instrumentation evidence (Frida / eBPF), and a
self-hosted LLM.

It is a sibling to **vaked-aegis** (the proposer/judge verification kernel,
`tools/dogfood/`) and reuses three of its proven assets: the `eventd`/ralph
**hash-chained ledger** pattern, the `tools/ralph` **decision loop**, and the
kernel's **transition record** as an integration seam. It runs on the `revdev`
analyst cell — least-authority by design (no sudo/docker), with untrusted
binaries sandboxed via `sample-run` (bubblewrap).

**Slice-1 target — the LLM runtime itself.** The first cycle reverse-engineers
the self-hosted inference runtime (`llama-cli`, FOSS llama.cpp) on `dev-cx53`.
This is deliberately recursive: a **decompiler-LLM** (llm4decompile-6.7B)
reverse-engineers the runtime of the **inference-LLM** — the "monitored / reversed
LLM" thread, and the deeper half of the "double-dogfood" (one normal LLM, one
monitored/reversed). Because llama.cpp is FOSS (MIT), we have **ground-truth
source** to score decompilation fidelity against — a built-in, objective
acceptance metric that an arbitrary stripped binary would not give us.

## 2. Goal & non-goals

**Slice-1 goal.** Given the `llama-cli` binary and a small set of target
functions, produce — through a budget-bounded **ralph decision loop** — a single
structured **RE finding record** containing, per function: Ghidra pseudo-C, an
llm4decompile-refined C rendering, a **fidelity score vs llama.cpp ground-truth
source**, and dynamic evidence (Frida userspace call traces + eBPF syscall/mmap
profile from a real inference run). The finding bridges to the kernel's evidence
seam (`observed_effects` + a transition cross-reference slot).

**Acceptance.** A full run on `llama-cli` over ~3 target functions (e.g. a
sampler, a `ggml` compute op, the model-mmap/load path) yields a complete finding
with non-null fidelity scores and dynamic evidence; the loop's ledger
replay-verifies (`verify_chain`); the bridge emits a valid `observed_effects`
shape. A CI-able smoke run on a trivial binary covers the plumbing
deterministically.

**Non-goals (later cycles).**
- Arbitrary-binary RE and the kernel double-dogfood as *primary* targets (slice 1
  fixes the target to the LLM runtime; the pipeline is target-agnostic by design).
- A `reverser_ai`-style **autonomous agent** driving the tools (architecture C) —
  rides on top of slice-1's deterministic primitives in a later cycle.
- A real `filesystem`/eBPF **enforcement** boundary (that is L2, another dev's
  lane). Oracle's evidence is advisory, like the kernel's L1.
- The execution **ARP IR** (Pipeline-DSL IR types) — another dev's lane; oracle
  integrates only via the kernel transition record, leaving an ARP-IR seam.

## 3. Decisions (resolved in brainstorm)

| Axis | Decision |
|------|----------|
| Scope | Thin vertical slice (end-to-end, shallow) |
| Decompile input | Ghidra-headless pseudo-C → **llm4decompile-6.7B** (OGhidra style) |
| Dynamic evidence | **Frida** (userspace, unprivileged) **+ eBPF** via a **privileged root watcher** |
| eBPF cap model | Root watcher service; `revdev` stays unprivileged (watcher watches the analyst) |
| Analysis target | The **LLM runtime** (`llama-cli`, FOSS llama.cpp) |
| Architecture | **Standalone `tools/oracle/` + kernel bridge** |
| Orchestration | **ralph decision loop** (reuse `tools/ralph/ralphcore.py`, never modify it) |

**Grounding (verified on dev-cx53, 2026-06-15):** 30 GiB RAM / 24 GiB free, 16
cores → 6.7B GGUF (~5–8 GB) + Ghidra + runtime all fit. `/sys/kernel/btf/vmlinux`
present → eBPF CO-RE works. `llama-cli` is a nix-store FOSS binary. `revdev`
cannot run `bpftrace` directly (`Missing CAP_DAC_READ_SEARCH`) — hence the root
watcher.

## 4. Architecture & components

Standalone subsystem under `tools/oracle/`, mirroring the `tools/dogfood/` layout;
pure-Python stdlib where possible. The privileged eBPF piece is a NixOS module.

```
tools/oracle/
  oracle.py            ralph-loop orchestrator + CLI (`oracle run --target … --funcs …`)
  ghidra_frontend.py   analyzeHeadless → export decompiler pseudo-C for named funcs
  llm_refine.py        pseudo-C → llm4decompile-6.7B (llama-server, temp=0) → refined C
  dynamic_frida.py     hook target funcs on a live llama-cli inference (userspace ptrace)
  watcher_ebpf.py      CLIENT to the root watcher socket (request a PID-scoped trace)
  fidelity.py          score refined-C vs ground-truth llama.cpp source
  finding.py           assemble + persist the finding (own hash-chained log)
  bridge.py            emit observed_effects {writes,deletes} + transition cross-ref
  schema.py            finding record schema (+ optional vaked `oracle_finding` schema kind)
  loop.py              ralph-loop glue over ralphcore (ledger/budget/control); decision policy
  test_oracle.py       stdlib tests (no pytest), incl. negative + graceful-degrade
  Taskfile.yml         dev-cx53 ops (model fetch, ghidra, run, watcher)
  findings/            persisted finding artifacts + ledger (gitignored)

hosts/dev-cx53/oracle-ebpf-watcher.nix   root systemd service + unix-socket request API
docs/oracle/
  README.md            onboarding (mental model, quickstart, lanes)
  v0.md                this slice's architecture, schema, recursion framing
  integration.md       how oracle plugs into the kernel evidence seam
vaked/examples/
  oracle-re-loop.vaked the RE loop as a checked Vaked capability graph (POLA source)
```

Each unit has one job and a typed boundary:
- **ghidra_frontend** — in: binary path + function names; out: `{func: pseudo_c}`.
  Runs as `revdev`. No root.
- **llm_refine** — in: `{func: pseudo_c}`; out: `{func: refined_c}`. Calls
  llm4decompile-6.7B with `temperature=0`; records the model GGUF sha256.
- **dynamic_frida** — in: a runnable inference command + target function names;
  out: `{func: {calls, args_sample, timing}}`. Runs the target via `sample-run`
  (bubblewrap, no-net — llama.cpp inference is local), Frida attaches in userspace
  (ptrace on `revdev`'s own process — no caps needed).
- **watcher_ebpf** (client) + **oracle-ebpf-watcher** (root) — client sends
  `{pid | cmd}`; the root service runs a PID-scoped eBPF/bpftrace program and
  returns `{syscalls, mmaps, files}` (notably the GGUF model mmap + weight reads).
  `revdev` never gains capabilities.
- **fidelity** — in: refined-C + ground-truth source for the function; out:
  `{score, method}`. Slice-1 method: normalized-token similarity (tree-sitter C
  AST diff is a later upgrade).
- **finding** / **bridge** — assemble + persist the record; emit the
  kernel-compatible `observed_effects` and a `transition_xref` slot.
- **loop** — the ralph decision policy (§7).

## 5. Data flow

```
llama-cli ─┬─ ghidra_frontend → pseudo_c → llm_refine → refined_c ─┐
           │                                                       ├→ finding → findings/ (persisted)
 live      ├─ dynamic_frida (sample-run, no-net) → {calls,timing} ─┤   │
 inference └─ watcher_ebpf → [ROOT watcher] → {syscalls,mmaps} ─────┘   ├→ fidelity (vs source)
                                                                       └→ bridge → observed_effects + xref
       (all three evidence producers are best-effort and independently nullable)
```

Orchestrated by the ralph loop (§7): the data flow above is one tick's worth of
work; the loop runs ticks until a stop condition, accumulating into the finding.

## 6. Finding record schema (`schema.py`)

```jsonc
{
  "kind": "oracle_finding", "v": 1,
  "target":     { "path": "...", "sha256": "...", "source_ref": "<llama.cpp commit/version>" },
  "decompiler": { "model": "llm4decompile-6.7b-v2", "model_sha256": "...", "temperature": 0 },
  "functions": [
    { "name": "...", "addr": "0x...",
      "pseudo_c_sha": "...", "refined_c": "...",
      "fidelity": { "score": 0.0, "method": "normalized-token-similarity" },
      "dynamic":  { "frida": { "calls": 0, "args_sample": [], "timing_ms": 0.0 } | null,
                    "ebpf":  { "syscalls": {}, "mmaps": [], "files": [] } | null } }
  ],
  "observed_effects": { "writes": [], "deletes": [] },   // kernel-bridge compatibility
  "transition_xref": null,                                // double-dogfood link (null in slice 1)
  "confidence": 0.0,
  "chain": { "prev_hash": "...", "this_hash": "..." }     // own append-only log (eventd/ralph pattern)
}
```

The optional Vaked `oracle_finding` schema kind (declared like `arp_event` — a
**schema**, not a new grammar kind, per the language lane) lets a finding be a
checked Vaked declaration. Deferred in slice 1; noted as a seam.

## 7. Orchestration — ralph decision loop

`oracle.py`/`loop.py` run as a ralph-style loop, **reusing**
`tools/ralph/ralphcore.py` (import only — never modify the shipping loop, exactly
as `tools/dogfood/` does):

- **Ledger** — `chain_hash` / `make_entry` / `verify_chain` /
  `longest_valid_prefix`: an immutable, replay-verifiable decision trail.
- **Budget** — `budget_total` / `cost_usd`: bounds the run. Local `llama-server`
  is $0, so the budget unit is **iterations + recorded token usage**, not dollars.
- **Control** — a live control file read each tick: pause / step / stop.

```
tick:
  read control (pause / step / stop)
  choose next action by policy:
    { decompile next fn | refine a low-fidelity fn | observe (frida/ebpf) | finalize }
  run it
  append a hash-chained ledger entry (action, fn, fidelity, cost)
  stop when:  budget spent  OR  all fns ≥ confidence threshold  OR  control stop
```

**Decision policy (slice 1, deterministic).** Round-robin the target functions;
for each, decompile then observe; if `fidelity < threshold`, schedule one refine
pass (re-prompt with the dynamic evidence as a hint); finalize when every function
is at/above threshold or the iteration budget is exhausted. The **ledger** is the
session's decision trail (replay-verifies); the **finding** is the accumulated
artifact — the two share the `eventd`/ralph hash-chain so the whole RE session is
tamper-evident and replayable.

**`vaked/examples/oracle-re-loop.vaked`** declares the loop as a checked Vaked
capability graph (mirroring `ralph-dogfood-loop.vaked`). Oracle's POLA — `revdev`
write-scope, watcher-socket access, model access — is **lowered from it** via
`scope_from_vaked.py`, so the RE loop is itself a Vaked declaration: full dogfood
symmetry with the aegis kernel.

## 8. eBPF watcher (the privileged piece)

`hosts/dev-cx53/oracle-ebpf-watcher.nix` defines a **root** systemd service that
exposes a narrow **unix-socket** request API. The unprivileged `revdev` client
(`watcher_ebpf.py`) sends `{pid | cmd}`; the service runs a **PID-scoped**
eBPF/bpftrace program — syscall histogram, `mmap` regions (the GGUF model map),
and file reads — and returns the events as JSON. The socket API is the entire
attenuation surface: `revdev` gets evidence, never `CAP_BPF`/`CAP_PERFMON`. This
is the concrete "the watcher watches the analyst" arrangement and the only path by
which the least-authority cell obtains kernel-level evidence.

## 9. Error handling — degrade, never crash

Every evidence producer is best-effort and independently nullable; a finding is
valid with any subset of evidence present.

| Failure | Behaviour |
|---------|-----------|
| Ghidra headless timeout/error | record exported funcs; mark the rest failed; continue |
| llm4decompile unavailable | `refined_c = null` (keep pseudo-C); flag; continue |
| Frida attach fails (run too short) | `dynamic.frida = null`; continue |
| Watcher unreachable / denied | `dynamic.ebpf = null`; continue |
| Ground-truth source unavailable | `fidelity.score = null` |
| Ledger tamper detected | replay to `longest_valid_prefix`; refuse to extend a broken chain |

## 10. Testing & acceptance

`tools/oracle/test_oracle.py` (stdlib, no pytest):
- finding schema round-trip + `chain` verify;
- fidelity scorer on a known pair (identical source → high; unrelated → low);
- bridge emits a valid `observed_effects` shape;
- graceful-degrade: missing frida / ebpf / source still assembles a finding;
- **CI smoke**: full pipeline on a trivial 3-line C binary compiled on dev-cx53
  (deterministic plumbing check — not the heavy `llama-cli` run).

**Manual acceptance demo:** a full ralph-loop run on `llama-cli` over ~3 target
functions, on dev-cx53, producing a finding with non-null fidelity + dynamic
evidence, and a replay-verifiable ledger.

## 11. Boundaries & safety

- `revdev` stays unprivileged; eBPF only via the root watcher's narrow socket.
- llama.cpp is MIT — reverse-engineering it is fully legitimate and yields the
  ground-truth needed for fidelity scoring.
- The M3 orchestrates; all heavy work (Ghidra, LLM, Frida, eBPF) runs on dev-cx53.
- Untrusted runs go through `sample-run` (bubblewrap, no-net).
- **Lanes:** do not modify `tools/ralph/` (import `ralphcore` only); do not touch
  the execution **ARP IR** or L2 eBPF-LSM (other dev's lanes); integrate only via
  the kernel transition record + an own finding artifact.
- No secrets. If the litellm gateway is used instead of a local `llama-server`,
  `LITELLM_KEY` is read from the environment, never stored.

## 12. Open items (resolve in the implementation plan)

- **Model + serving:** exact 6.7B variant (`llm4decompile-6.7b-v2` vs `-ref`) and
  GGUF source; serving via a new `llama-server` user service for `revdev` vs the
  existing litellm gateway (`:4000`).
- **Ghidra:** `analyzeHeadless` invocation + which decompiler export format; how to
  resolve function names/addresses on the nix-store `llama-cli`.
- **Fidelity:** confirm slice-1 normalized-token similarity; map the GGUF/runtime
  build to the exact llama.cpp source commit for ground truth.
- **Watcher protocol:** the unix-socket request/response schema and the PID-scoped
  eBPF/bpftrace program.

## 13. Roadmap (later cycles)

1. **Arbitrary-binary RE** — the same pipeline on unknown/stripped ELFs (the pure
   llm4decompile/OGhidra demo).
2. **Double-dogfood** — oracle reverse-engineers a kernel proposer transition;
   populate `transition_xref`.
3. **reverser_ai agent loop** — an installed agent (pi/claude/nullclaw) drives the
   deterministic primitives autonomously.
4. **eBPF depth + L2 seam** — richer behavioral models; hand off to the enforcement
   lane.
5. **tree-sitter fidelity** — AST-level decompilation scoring.
