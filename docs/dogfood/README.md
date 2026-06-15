# vaked-aegis — onboarding

> *The aegis is the templar's shield. Nothing crosses it unverified.*

**vaked-aegis** is the local **proposer/judge verification kernel** for the Vaked
dogfood loop: an AI agent *proposes* a code transition; the kernel *judges* it
against four gates, records the accepted ones to an append-only hash-chained
ledger, and replay-verifies them — all **locally, at zero cloud cost**, on a
macOS M1, with a real-Linux evidence layer on `dev-cx53`.

> Vaked declares · Nix materializes · OTP supervises · Zig enforces · eBPF testifies · **Aegis adjudicates**.

This doc is everything you need to jump in: the mental model, the tools, the repo
map, the quickstart, the lane boundaries, and the gotchas.

---

## 1. Mental model (read this first)

**Creativity proposes; determinism decides.** An LLM agent is creative but
untrusted. vaked-aegis lets it propose freely, then admits a change only if it
survives four gates. The agent never has authority it wasn't granted, and every
accepted change is replayable and tamper-evident.

```
  opencode (local LLM)        vaked-aegis (the judge)            L1 observer (Linux)
    = PROPOSER          →       = the aegis / four gates    →      = ADVISORY EVIDENCE
  proposes a transition       capability → declared≈actual        LD_PRELOAD/Frida sees
  (edits + declared            → replay-stable → observed          real file syscalls,
   effects), scoped            accept ⇒ append eventd WAL          feeds the observed gate
                               reject ⇒ roll the tree back
```

**The four gates** (a transition is accepted only if ALL pass; else the tree is
rolled back and nothing is recorded):

| Gate | Question | Catches |
|------|----------|---------|
| **Capability (POLA)** | every changed path inside the granted scope? | scope-escape / confused deputy — the open `E-CAP-USE` use-check, locally |
| **Declared vs actual** | did the agent change exactly what it claimed? | a lying / sloppy proposal |
| **Replay-stability** | does `base + recorded post-images` reproduce the recorded `state_hash_after`? | incomplete capture, blob corruption, post-record drift |
| **Observed** (L1) | are real (LD_PRELOAD/Frida-observed) writes ⊆ declared? | undeclared side effects |

**The three theories vaked-aegis dogfoods** (Vaked's core bets, tested on
ourselves before they land in the language):
- **immutable** — the WAL is the canonical `eventd` append-only hash chain;
- **control** — accept / reject / rollback; budget-bounded; pausable;
- **capability** — POLA path-scope, *lowered from a Vaked declaration*.

**Advisory vs boundary.** The L1 layer (LD_PRELOAD/Frida) is *evidence, not
enforcement* — it's bypassable (static binary, direct `syscall()`). The real
boundary is **L2** (eBPF/seccomp), which is **another dev's lane** (do not build
it here). vaked-aegis proves the *principles* at the layer that runs without a
kernel.

---

## 2. Architecture & data flow

A transition is captured as a deterministic function of `(base tree, post-image
set)` — the "patch" is the exact post-image bytes of changed in-scope files,
content-addressed as blobs. No textual diff/patch tooling (avoids fuzz/whitespace
nondeterminism). Pipeline (`tools/dogfood/kernel.py::judge`):

```
snapshot base → proposer mutates tree → detect actual delta (git status delta) →
CAPABILITY (delta ⊆ scope) → DECLARED==ACTUAL → [OBSERVED ⊆ DECLARED] →
capture post-images → REPLAY (base+post-images ⇒ state_hash_after) →
accept ⇒ append to eventd WAL ;  reject ⇒ roll tree back, record nothing
```

The **WAL is the real `eventd` daemon** (`eventd/` — Python reference oracle:
hash chain, single-writer, boot-time tamper check), not a third hash chain.

**POLA is lowered from Vaked.** Instead of hand-passing the scope, vaked-aegis
reads it from a Vaked capability declaration:

```
dogfood-kernel.vaked --(vakedc|vakedz parse)--> .vaked/graph.json
                                                      │
                            scope_from_vaked.py (reads the LPG)
                                                      │
              kernel.py propose --from-vaked … --principal proposer
```

`scope_from_vaked.py` returns a principal's `writeScope` only if its `fs` grant is
write-capable (`repo_rw`/`host_rw`); a read-only principal (`fs.repo_ro`) gets
nothing. It reads the *parsed LPG artifact*, so it's **engine-agnostic** — works
with `vakedc` (Python) or `vakedz` (Zig), surviving the planned cutover.

---

## 3. Repo map

