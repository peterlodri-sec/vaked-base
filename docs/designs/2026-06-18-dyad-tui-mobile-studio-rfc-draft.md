# Vaked Design RFC (DRAFT) — Flake-Native Capability-Graph Routing for the `vaked-tui` Mobile Operator Surface

**Status: DRAFT — not built, not executed, not a numbered protocol RFC.**
This is a design document only. Nothing herein has been compiled, run, or measured. It is **not** an HCP/Litany numbered protocol RFC (those live under `protocol/rfcs/0001…0007`); if promoted to a protocol RFC it must go through the `hcp-rfc-author` flow. Per the project-wide rule, **no build/compile/execute occurs on the developer machine (M1).** Every "buildable" claim below means *design-buildable on a Linux target* (`dev-cx53`, x86_64-linux) or CI, gated by the 3-gate verify-confirm protocol — never the laptop.

Author: Paige (Tech Writer), compressing the Architect (Winston), Dev/Renderer, Analyst (Mary), UX, and PM (John) roundtable positions.

---

## 0. Dependency ledger — `[design-real]` vs `[aspirational]`

Every external dependency is tagged. `[design-real]` = a file or committed spec exists (verified against `vaked-base` this session). `[aspirational]` = named only, no backing file, or scope materially smaller than claimed.

| Dependency | Tag | Ground-truth note (verified this session) |
|---|---|---|
| `tools/vaked-tui/` (TUI project) | `[design-real]` | Exists. Currently a **TypeScript** package (`src/`, `package.json`, `tsconfig.json`), not Zig. The proposed Zig renderer is greenfield. |
| `tools/vaked-cli` + `tools/VAKED_CLI_README.md` | `[design-real]` | **Exists.** Both files present. Brief's "probably absent" is **wrong** — corrected. It is stdlib-Python remote-exec/scp glue, **not** the TLS-verified OpenRouter SDK path CLAUDE.md mandates. Treat as plumbing, not a hardened tool. |
| `daemons/openrouterd/src/qjs_bindings.zig` | `[design-real]` | Exists. `jsMapMemoryPlanePointer` (line 7–9) does `return @intFromPtr(raw_ptr);` — a **raw host pointer injected into the QuickJS VM as a JSValue**. This is the boundary the arena design forbids and must replace. |
| `daemons/openrouterd/src/layer_collapse.zig` `MemoryPlane` | `[design-real]` | Exists. Fixed-layout `extern struct` (magic/budget/tokens/`conductor_model`/build-status). A single control-block, **not** a general arena. `conductor_model` comment value `"deepseek-v4-pro"` is an **unverified model slug** (see §10). |
| `daemons/openrouterd/src/seccomp_filter.zig` | `[design-real]` file / `[aspirational]` scope | Exists but is a **4-instruction BPF stub** (`BPF_LD` offset 4, one `JEQ`, `RET_ALLOW`, else `RET_KILL_PROCESS`). **No** 22-syscall allowlist, **no** arch gate, **zero** tty/termios/ioctl references. The "22-syscall tty-binding seccomp profile" is **aspirational**. |
| QuickJS bindings (~26 files incl. `daemons/synapsed/quickjs_bindings.zig`) | `[design-real]` | Exist as files. |
| Zig daemons (`agent_guardd`, `eventd`, `openrouterd`, `synapsed`) | `[design-real]` | Exist. `agent_guardd` = egress membrane; `eventd` = append-only hash-chained log. |
| OpenRouter as swarm-default LLM provider | `[design-real]` | Mandated by CLAUDE.md; `daemons/openrouterd/` exists. `OPENROUTER_API_KEY` gating is real; spend is real when set. |
| `docs/superpowers/specs/2026-06-14-sandboxd-seccomp-plan.md` (the **real** allowlist) | `[design-real]` | The only committed syscall allowlist; §5.1 lists **33** syscalls (read/write/openat/close/fstat/lseek/mmap/munmap/mprotect/brk … getrandom/pread64/pwrite64/readv/writev/dup/dup2/fcntl/getpid/gettid/sched_yield/clock_nanosleep). |
| `telemetry.zig` | `[design-real]` | Referenced as the cost/volume instrumentation source for routing decisions. |
| "Tailscale Aperture" | `[aspirational]` | **Zero product files.** One doc mention, and that doc states the vault has 0 files. The mesh node is **generic Tailscale** `[design-real as a generic dependency]`; "Aperture" is not a deliverable — do not schedule against it. |
| Model slugs `DeepSeek-V4-Flash` / `deepseek-coder` / `Qwen3.5-9B` | `[aspirational]` | No repo file matches. Do not pin V1 to them. (Distinct from the `"deepseek-v4-pro"` *comment* in `MemoryPlane`, which is also unverified.) |
| "Liquid Glass" aesthetic | `[aspirational]` | Zero files reference it; brief-level concept only. Interpreted in §4. |

