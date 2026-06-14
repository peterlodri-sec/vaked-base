# sandboxd-seccomp-plan — seccomp-bpf allowlist + cgroup-v2 slice attachment alongside agent_guardd eBPF hooks (WP4-S2)

## Status

Planning artifact (2026-06-14). A **companion** to the broad sprint spec
[`2026-06-14-wp4-s2.md`](2026-06-14-wp4-s2.md), narrowed to two coupled
mechanisms that the broad spec lists but leaves as named-Open boundaries:

1. the **seccomp-bpf allowlist** sandboxd installs under `PR_SET_NO_NEW_PRIVS`
   before `execve` (`wp4-s2.md` §3, §5.3 — the one module with no Python
   oracle);
2. the **cgroup-v2 leaf ↔ agent_guardd eBPF attach** coordination — i.e. how
   the `vaked/<agent-id>/` slice sandboxd creates becomes the cgroup at which
   agent_guardd's `BPF_CGROUP_INET_EGRESS` program attaches "alongside"
   sandboxd's confinement.

This plan **resolves**, with provenance, the design's two named Open items that
govern (2):

- `wp4-s2.md` §7 (dependency table): *"the `vaked/<agent-id>` cgroup subtree S2
  creates is where guardd's egress program attaches; netns programming is
  guardd's."*
- [`2026-06-13-sandboxd-design.md`](2026-06-13-sandboxd-design.md) §Open
  *"Network-namespace ownership — sandboxd builds the netns, but the `network`
  membrane ... is agent-guardd's. Who creates vs who programs the netns."*
- sandboxd-design §Open *"fs-snapshotd ⇄ sandboxd overlay-ownership boundary"*
  (the directory-lifecycle precedent this plan reuses for the cgroup leaf:
  one creator, one accountant).

It does **not** re-litigate the S2/S5 scope reconciliation; it inherits it
verbatim from `wp4-s2.md` §3/§5.3: **the seccomp filter install is S2; the
capability→syscall-set lowering (grant→profile) is the WP4-S5 hook.** Per the
repo's "named, not silently resolved" convention (`wp4-s2.md` §1, CLAUDE.md §1),
every Open-item resolution below is phrased *"this plan proposes X (provenance:
…)"*, not asserted as settled contract.

Build target `dev-cx53` (Linux x86_64, kernel 6.x, cgroup-v2) is OFF-LIMITS for
the current autoresearch window. Everything marked **M1-local** must pass on
aarch64-darwin without it (`zig 0.16.0`, `cargo 1.95.0`, arch arm64, verified on
this host 2026-06-14). `dev-cx53` legs are kernel-effect only.

## 1. Objective

Make a sandboxed worker's runtime defense the **intersection** of two
kernel-enforced layers that share exactly one anchor — the worker's cgroup-v2
leaf:

- **seccomp-bpf** restricts the *syscall surface* of the workload process
  (classic-BPF allowlist, default-deny `RET_ERRNO(EPERM)`), installed by
  sandboxd inside the child after all privileged setup and before `execve`
  (`wp4-s2.md` §5.1 steps 7–9).
- **agent_guardd's eBPF cgroup program** observes/gates the *egress surface* of
  every process in that same leaf (`BPF_CGROUP_INET_EGRESS`, cgroup-scoped —
  [`agent_guardd/bpf.py`](../../../agent_guardd/bpf.py) lines 39, 160–173).

The two layers are orthogonal in mechanism (seccomp = per-thread syscall filter;
eBPF egress = per-cgroup packet hook) but **must converge on one leaf path** so
that "the processes sandboxd confines" and "the processes guardd testifies on"
are the same set. This plan fixes:

1. the exact bytes and structure of the S2 `default` seccomp filter and how it
   is asserted on M1 without executing `seccomp(2)`;
2. the **leaf-path agreement contract** (sandboxd's `leaf_path(agent_id)` is the
   single source of truth; guardd attaches there instead of its current
   throwaway `vaked_guard_<pid>` cgroup);
3. the **attach/teardown handshake ordering** relative to `execve` and `rmdir`,
   so there is no unfiltered-egress window and no rmdir-while-live failure.

### 1.1 Non-goals (explicit, with provenance)