```
tools/dogfood/                  the kernel (pure Python stdlib)
  kernel.py        the judge: gate → record → replay-verify; CLI (propose/verify/log)
  capability.py    POLA path-scope gate
  transition.py    content-addressed tree hashing + post-image blob store
  wal.py           thin wrapper over the real eventd EventLog
  proposer.py      stub_propose (tests/demo) + opencode_propose (local LLM)
  scope_from_vaked.py  lower the write-scope FROM a Vaked POLA graph
  observe_preload.c    L1 LD_PRELOAD advisory observer (Linux; built on dev-cx53)
  observe_preload.py   run a cmd under the .so → observed_effects
  observe_frida.py     Frida alternative to LD_PRELOAD
  Dockerfile.l1        colima container for L1 (alternative to dev-cx53)
  Taskfile.yml         dev-cx53 ops (go-task): stack, ollama, l1:build/test/observe
  test_kernel.py       16 stdlib tests (no pytest)
  sandbox/             demo target dir
.dogfood/                       runtime state (gitignored): wal/ + blobs/

vaked/examples/
  dogfood-kernel.vaked      vaked-aegis's OWN capability graph (POLA source of truth)
  ralph-dogfood-loop.vaked  the ralph loop as a checked capability graph

tools/ralph/                    the shipping decision loop (do NOT modify here)
  tracks.local.json   local override: all tracks → a local model (qwen3:8b)

docs/dogfood/
  README.md             ← you are here (vaked-aegis onboarding)
  kernel-v0.md          design + hot-path complexity table
  local-ollama-setup.md ralph on a local model, ≤8GB
  l1-frida-evidence.md  the L1 layer + dev-cx53 LD_PRELOAD path
```

---

## 4. Environment & tools

| Tool | Where | Why |
|------|-------|-----|
| Python 3.12+ stdlib | M1 + dev-cx53 | the kernel, ralph, eventd — no pip needed |
| **Ollama** | M1 (≤8GB) or dev-cx53 | the local model backend (OpenAI-compatible) |
| **opencode** | M1 | the proposer agent (drives a local model) |
| **vakedc** | M1 | `python3 -m vakedc parse\|check\|lower` — the Vaked front-end |
| **go-task** | M1 | runs `tools/dogfood/Taskfile.yml` |
| **clang** | dev-cx53 only | builds the LD_PRELOAD `.so` (Linux) |
| **tailscale** | both | reaches dev-cx53 (`100.105.72.88`) |

**Two machines, one rule each:**

- **macOS M1 (dev workstation)** — runs the kernel, ralph, opencode, vakedc. Keep
  Ollama **≤8GB**: serve with `OLLAMA_CONTEXT_LENGTH=8192 OLLAMA_MAX_LOADED_MODELS=1
  OLLAMA_KEEP_ALIVE=60s OLLAMA_FLASH_ATTENTION=1` (16k ctx nearly froze the host).
  **Cannot** do LD_PRELOAD/seccomp/eBPF (macOS).
- **dev-cx53 (NixOS, `dev@100.105.72.88`)** — the sanctioned Linux build/run
  target (16 cpu, 30GB, sudo-nopasswd). Real LD_PRELOAD/clang. Already self-hosts
  a `crabcc-ollama-stack` (ollama + **litellm** OpenAI-compat gateway on `:4000`,
  auth-gated). **Never build/compile on the M1** (project rule) — gate compiles to
  dev-cx53.

---

## 5. Quickstart

### 5a. Get on the real trunk (the local checkout is a stale scaffold!)
```bash
git fetch origin
git worktree add .worktrees/aegis -b your-branch origin/main
cd .worktrees/aegis
python3 tools/dogfood/test_kernel.py   # 16 passed
python3 tools/ralph/test_ralph.py      # 111 passed
```

### 5b. ralph on a local model (zero cloud cost)
```bash
OLLAMA_CONTEXT_LENGTH=8192 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_FLASH_ATTENTION=1 ollama serve &
export RALPH_BASE_URL=http://localhost:11434/v1/chat/completions RALPH_API_KEY=ollama RALPH_CRITIQUE=off
python3 tools/ralph/ralph.py decide --tracks tools/ralph/tracks.local.json --track mlir-topology --dry-run
python3 tools/ralph/ralph.py decide --tracks tools/ralph/tracks.local.json --track mlir-topology
python3 tools/ralph/ralph.py events --replay
```
> ralph stage-1 sends `reasoning=`, which Ollama **400s** on non-thinking models —
> use `qwen3:8b` (thinking-capable), not `qwen2.5-coder`.

### 5c. The kernel, scope lowered from Vaked
```bash
python3 -m vakedc check vaked/examples/dogfood-kernel.vaked
python3 -m vakedc parse vaked/examples/dogfood-kernel.vaked      # → .vaked/graph.json
python3 tools/dogfood/kernel.py propose --from-vaked .vaked/graph.json --principal proposer \
  --intent "demo" --proposer stub --edit tools/dogfood/sandbox/demo.txt=/path/to/new.txt
python3 tools/dogfood/kernel.py verify    # boot tamper-check + replay summary
```