---

## 1. Overview & motivation

`vaked-tui` is the primary operator surface for the Vaked agentic runtime, targeted for V1 at a **mobile (Fiat Ducato van) monitor**. This RFC specifies four coupled subsystems and the economics/UX/timeline that bind them:

1. **Flake-native capability-graph routing** — how a Vaked declaration materializes the daemon graph (OpenRouter LLM path + Zig enforcement daemons + eBPF evidence) that drives the TUI, and where LLM traffic routes (OpenRouter vs. self-host).
2. **A deterministic shared-memory arena** for the QuickJS ⇄ Zig boundary (the data plane the renderer reads).
3. **A zero-dependency Zig ANSI renderer** consuming that arena read-only.
4. **A glare-survivable 12×12 UX grid** for the outdoor mobile context.

The Vaked thesis applies end-to-end: *Vaked declares → Nix materializes → OTP supervises → Zig enforces → eBPF testifies → surfaces reveal.* The capability graph is the declaration; the arena + renderer + routing are the materialized surface.

---

## 2. Flake-native capability-graph routing

### 2.1 The graph

A Vaked declaration compiles to a typed semantic graph whose nodes, for this surface, are: the TUI process, the OpenRouter LLM edge (`openrouterd` `[design-real]`), the shared arena (§3), the enforcement daemons (`agent_guardd` egress membrane, `seccomp_filter` `[design-real]`), and the evidence layer (`eventd` append-only hash-chained log `[design-real]`). Nix materializes these as a `nixosConfigurations.vakedos` host plus daemon configs; OTP supervises; the arena is the inter-actor data plane.

### 2.2 Routing decision — where LLM (AST-heal) traffic goes

LLM routing is **economically governed** (§5), not statically wired. The capability graph carries a routing edge whose target is selected from measured cost/volume telemetry. **Default and only V1-sanctioned path: OpenRouter** (`[design-real]`, per CLAUDE.md), guarded on `OPENROUTER_API_KEY`, executed on the Linux target, never the laptop. V1 must pin to an **OpenRouter-default Claude/Opus slug**, not the aspirational DeepSeek/Qwen slugs (§10).

### 2.3 Materialization posture

The graph is **design-buildable** on `dev-cx53`/CI via `zig build -Dtarget=x86_64-linux` (cross-compile on M1 is allowed; **execution is not**). `tools/vaked-cli` `[design-real]` can drive the remote build/deploy as plumbing, but it is **not** the TLS-verified OpenRouter SDK path the conventions mandate; production deploy should migrate to `@vaked/openrouter-ts` / `adk-rust`.

---

## 3. Deterministic shared-memory arena (QuickJS ⇄ Zig boundary)

### 3.1 What ground truth forces

- `qjs_bindings.zig:9` injects `@intFromPtr(raw_ptr)` across the boundary today — exactly the raw cross-actor pointer this design forbids. **The current binding must be deleted.**
- `MemoryPlane` (`layer_collapse.zig`) is a fixed control-block, not a general arena — no handle table, no bounds, no offset discipline.
- **Verdict: a new module `arena.zig`, not a `MemoryPlane` retrofit.** `MemoryPlane` is demoted to *one typed handle* (kind = control-block) inside the arena, preserving its getters.

### 3.2 Layout (offset-based, bounds-checked, never raw pointers)

Single contiguous page-aligned `mmap`, fixed total size at create time. All references are **offsets from arena base**, so the arena survives being mapped at different addresses in two actors.

```
+0x000  Header (one cache-line, align 64)
          magic u32 = 0x7C242080 (reuse GENESIS_SEAL), version u16,
          arena_size u32, seq u64 (even=stable/odd=writing),
          handle_count u32, handle_cap u32, heap_head u32, owner_pid u32
+0x040  Handle table: handle_cap × HandleEntry (16B):
          off u32 (0=null), len u32, kind u16, gen u16, flags u32 (RO/OWNED_BY_ZIG/OWNED_BY_JS)
+....   Data region: bump-allocated, offsets only
```