- **Live in-kernel egress enforcement is NOT delivered here.** Today guardd's
  loadable program is the deny-by-default *posture* (`return 0/1`), **not
  allow-set-aware**; `bpf.py:LoadReport.mechanism` is *always* `"reference"` and
  the attach is a **probe-then-release** (`bpf.py` lines 93–105, 226–235;
  `docs/runtime/agent-guardd.md` "Attach (probe)" row). What S2 delivers for
  layer (2) is the **attach point + lifecycle handshake**; the allow-set-aware
  `cgroup/skb` program that flips `mechanism` to `"ebpf-cgroup"` is the guardd
  follow-up (`agent-guardd.md` §Next item 1). Writing "egress is enforced
  in-kernel" would contradict the oracle.
- **Grant→seccomp-profile and grant→egress-policy lowering** is WP4-S5
  (`wp4-s2.md` §3, §5.3). S2 ships a fixed `default` profile and a
  stubbed-but-wired `cfg.seccomp.profile` read.
- **netns programming / DNS oracle** is guardd's (`namespace.py` lines 19–23;
  sandboxd-design §Open). sandboxd creates the netns; this plan shows why the
  cgroup attach is **independent of** netns ownership (§5.4).
- **Canonical hashing** — eventd owns bytes; sandboxd emits payloads only
  (`wp4-s2.md` §1.2; [`agent_sandboxd/eventd.py`](../../../agent_sandboxd/eventd.py)).

## 2. Inputs and oracles

### 2.1 Per-module oracles

| Concern | Oracle | Held identical |
|---|---|---|
| cgroup leaf path | [`agent_sandboxd/cgroup.py`](../../../agent_sandboxd/cgroup.py) `cgroup_path` / `_VAKED_SUBTREE` | leaf = `<root>/vaked/<agent-id>` (lines 93–95, 47–48) |
| cgroup limit-file content | `cgroup.py` `apply_cgroup_limits` | `memory.max`/`pids.max`/`cpu.max`=`"<quota> <period>"`/`io.max` bytes (lines 167–194) |
| cgroup teardown rule | `cgroup.py` `teardown_cgroup` | `rmdir` only after no live procs; kernel refuses otherwise (lines 209–219) |
| eBPF attach call shape | `agent_guardd/bpf.py` `attach`/`detach` | `BPF_PROG_ATTACH`/`DETACH` at `BPF_CGROUP_INET_EGRESS` on a cgroup *fd* (lines 160–186) |
| eBPF attach-point selection | `bpf.py` `load_membrane` lines 218–219 | **the line this plan changes**: today `vaked_guard_<pid>`; proposed `vaked/<agent-id>` |
| spawn/kill/access payloads | `eventd.py` `spawn_event`/`kill_event`/`access_event` | `kind`/`v`/field set (lines 37–109) |
| seccomp filter | **none** (see §3) | modelled on `bpf.py`'s `_insn` ABI-direct pattern (lines 51–53) |

### 2.2 Config input

Same `daemons/sandboxd/testdata/fixture.sandbox.json` as `wp4-s2.md` §2.2. The
two fields this plan consumes:

```json
"seccomp": { "profile": "default" },
"agent_id": "fixture-worker"
```

`agent_id` is the join key: `cgroup.leaf_path("fixture-worker")` ==
`<root>/vaked/fixture-worker` is *both* the slice sandboxd writes limits into
*and* the directory guardd opens an fd on to attach. There is **no separate
guardd-cgroup field** — that is the whole point of the contract (one anchor).

### 2.3 Host substrate (already present; no host change)

- `security.allowUserNamespaces = true` and cgroup-v2 unified at `/sys/fs/cgroup`
  ([`hosts/vakedos/configuration.nix`](../../../hosts/vakedos/configuration.nix)
  lines 136–138; sandboxd-design line 24).
- `networking.nftables.enable = true` — the nftables backend that **composes
  with** the cgroup/BPF egress programs guardd loads
  (`configuration.nix` lines 132–134).
- The `vaked` subtree **delegated** to sandboxd's uid (`cgroup.py` §Privilege
  note lines 25–33; systemd `Delegate=`). This delegation is the permission
  basis for §5.4's attach-by-other-daemon requirement.

## 3. The seccomp asymmetry (inherited from `wp4-s2.md` §3)