### 5d. L1 evidence + self-hosted LLM on dev-cx53
```bash
cd tools/dogfood
task preflight        # probe dev-cx53
task stack:status     # the existing ollama+litellm stack
task l1:build         # ship observe_preload.c → clang on dev-cx53
task l1:test          # expect W,W,D; read-only open NOT logged
task point            # prints env to aim ralph/opencode at dev-cx53 (frees M1 RAM)
```
> litellm is auth-gated: `export LITELLM_KEY=…` (see `OLLAMA-AUTH.md` in the stack)
> before `task stack:models` / using `task point`.

---

## 6. Lane boundaries (do NOT touch)

A second dev owns the runtime track. Stay out of:
- **ARP IR / DSL parser** (`ail_parse`/`ail_emit`/AIL-0 grammar) — vaked-aegis uses
  **plain JSON** transition records, with a seam to adopt the ARP IR later.
- A2A dispatch / wavefront scheduler · ZetaTensor wire / io_uring Zig logger ·
  the L1 hook *enforcement impl* + secret vault · **L2 eBPF-LSM** (the real boundary).
- `eventd`'s format — reuse read/append only; do not change it.
- `tools/ralph/` shipping code — add overrides (`tracks.local.json`), don't edit the loop.

---

## 7. Hot-path complexity (per transition)

| Step | Cost |
|------|------|
| change detection (git) | `O(N_tracked stats + N_changed·bytes)` — `git status` delta, only changed files hashed |
| post-images + state hash + replay | `O(N_scope·bytes)` — bounded by the small granted scope |
| capability check | `O(N_changed · N_prefixes)` |
| WAL append (eventd) | `O(n)` boot-verify per open (the tamper guarantee); a long-running supervisor holds the log open for `O(1)` appends |

Earlier drafts content-hashed the whole git universe twice per transition
(`O(N_repo·bytes)`) — removed. See `kernel-v0.md` for the full table.

---

## 8. Gotchas (learned the hard way)

- **Local `main` is a stale divergent scaffold** — NOT an ancestor of `origin/main`.
  Always branch from `origin/main`.
- **ralph needs a *thinking* model** locally (`qwen3:8b`); `qwen2.5-coder` 400s on
  the `reasoning=` field.
- **Keep Ollama ≤8GB on the M1** — 16k context nearly froze the host. Or offload to
  dev-cx53 (`task point`).
- **Don't `pkill -f "ollama serve"` on dev-cx53** — it matches the stack container's
  process (shared host). Use `task`/docker compose instead.
- **dev-cx53 already self-hosts the LLM** (crabcc-ollama-stack) — don't spin a
  duplicate; reuse via litellm `:4000` (needs `LITELLM_KEY`).
- **macOS can't LD_PRELOAD** — the L1 observer builds/runs on dev-cx53 (or colima).
- **`writeScope` is carried, not yet checked** — `filesystem` is a schema-less kind;
  the path allow-set rides as an open `meshNode` field until a real `filesystem`
  membrane schema lands (open follow-up).

---

## 9. Glossary

- **POLA** — Principle of Least Authority. Here: a transition may only write paths
  under its granted scope. `E-CAP-USE` = the `used(p) ⊑ granted(p)` use-check
  (unimplemented on trunk; vaked-aegis does it at the path layer).
- **transition** — one proposed change: intent + scope + post-images + declared/
  actual/observed effects + state hashes. One WAL entry.
- **WAL** — the `eventd` append-only hash-chained ledger (state-of-record).
- **LPG** — Labeled Property Graph: Vaked's parsed semantic graph (`.vaked/graph.json`).
- **L1 / L2** — L1 = advisory userspace evidence (LD_PRELOAD/Frida/seccomp-unotify);
  L2 = the real kernel boundary (eBPF/seccomp). vaked-aegis is L1-adjacent only.
- **mesh / capability / `fs.repo_rw`** — Vaked primitives: a `mesh` of nodes with
  attenuated `capability` grants; delegation may only weaken authority.

---

## 10. Status & next steps

- **Branch:** `feat/local-dogfood-kernel` · **PR:** #267 · **trunk:** `origin/main`.
- **Done:** ralph-on-Ollama (M1) · kernel + 16 tests · POLA lowered from Vaked ·
  hot-path made linear-in-change · L1 LD_PRELOAD observer built+validated on dev-cx53 ·
  Taskfile.
- **Next (pick up here):**
  1. Wire opencode (local model) as the live proposer end-to-end.
  2. Feed `observe_preload.py` output into the kernel's observed gate on dev-cx53
     (close the declared≈observed loop on real syscalls).
  3. Aim ralph/opencode at the dev-cx53 litellm stack (`LITELLM_KEY` + `task point`)
     to free the M1 entirely.
  4. File the `filesystem`-membrane follow-up (make `writeScope` a checked schema).

**Pointers:** design `docs/dogfood/kernel-v0.md` · local model `docs/dogfood/local-ollama-setup.md`
· L1 `docs/dogfood/l1-frida-evidence.md` · the kernel `tools/dogfood/README.md`
· ops `tools/dogfood/Taskfile.yml`.