**Boundary contract:** QuickJS never receives a pointer. It receives a `Handle = packed u64 (index:32 | gen:32)`. Every JS access goes through a Zig FFI shim `arena_read/arena_write` that: (1) bounds-checks `index < handle_count`; (2) checks `table[index].gen == handle.gen` (defeats use-after-free); (3) overflow-checks `off+len <= entry.len` and `entry.off+entry.len <= arena_size` (`std.math.add` with error); (4) only then computes `base + entry.off + off` *inside Zig*, copying into a JS-owned ArrayBuffer.

### 3.3 Determinism & single-writer discipline

- Bump allocator, no free-list, no `getrandom`/address-dependent hashing in the hot path → identical event sequence yields **byte-identical** arena state.
- Exactly one writer (the Zig daemon side) owns `heap_head`, the handle table, and `seq`. JS is read-mostly; JS "writes" are serialized requests applied by the writer (matches the existing single `*MemoryPlane`).
- **Seqlock publish:** writer `seq++` (odd) → mutate → `seq++` (even); readers snapshot/recheck/retry. No locks, no `futex` in the common path.

### 3.4 Lifecycle & syscall budget (the load-bearing decision)

- **create** (writer): `memfd_create("vaked-arena", MFD_CLOEXEC)` → `ftruncate` → `mmap(MAP_SHARED)` → init header. Anonymous memfd replaces the current named-file `open`+`mmap` in `layer_collapse.zig` (no on-disk path, no `open(2)`).
- **attach** (reader): receive fd (SCM_RIGHTS / same fd in-proc) → `mmap` → validate magic/version/size → `close(fd)` (mapping survives).
- **teardown:** `munmap` (+ `close` memfd on writer).

Cross-check against the **real** allowlist (`sandboxd-seccomp-plan` §5.1, 33 syscalls): `mmap`/`munmap`/`mprotect`/`close` are **present**; `memfd_create` and `ftruncate` are **absent**. **Resolution: arena `create()` runs in the pre-seccomp daemon-setup phase; only `mmap`/`munmap`/`mprotect`/`close` need to be in the post-seccomp workload profile — and all four already are.** This keeps the arena inside the syscall budget without growing the allowlist. (Alternative — add `memfd_create`+`ftruncate`, pushing 33→35 — requires seccomp-owner sign-off; see §11.)

### 3.5 Event-sourcing mapping

The data region is an append-only ring of event records; each `arena_write` bump-allocates a new handle (never overwrites), so the handle table **is** the event index and `seq` is the logical clock. Canonical hashing stays `eventd`'s job (`[design-real]`, RFC 0004 §3.1); the arena emits payloads only.

---

## 4. `vaked-tui` strict-ioctl ANSI renderer (Zig, zero-dep) — UNCOMPILED SKELETON

### 4.1 Domain stance

Pure Zig, **zero external deps** — `std.os.linux` raw syscalls only, no ncurses/termcap/terminfo/libvaxis. This matches the verified in-repo house style (`tools/inbox/inbox.zig`, `tools/monologue/monologue.zig` go straight to `std.os.linux.<syscall>`). No JS/QuickJS in the render hot path; panels may be *produced* by JS upstream but the renderer only sees resolved `Cell` bytes.

### 4.2 Module layout (`tools/vaked-tui/src/render/`)

`term.zig` (termios raw-mode + winsize + SIGWINCH), `cell.zig` (`Cell` = u21 rune + packed `Style`; `Grid` flat row-major), `framebuffer.zig` (front/back double buffer + dirty-diff + coalesce buffer), `ansi.zig` (comptime escape constants, alloc-free SGR/cursor encoders), `panels.zig` (read-only arena view via offset handles), `renderer.zig` (orchestrator `init/deinit/resize/render`).

### 4.3 Performance invariants (design targets, NOT measured)

- **One `write(2)` per frame.** Compose everything into a single preallocated buffer; emit once. Syscall count dominates the budget. A per-cell-write design is rejected.
- Double-buffer + dirty-diff; equal cells emit zero bytes; CUP only on cursor jump; SGR only on style change. Full repaint only on resize/first frame.
- **<5ms refresh is a design target, unmeasured and unmeasurable here** (no-build rule). Verification requires a perf harness on `dev-cx53` (`clock_gettime(CLOCK_MONOTONIC)` around `render()`, p99 over a scripted trace). It must **not** be quoted as a measured result.
- Allocation-free at steady state; allocation only at init and on resize.