`seccomp.zig` has **no Python oracle** — `agent_sandboxd` never implemented
seccomp (grep confirms: seccomp appears only in design/threat-model prose). Its
model is the ABI-direct pattern of `bpf.py`: assemble the program as
struct-packed instructions (no libseccomp/libbpf). Acceptance is therefore
**self-consistent byte assertions** (filter == hand-derived golden, §6.1) plus
**kernel behaviour** (a disallowed syscall is ERRNO'd/killed, §6.2).

The threat-model mandate this satisfies: `docs/language/THREAT_MODEL.md`
§Scenario C item 1 *"Zig daemons should run in OS-level sandboxes (seccomp, …)"*
(cited in `wp4-s2.md` §3).

## 4. File layout (paths to create / modify)

A **subset** of `wp4-s2.md` §4 — only the files this plan's two mechanisms own,
plus the one guardd change the contract requires. All sandboxd paths under
[`daemons/sandboxd/`](../../../daemons/sandboxd/) (build shell exists:
`build.zig`, `build.zig.zon`, `src/main.zig` stub, `README.md`).

```
daemons/sandboxd/
  src/
    seccomp.zig             # NEW: classic-BPF allowlist assembly + install (no oracle)
    cgroup.zig              # NEW: leaf_path + limit writers + teardown (oracle: cgroup.py)
    guard_handshake.zig     # NEW: "leaf-ready" barrier emit + teardown gate (§5.4)
    linux.zig               # NEW (shared w/ wp4-s2): seccomp/cgroup/PR_* constants, structs
  testdata/
    fixture.sandbox.json    # NEW (shared): the §2.2 fixture
    seccomp.default.golden  # NEW: hex of the assembled x86_64 default filter (M1 byte oracle)
  test/
    seccomp_asm_test.zig    # NEW: assemble("default") == golden, byte-for-byte (M1)
    cgroup_leaf_test.zig    # NEW: leaf_path agreement + limit-file content vs cgroup.py (M1)
    handshake_order_test.zig# NEW: pure ordering-state-machine assertions (M1)
    guard_attach_smoke.zig  # NEW: real attach to sandboxd leaf + egress effect (dev-cx53)
```

Guardd side (Python reference — the oracle the Zig guardd port later mirrors):

```
agent_guardd/bpf.py         # MODIFY: load_membrane() gains an explicit `cgroup_dir`
                            #   param; when given, attach there instead of minting
                            #   vaked_guard_<pid> (lines 218–219). Default behaviour
                            #   (probe own cgroup) preserved for `probe`/`demo`.
```

`linux.zig` centralises the **x86_64** ABI (target is x86_64-linux):
`__NR_seccomp`, `__NR_prctl`, `PR_SET_NO_NEW_PRIVS`, `SECCOMP_SET_MODE_FILTER`,
`SECCOMP_RET_KILL_PROCESS`/`RET_ERRNO`/`RET_ALLOW`, `AUDIT_ARCH_X86_64`, and the
`sock_filter`/`sock_fprog`/`seccomp_data` layouts (per `wp4-s2.md` §4). Keep
`std.os.linux` constants where Zig 0.16 provides them; define the rest locally
(the guardd-bpf precedent).

## 5. Algorithm / design

### 5.1 The seccomp `default` filter (seccomp.zig)

Classic-BPF program consumed by `seccomp(SECCOMP_SET_MODE_FILTER)`, assembled as
`[]sock_filter` then wrapped in `sock_fprog`. Structure (matches `wp4-s2.md`
§5.3, made byte-precise here):

```
L0:  BPF_LD  | BPF_W | BPF_ABS, k = offsetof(seccomp_data, arch)
L1:  BPF_JMP | BPF_JEQ | BPF_K, k = AUDIT_ARCH_X86_64, jt=0, jf=(KILL)
L2:  BPF_LD  | BPF_W | BPF_ABS, k = offsetof(seccomp_data, nr)
L3..: for each nr in ALLOWLIST (ascending):
        BPF_JMP | BPF_JEQ | BPF_K, k = nr, jt=(ALLOW), jf=0
Lk:  BPF_RET | BPF_K, k = SECCOMP_RET_ERRNO | EPERM      # default-deny (observable)
LA:  BPF_RET | BPF_K, k = SECCOMP_RET_ALLOW
LX:  BPF_RET | BPF_K, k = SECCOMP_RET_KILL_PROCESS       # arch mismatch
```

- **Arch gate first** (L1): a syscall issued under any arch other than
  `AUDIT_ARCH_X86_64` → `KILL_PROCESS`. This closes the x32/multi-arch
  syscall-number-aliasing hole. The golden encodes the **target's**
  `AUDIT_ARCH_X86_64` (`0xC000003E`), *not* the aarch64 M1 host's arch — the
  M1 test asserts pure assembled bytes and never calls `seccomp(2)`, so the host
  arch cannot leak in (§6.1).
- **Default action** `SECCOMP_RET_ERRNO | EPERM` — fail-closed but **observable**
  (the workload sees `-EPERM`, the run continues, the violation is diagnosable).
  `RET_KILL_PROCESS` is a config toggle for the strict profile (S5 wiring).
- **ALLOWLIST (`default` profile, S2-fixed, conservative compute worker):**
  `read write openat close fstat lseek mmap munmap mprotect brk
  rt_sigaction rt_sigprocmask rt_sigreturn ioctl clock_gettime exit
  exit_group nanosleep futex getrandom pread64 pwrite64 readv writev
  dup dup2 fcntl getpid gettid sched_yield clock_nanosleep`. Sorted ascending
  by x86_64 `__NR_*` for deterministic JEQ ordering. The **exact** set is
  frozen in `seccomp.default.golden`; this list is the human-readable shadow of
  those bytes. (S5 replaces the fixed set with a grant→set lowering;
  `cfg.seccomp.profile` is read and routed today, only `"default"` resolves —
  `wp4-s2.md` §5.3.)
- **Install ordering** (the load-bearing invariant, `wp4-s2.md` §5.1 step 7):
  `prctl(PR_SET_NO_NEW_PRIVS, 1)` **before** `seccomp(SECCOMP_SET_MODE_FILTER)`;
  the filter installed **after** all privileged setup (mounts, cgroup join,
  uid_map) and **before** drop-privs + `execve`, so the filter covers the
  workload but not sandboxd's own setup syscalls.

`assemble(profile) []sock_filter` is **pure** (no syscalls), M1-tested against
the golden (§6.1). `install(filter)` is the effectful `prctl`+`seccomp` pair,
dev-cx53 only (§6.2).

### 5.2 cgroup leaf (cgroup.zig)

Pure helper `leaf_path(agent_id) = "vaked/" ++ agent_id` reproduces
`cgroup.py:cgroup_path` exactly (the `_VAKED_SUBTREE`=`"vaked"` join). Limit
writers (`memory.max`/`pids.max`/`cpu.max`/`io.max`) take a `cgroup_root`
parameter so M1 tests redirect to a temp dir (the `cgroup.py` mock discipline,
lines 35–38). Content parity is against `apply_cgroup_limits`, the formatter (per
`wp4-s2.md` §5.4 oracle note), not `daemon.spawn`.

`leaf_path` is also exported as the **public join key** for the guardd handshake
(§5.4): it is the *only* place the leaf path is computed. No second derivation.

### 5.3 cgroup ↔ guardd ownership (the contract)

Proposed division (provenance: `wp4-s2.md` §7; sandboxd-design §Open
"Network-namespace ownership", "fs-snapshotd ⇄ sandboxd overlay-ownership"):

| Action | Owner | Mechanism |
|---|---|---|
| `mkdir vaked/<agent-id>`, write limit files | **sandboxd** | `cgroup.zig` (oracle `cgroup.py`) |
| write child PID → `cgroup.procs` | **sandboxd** | before `execve` (`wp4-s2.md` §5.1 step 2 note) |
| `open(leaf, O_DIRECTORY)` + `BPF_PROG_ATTACH @INET_EGRESS` | **agent_guardd** | `bpf.py:attach` (holds a *fd*, never `mkdir`s) |
| `BPF_PROG_DETACH` | **agent_guardd** | `bpf.py:detach` |
| `rmdir vaked/<agent-id>` | **sandboxd** | `cgroup.zig` teardown, after no live procs |

So **sandboxd owns the directory lifecycle; guardd owns only an attach on a leaf
it does not create or remove.** This is the same single-creator pattern the
design already uses for the overlay (sandboxd mounts, fs-snapshotd accounts —
sandboxd-design §Relationship to the roster). The guardd change is one line: in
`bpf.py:load_membrane` (lines 218–219) accept an explicit `cgroup_dir` and skip
the `vaked_guard_<pid>` mint/`mkdir`/`rmdir` when given; default path (own
throwaway cgroup) preserved for `probe`/`demo`.

**Permission basis:** guardd attaching a BPF program to a cgroup it does not own
requires that the `vaked` subtree is delegated such that guardd's uid can
`open()` the leaf for attach (cgroup-v2 delegation, `cgroup.py` §Privilege note;
`configuration.nix` line 138). On the delegated vakedos subtree this holds; in a
nested container the attach is refused EINVAL and **reported, not faked**
(`bpf.py` line 51 commentary; `agent-guardd.md` "Attach (probe)").

### 5.4 Why the cgroup attach is independent of netns ownership

`BPF_CGROUP_INET_EGRESS` is **cgroup-scoped**, not netns-scoped (`bpf.py`
line 39, `expected_attach_type` line 143). A program attached at
`vaked/<agent-id>` runs for the egress of **every process in that cgroup
regardless of which network namespace they sit in**. Therefore the
sandboxd-design §Open question "who creates vs who programs the netns" is
**orthogonal** to this contract: sandboxd can own netns creation
(`CLONE_NEWNET`, `namespace.py` lines 19–23) and guardd can still enforce egress
via the shared cgroup without touching the netns. This plan resolves the
*cgroup* attach point; it deliberately leaves netns programming to guardd (its
roster membrane) and does not couple the two.

### 5.5 The attach/teardown handshake (guard_handshake.zig) — no enforcement gap

The ordering that makes (2) implementation-ready, relative to the `wp4-s2.md`
§5.1 spawn sequence:

```
sandboxd spawn(cfg):
  2. cgroup.create_leaf(agent_id); cgroup.write_limits(cfg.limits)   # leaf exists
  2a. event.spawn(..., action="allow")  -> eventd   [write-ahead, RFC 0004 §3.1]
  2b. emit "cgroup-leaf-ready(agent_id, leaf_path)"  ── guardd attach barrier ──┐
  3. clone child (CLONE_NEWUSER|NEWNS|NEWPID|NEWNET)                            │
  4-6. (child) userns / mountns / pivot_root                                    │
      parent: write child host-pid -> leaf/cgroup.procs                         │
  ── BARRIER: parent BLOCKS until guardd acks attach (or attach-refused) ───────┘
  7. (child) prctl(NO_NEW_PRIVS); seccomp(SET_MODE_FILTER, default)   [§5.1]
  8. (child) drop privs
  9. (child) execve(cfg.exec.path, argv, env)        # egress program already attached
 10. (parent) waitpid; on exit: event.exit -> eventd
 teardown: guardd BPF_PROG_DETACH  →  sandboxd rmdir leaf  (after no live procs)
```

Invariants:

1. **No unfiltered-egress window.** The barrier at step 6→7 ensures guardd's
   attach (or an honest attach-refused, §5.3) completes **before** the child
   `execve`s the workload — so the first packet the workload can send is already
   under the cgroup egress hook. The PID is in `cgroup.procs` before the barrier
   releases, so attach covers it.
2. **Write-ahead precedes effect.** The `event.spawn` (2a) is appended **before**
   the clone, per the RFC 0004 §3.1 *"Registration precedes consumption"*
   write-ahead discipline ([RFC 0004 §3.1](../../../protocol/rfcs/0004-multi-agent-state-dependency.md))
   and the eventd single-source-of-truth role
   ([RFC 0001 §5](../../../protocol/rfcs/0001-hcp.md), "Event log and
   tamper-evidence: `eventd`", line 45). eventd owns canonical hashing; sandboxd
   emits the payload only.
3. **Teardown ordering.** `BPF_PROG_DETACH` (guardd) **before** `rmdir` (sandboxd),
   and `rmdir` only after the leaf has no live processes — the kernel refuses
   `rmdir` on a non-empty cgroup (`cgroup.py:teardown_cgroup` lines 209–219).
4. **Authority is stubbed-but-wired.** The grant gate (deny if
   `process_policy.grant == none`) is checked and logged `action="deny"`, but
   real authority is preceptord's ([RFC 0001 §5](../../../protocol/rfcs/0001-hcp.md),
   "Authority and policy: `preceptord`", line 331); absent in the reference
   phase, so allow-all + log (sandboxd-design §Security model).

The barrier transport in S2 is the eventd-mediated "cgroup-leaf-ready" payload
(guardd subscribes; acks via its own event). The **full** lifecycle owner is
agent-supervisord ([RFC 0001 §5](../../../protocol/rfcs/0001-hcp.md),
"Supervision and state dependencies: `agent-supervisord`", line 425); sandboxd
does **not** transition agent state — it only sequences attach vs exec
(`wp4-s2.md` §1.2 "No second lifecycle").

## 6. Test plan — M1-local vs dev-cx53/Linux

Split mirrors `wp4-s2.md` §6 and the design's verification posture
(sandboxd-design §Verification posture: *"CI stays bytes/structure; runnability
is a devshell gate"*).

### 6.1 Runs fully on M1 (aarch64-darwin) — pure logic & assembly

| Check | Command | Why M1 suffices |
|---|---|---|
| seccomp filter byte assembly | `zig build test` (`seccomp_asm_test.zig`) | asserts `assemble("default")` == `seccomp.default.golden`; encodes x86_64 `AUDIT_ARCH_X86_64` + `__NR_*`; **no `seccomp(2)` call**, so host arch cannot leak |
| arch-gate + default-deny structure | same | asserts L1 jf→KILL on arch mismatch and the trailing `RET_ERRNO\|EPERM` are present in the bytes |
| cgroup leaf-path agreement | `zig build test` (`cgroup_leaf_test.zig`) | pure: `sandboxd.leaf_path("fixture-worker")` == `"vaked/fixture-worker"` == the path guardd will `open()` — the cross-daemon contract as a pure string assertion |
| cgroup limit-file content | same | writes to temp `cgroup_root`, asserts bytes vs `cgroup.py:apply_cgroup_limits` |
| handshake ordering state machine | `zig build test` (`handshake_order_test.zig`) | pure: drives a state enum and asserts attach-barrier precedes exec, detach precedes rmdir, write-ahead precedes clone — no syscalls |
| cross-compile to target | `zig build -Dtarget=x86_64-linux` | compiles full daemon on M1; ns/cgroup/seccomp **syscalls do not run here** |

Python cross-check (M1): `python3 -m agent_guardd probe` reports the current
`vaked_guard_<pid>` behaviour; after the `bpf.py` change, a unit asserts
`load_membrane(..., cgroup_dir=<leaf>)` opens `<leaf>` and does **not** `mkdir`
a `vaked_guard_*` directory (pure call-shape assertion; the real `attach` errno
is host-dependent and tolerated, per `bpf.py`'s structured-report discipline).

### 6.2 Requires dev-cx53 (Linux x86_64) — kernel effects

| Check | Why it cannot gate on M1 |
|---|---|
| seccomp behaviour: a syscall outside the allowlist → `EPERM` (and KILL on arch mismatch) | `prctl`+`seccomp(SET_MODE_FILTER)` are Linux-only |
| guardd attaches at sandboxd's **shared** leaf (not a throwaway), and a process in `vaked/<agent-id>` is subject to the egress hook | `BPF_PROG_LOAD`/`PROG_ATTACH` + delegated cgroup-v2; verifier runs only on Linux |
| no unfiltered-egress window: the workload's first egress is already under the attached program | requires real clone + attach barrier + execve timing |
| teardown: `DETACH` then `rmdir`; `rmdir` on a still-live leaf is refused | cgroup-v2 kernel semantics |
| write-ahead/exit events land on the real eventd chain | runtime eventd daemon; integration host is Linux |

This extends the future `task sandbox-smoke` gate (`wp4-s2.md` §6.2) with the
two checks specific to this plan: **(a)** a non-allowlisted syscall is `EPERM`'d,
and **(b)** guardd's egress program is attached at sandboxd's `vaked/<agent-id>`
leaf (assert `bpf_prog_query` lists the program on that cgroup), proving the
"alongside" attach point — **not** that egress was enforced in-kernel (the
loaded program is still the posture; §1.1).

### 6.3 CI wiring

M1-local `zig build test` runs in the dev shell pre-PR (CI has no privileged
sandbox — sandboxd-design §Verification posture). The dev-cx53 leg runs in the
WP4 CI lane via `nix develop` on the build host. Every new test file cites the
design § or oracle function it enforces (the `wp4-s2.md` §6.3 / WP3-S7
adversarial-independence convention).

## 7. Dependencies on other sprints

| Depends on | What this plan needs | Status |
|---|---|---|
| **WP4-S1** | sandboxd build shell + CLI skeleton to host `seccomp.zig`/`cgroup.zig` | Prereq; today only the `main.zig` stub exists (`daemons/sandboxd/src/main.zig`) |
| **WP4-S2 (broad)** | the spawn sequence, `linux.zig`, `config.zig`, fixture, eventd payloads this plan slots into | Co-sprint; this is the seccomp+attach slice of `wp4-s2.md` |
| **Design Plan step 0** (config projection, grammar-first, **gated**) | grant→profile inputs eventually drive `cfg.seccomp.profile`; until then `"default"` only | BLOCKER for the *config-driven* profile path; S2 runs the fixed `default` against the §2.2 fixture (sandboxd-design §Config contract / §Open) |
| **agent_guardd** | the one-line `bpf.py:load_membrane` change to attach at sandboxd's leaf; the allow-set-aware program is guardd's follow-up | Python ref exists (`agent_guardd/bpf.py`); allow-set program is `agent-guardd.md` §Next; Zig port is later |
| **eventd** | append-only hash-chained log for write-ahead spawn/exit and the leaf-ready barrier payload | Python ref exists (`agent_sandboxd/eventd.py`); Zig port is WP4-S4 |
| **agent-supervisord** | owns the RFC 0004 lifecycle; this plan only sequences attach-vs-exec, never agent state | RFC 0001 §5 / RFC 0004; WP4-S3 |
| **WP4-S5** | grant→seccomp-profile and grant→egress-policy lowering | Downstream; S2 ships fixed `default` + stubbed-but-wired selection |
| **vakedos host** | userns enabled, cgroup-v2 mounted, `vaked` subtree delegated, nftables | Present (`configuration.nix` lines 134, 138; `cgroup.py` §Privilege note) |

## 8. Acceptance criteria

S2's seccomp+attach slice is done when **all** hold:

1. **seccomp assembly (M1-local).** `seccomp.zig:assemble("default")` equals
   `testdata/seccomp.default.golden` byte-for-byte; the bytes encode the
   arch-gate (`AUDIT_ARCH_X86_64` mismatch → `KILL_PROCESS`), each allowlisted
   x86_64 `__NR_*` → `RET_ALLOW`, and the trailing default `RET_ERRNO(EPERM)`
   (§5.1). No `seccomp(2)` executed on M1.
2. **Leaf-path agreement (M1-local).** `sandboxd.leaf_path(agent_id)` is the
   single source of truth and equals `"vaked/"+agent_id` == the path
   `bpf.py:load_membrane(cgroup_dir=…)` opens; asserted as a pure cross-daemon
   string equality (`cgroup_leaf_test.zig`) and by the guardd unit confirming no
   `vaked_guard_*` dir is minted when `cgroup_dir` is passed.
3. **cgroup content parity (M1-local).** limit files match `cgroup.py:apply_cgroup_limits`
   for the §2.2 fixture, written under a temp `cgroup_root`.
4. **Handshake ordering (M1-local + dev-cx53).** Pure state-machine test asserts:
   write-ahead spawn precedes clone; attach barrier precedes `execve`;
   `no_new_privs` precedes seccomp; seccomp precedes drop-privs+`execve`; detach
   precedes rmdir (§5.5). On dev-cx53 the observable subset is asserted by the
   smoke harness.
5. **Cross-compile (M1-local).** `zig build -Dtarget=x86_64-linux` compiles the
   full daemon (no syscall executed on M1).
6. **Kernel behaviour (dev-cx53).** A non-allowlisted syscall returns `EPERM`
   (KILL on arch mismatch); guardd's egress program is attached at sandboxd's
   `vaked/<agent-id>` leaf (verified via prog-query on that cgroup); the
   workload's first egress occurs after the attach barrier; `DETACH` precedes a
   successful `rmdir` and `rmdir` on a live leaf is refused.
7. **No over-claim of enforcement.** The spec, code comments, and PR description
   state that S2 delivers the **attach point + handshake**, not live in-kernel
   egress enforcement; `mechanism` stays `"reference"` until the allow-set-aware
   guardd program lands (§1.1; `agent-guardd.md` §Next). The
   `cfg.seccomp.profile` selection and grant→egress lowering are named as the
   WP4-S5 hook.
8. **Convention.** Every test file cites the design § or oracle function it
   enforces; `daemons/sandboxd/build.zig.zon` `dependencies` stays empty (pure
   syscalls — the guardd-bpf precedent); the guardd change is the single
   `cgroup_dir` parameter with default behaviour preserved.