### 4.4 Safety invariants

- SIGWINCH handler is async-signal-safe: it sets an atomic flag only; all resize work happens in the render loop.
- termios restored on **every** exit path including panic (`deinit` + panic hook); alt-screen `1049h`/`1049l` brackets the session; `?25h` show-cursor on exit.
- The arena is **untrusted input**: every offset-handle resolve bounds-checks against `ArenaView.len` before dereferencing — out-of-range = error, never a segfault.

### 4.5 Arena contract (consumed from §3)

Renderer receives `ArenaView { base, len }` + a slice of `PanelHandle { offset, len, rows, cols }`; `panels.zig` resolves to `[]const Cell` with a bounds check. **These types are PROPOSED, not real** — `daemons/synapsed/memory_guard.zig` exposes only `verifyAllocationLimits(...) -> bool` and an `arena_limit_bytes` field; there is **no** published offset-handle accessor. Winston must confirm the handle struct, offset width (u32 vs u64), and cross-process-vs-in-process topology before `PanelHandle` is frozen (§11).

---

## 5. Routing economics (Analyst)

### 5.1 Breakeven (the only claim defended without caveats)

Route AST-heal traffic local only when self-host beats per-call OpenRouter over the same window:

```
N* = fixed_host_$/day / (cost_per_call_OR − variable_local_$/call)
```

- `N` (sustained calls/day) `> N*` → self-host wins; `N < N*` → OpenRouter wins (zero fixed cost).
- Denominator must be `> 0`. **Cache hits shrink effective `cost_per_call_OR`, raising `N*` — structurally favoring OpenRouter.**
- This formula is provider-agnostic and domain-correct. Everything numeric below is an **assumption**.

### 5.2 Worked example — INPUTS UNVERIFIED `[aspirational]`

Brief assumptions (no repo file matches the model slugs): OpenRouter proxy "1.8B tok/$10" ⇒ ~$5.56e-9/tok; ~2k tok/heal-call ⇒ `cost_per_call_OR ≈ $1.1e-5` (≈$0.7e-5 with assumed 50% cache hit). Assumed Qwen-class box ~$200/mo ⇒ `fixed_host_$/day ≈ $6.67`; `variable_local ≈ $1e-6`.

```
N* = 6.67 / (0.7e-5 − 0.1e-5) ≈ 1.11 MILLION heal-calls/day
```

A beta TUI does ~10²–10⁴/day. **OpenRouter wins by 2–4 orders of magnitude.** Robust across the assumption band (halving the box → `N* ≈ 555k/day`); only collapses if real OpenRouter price is ~10× the proxy — which is **why inputs must be measured, not assumed**.

### 5.3 Hidden self-host costs (widen OpenRouter's lead)

`fixed_host_$/day` is not just rent: + ops/patching, + cold-start on a 9B model, + idle-GPU underutilization, + a self-host's **own** egress membrane + sandbox. `agent_guardd`/`seccomp_filter` are **specs, not a turnkey isolation layer** (`seccomp_filter.zig` is a 4-instruction stub, ~880B — see §0), so isolation is unbudgeted fixed cost.

### 5.4 Recommendation

**Route to OpenRouter for V1. Period.** Revisit self-host only when (a) *measured* sustained volume approaches a `N*` computed from *real* prices, and (b) isolation/ops fixed costs are budgeted. Instrument `cost_per_call_OR` and calls/day from day one via `telemetry.zig` `[design-real]`.

---

## 6. UX — 12×12 solar-glare dashboard (the "solarHardGlare" profile)

### 6.1 Glare physics overrides aesthetics

"Liquid Glass" `[aspirational]` is translucency/blur/low-alpha layering — and **ANSI has no alpha channel**; direct sun washes out exactly those mid-tones. Translation rule: **Liquid Glass = maximal luminance separation + heavy structural borders.** Glass is the *feel* (depth via z-order/borders), not the implementation.

### 6.2 Palette — 5 colors max, true-black bg

Luminance contrast is the only knob that survives glare. Require **true terminal black bg (256 code 16, `#000000`)**, not the existing TUI `#040804`. Foreground near-max luminance. Permitted set: **231 white** (primary text), **226 yellow** `#ffff00` (alerts/headers — highest photopic luminance), **46 green** `#00ff00` (pass), **196 red** `#ff0000` (fail), **16 black** (bg). Target on-screen contrast ≥10:1 *after* the glare floor (~≥15:1 nominal).

- **Ban pure-blue-on-black** (blue 21 ≈ 7% relative luminance, near-invisible). Cyan permitted **only** as a non-load-bearing secondary label.
- **Bold (SGR 1) required** on all foreground text. **Banned:** dim/faint (SGR 2), italic, 24-bit truecolor gradients. Use **256-color SGR** (`38;5;N` / `48;5;N`) for portability.
- **Heavy double-line / block borders** (`═ ║`, or `█`) in 226/231 — thin single lines disappear in glare. Borders carry the "glass-pane edge" metaphor.
- **Monochrome-degrade fallback mandatory:** status conveyed by GLYPH + POSITION + TEXT LABEL (`FAIL`, `[X]`, `!!!`), never by color alone (WCAG-equivalent safety rule).

### 6.3 Layout — 144 cells (hard canvas)

Row 1 (12 wide) TOP BAR = status/clock/profile. AGENT-EXEC = rows 2–7 × cols 1–7 (6×7, primary). SWARM-METRICS = rows 2–7 × cols 8–12 (6×5, KPIs: active agents, `val_bpb` `[aspirational]` source, queue depth). MEMORY-LOG = rows 8–12 × cols 1–12 (5×12 append-only scroll, newest top). **No panel chrome may consume >1 cell of border per side** or content drowns (a 6×7 box minus borders ≈ 5×5 interior ≈ 25 glyphs). The grid may be under-spec'd for the data (see §11).

### 6.4 Coexistence with existing profiles

The existing three profiles (`denseMatrixGreen`, `cleanGraphCyberpunk`, `tacticalGraveyard`, commit `dc92de2`) use non-black backgrounds and mid-luminance accents — **fine indoors, fail the glare floor outdoors.** This RFC **adds a 4th profile (`solarHardGlare`)** selected by environment; it does not delete the existing three. The existing `colorscheme.ts` stores **hex** (hinting truecolor emit); the 256-color mapping here is **lossy and provisional** until the emit path (`main.ts`) is read (§11).

---

## 7. V1 14-day critical path (PM)

**Two workstreams, one hard coupling.** SOFTWARE = arena+renderer lock + Linux/CI build. HARDWARE = van power delivery + monitor + Tailscale mesh node. The schedule killer is the **no-build-on-laptop rule**: software cannot validate until a paid build target (`dev-cx53`/CI + Vast/GPU for agent loops) is live **and** the van's Tailscale node can reach it. **The critical path runs through hardware.**

| Day | Track | Milestone |
|---|---|---|
| D1 | CP HW+infra | Procure van DC-DC/battery spec, monitor, confirm `dev-cx53` reachability; provision van Tailscale node identity; Gate-1 check `ssh dev-cx53 'which zig && zig version && df -h && free -h'`. **Blocker if any fails.** |
| D2 | CP infra / ∥ SW | Wire CI build fallback; first green remote build of `vaked-tui`. ∥ Freeze arena allocator + renderer interface (laptop = edit/design only). |
| D3 | CP HW / ∥ SW | Bench power test (battery→DC-DC→monitor+compute), measured draw. ∥ Arena impl built remote. **Gate: infra trio green here or V1 slips.** |
| D4 | ∥ SW / ∥ HW | Renderer first paint on `dev-cx53` viewed via Tailscale. ∥ In-van monitor+compute mount. |
| D5 | ∥ SW / ∥ HW | Arena+renderer integration + input loop. ∥ Tailscale node installed in van. |
| **D6** | **CP join** | **First end-to-end: van node → remote-built TUI → live render on van monitor.** Convergence point; slips cascade. |
| D7 | buffer | D6 defect burn-down. |
| D8 | ∥ SW | OpenRouter agent loop wired (guarded on `OPENROUTER_API_KEY`), spend through `dev-cx53`. |
| D9 | ∥ SW | TUI ↔ OpenRouter ↔ MemoryPlane/daemon round-trip on target. |
| **D10** | **CP** | **Power soak test** (off-grid full-stack) + thermal under TUI+agent load. |
| D11 | buffer | — |
| **D12** | **CP** | **V1 acceptance:** van cold-start, Tailscale up, remote build current, TUI renders, agent call succeeds, power within budget. |
| D13 | buffer | — |
| D14 | ship/contingency | — |

**Critical path:** D1→D2→D3 (infra trio) → D6 (SW/HW join) → D10 (power soak) → D12 (acceptance). Arena+renderer SW has genuine parallel slack; the date is set by build-target + Tailscale + power.

---

## 8. Hard constraints (consolidated, normative)

1. **No raw pointer crosses the QuickJS⇄Zig boundary.** JS receives an opaque packed `u64` Handle; `qjs_bindings.zig:9` `@intFromPtr` behavior is deleted.
2. All arena access is offset-based and bounds+generation+overflow-checked inside Zig before any `base+offset`.
3. Arena is offset-relative end to end (address never affects contents) → determinism + cross-actor safety.
4. Single-writer; readers use a seqlock; no locks in the common path.
5. Workload-phase syscalls confined to `mmap`/`munmap`/`mprotect`/`close` (all in the §5.1 allowlist); `memfd_create`+`ftruncate` run **pre-seccomp** during setup.
6. Deterministic bump allocator; no free-list, no `getrandom` in the hot path.
7. Anonymous `memfd_create(MFD_CLOEXEC)` replaces the named-file `open`+`mmap`.
8. Renderer: **zero external deps**, **one `write(2)`/frame**, async-signal-safe SIGWINCH, termios restored on every exit incl. panic, allocation-free steady state, arena treated as untrusted.
9. UX: true-black bg, ≤5-color high-luminance palette, bold required, no dim/italic/truecolor-gradient, heavy borders, mandatory monochrome-degrade.
10. Routing governed by `N*` from **measured** `cost_per_call_OR` and calls/day; OpenRouter is the V1 default and only sanctioned path; agent loop runs on the target host.
11. **No build/compile/run on the M1.** SPEC only; design-buildable target = `dev-cx53`/CI under the 3-gate protocol. The <5ms budget is a design target, never a measured claim.

---

## 9. Unverified assumptions (read before relying on anything here)

- **Tailscale Aperture** — does not exist (1 doc mention; vault has 0 files). Mesh node is generic Tailscale. Do not schedule against an "Aperture" deliverable.
- **`vaked-cli`** — **does** exist (`tools/vaked-cli` + `tools/VAKED_CLI_README.md`); the brief's "probably absent" is corrected. But it is stdlib-Python scp glue, not the mandated TLS-verified OpenRouter SDK path.
- **Model slugs `DeepSeek-V4-Flash` / `deepseek-coder` / `Qwen3.5-9B`** — unverified, no repo match. The `"deepseek-v4-pro"` string in `MemoryPlane.conductor_model` is also an unverified slug. V1 pins to an OpenRouter-default Claude/Opus slug.
- **"22-syscall seccomp profile binding tty syscalls"** — does not exist. `seccomp_filter.zig` is a 4-instruction BPF stub with no allowlist, no arch gate, **zero** tty/termios/ioctl refs. The only real allowlist (`sandboxd-seccomp-plan` §5.1) lists **33** syscalls. The TUI's required tty syscalls (`ioctl TIOCGWINSZ`, `TCGETS/TCSETSF`, `rt_sigaction`, `write`) are in **neither** — unreconciled.
- **Mary's economic inputs** — OpenRouter price proxy "1.8B tok/$10", ~2k tok/heal-call, 50% cache-hit rate, ~$200/mo box, ~$1e-6/call variable, 10²–10⁴ beta calls/day are **all assumptions**, none measured.
- **Van power budget** — no battery capacity / DC-DC rating / monitor draw / compute TDP figures exist in repo. Feasibility unconfirmed.
- **`dev-cx53` liveness, Vast/GPU billing, `OPENROUTER_API_KEY` funding** — asserted by CLAUDE.md but not proven this session.
- **Arena topology** — out-of-process (seqlock load-bearing) vs. in-process (current `qjs_bindings.zig` reality; boundary is the FFI call) is unconfirmed. Handle discipline is mandatory either way.
- **Renderer plumbing** — no termios/`TIOCGWINSZ`/SIGWINCH/`tcsetattr` code exists anywhere in repo; the Zig renderer is fully greenfield. Whether Zig 0.16 `std.posix` exposes termios cleanly vs. needing raw `ioctl(TCGETS/TCSETSF)` is unchecked. Whether the renderer replaces the TS TUI or is a new binary is undecided.
- **UX target hardware** — van monitor color depth (16/256/truecolor), nit brightness, and character-cell aspect ratio are unknown; the entire palette/layout decision hinges on them. `colorscheme.ts` stores hex (hints truecolor emit) — `main.ts` emit path unread.
- **Panel data contracts** — no brief file defines agent-exec / swarm-metrics / memory-log contents or priority; `val_bpb` as a live TUI-wired source is unverified.

---

## 10. Open cross-role conflicts

See `openConflicts`. These are unresolved at draft time and require owner sign-off before any build is gated.

---

## 11. Decision log / required sign-offs

1. **Seccomp owner:** accept pre-seccomp arena creation (recommended) OR add `memfd_create`+`ftruncate` (33→35).
2. **Daemon owner:** accept the memfd switch (deletes named-file `open`+`mmap`) and deletion of the `@intFromPtr` JS binding.
3. **Architect (Winston):** publish the real handle struct + offset width + topology so the renderer can freeze `PanelHandle`.
4. **Architecture/rendering owner:** confirm the TUI color-emit path (256 vs truecolor) so the `solarHardGlare` palette can be fixed.
5. **Infra/PM:** prove the infra trio (`dev-cx53` + Tailscale + paid key) green by D3.
6. **Hardware:** supply measured van power budget before D3 bench / D10 soak.


---

## Appendix Z — Adversarial verify corrections (verify FAILED; fixes applied here)

The 2-lens adversarial pass returned **pass=false**. The failures were **factual-accuracy
errors in this draft**, NOT implementation overclaims (the "not built / not measured /
no-build-on-M1" posture held, the arena offset-handle design and the caveated <5ms target
were verified honest). Corrections, each re-grounded against the tree this session:

1. **SECCOMP INVERSION (load-bearing).** The body analyzed `seccomp_filter.zig` (a dead
   4-instruction BPF stub). The **wired** file is `seccomp.zig` — `main.zig:9`
   `@import("seccomp.zig")`, applied at `main.zig:275`. `seccomp.zig:5` is a **real
   22-syscall allowlist**: `{0,1,257,3,41,42,44,45,291,233,232,9,11,10,12,60,231,318,228,202,425,426}`
   = read,write,openat,close,socket,connect,sendto,recvfrom,epoll_create1,epoll_ctl,
   epoll_wait,mmap,munmap,mprotect,brk,exit,exit_group,getrandom,clock_gettime,futex,
   io_uring_setup,io_uring_enter. So the "22-syscall profile" is **[design-real]**, not
   aspirational — the body's §0/§3.4/§5.3/§8.5/§9 seccomp narrative is RETRACTED.
2. **REAL BUILDABILITY CONFLICT (was missed).** The wired 22-list contains **no `ioctl`
   and no `rt_sigaction`**. The renderer's mandatory tty path — `ioctl(TIOCGWINSZ)` for
   winsize, `rt_sigaction` for SIGWINCH — would be **SIGKILL'd** under the live profile.
   Reconciliation (add `ioctl`+`rt_sigaction`, → 24 syscalls; or run the renderer outside
   this daemon's profile) is **unresolved** and needs the seccomp owner. This is the genuine
   blocker, not the stub.
3. **Syscall count.** The `sandboxd-seccomp-plan` §5.1 allowlist is **~31** syscalls (and
   DOES contain `ioctl`/`rt_sigaction`/`write`), not "33". Note it diverges from the wired
   22-list (the plan is not what's loaded).
4. **`deepseek-v4-pro` is [design-real], wired** — `tools/openrouter/cli.py:30`,
   `tools/openrouter/deliberate.py:23,50` (priced 0.27/0.27) — not merely a MemoryPlane
   comment. (`DeepSeek-V4-Flash` / `Qwen3.5-9B` / `deepseek-coder` remain genuinely absent →
   `[aspirational]` tags correct.)
5. **"Tailscale Aperture" is more real than §0 claimed.** `.vaked/runtime_policy.zig`
   defines `assertApertureSecurity()`; swe-af specs pin a tailnet gateway + grant cap
   `tailscale.com/cap/aperture`. The flat "zero product files" claim is **false** and
   RETRACTED. (The conservative scheduling stance — do not pin the van V1 to an "Aperture
   deliverable" — still holds; the supporting fact was wrong.)

**Net:** the design (arena, renderer, routing, UX, timeline) stands; the seccomp section is
corrected and now exposes a real renderer↔profile conflict that must be resolved before any
build. Nothing here is built, run, or measured.
