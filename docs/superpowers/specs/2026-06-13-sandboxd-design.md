# sandboxd — the process + filesystem membrane daemon (design)

## Status

Design (2026-06-13). The enforcement daemon for the **process** and
**filesystem** membranes of the runtime roster
([`docs/runtime/README.md`](../../runtime/README.md)): the Zig daemon that, per
worker, builds an isolation boundary and runs the agent workload inside it.
Tracks issue [#86](https://github.com/peterlodri-sec/vaked-base/issues/86) (the
isolation-backend question) and relates to [#50](https://github.com/peterlodri-sec/vaked-base/issues/50)
(the wasm backend). Convention: daemon = design → plan → impl; this is the
design.

This document **opens the isolation-backend axis** that the
[wasm-worker-isolation design](./2026-06-13-wasm-worker-isolation-design.md)
explicitly deferred to "the daemon-spec phase" (its Plan item 2). It composes
already-specified foundations — the RFC 0004 lifecycle, the
[agent-supervisord](./2026-06-12-agent-supervisord-design.md) worker contract
(`vaked_fiber_worker` → port), the [eventd](./2026-06-12-eventd-design.md) oracle,
and the lowered `gen/zig/<fiber>.json` config contract
([0012 §5.2](../../language/0012-lowering.md)) — and fixes how they snap together
for a process running under isolation. The host substrate is already in place:
`hosts/vakedos` ships user namespaces, cgroup-v2, and the `overlay` module
(PR #77/#87), so no host change is required to land native-exec.

## Purpose

One Zig daemon that, per worker, materializes the **process + filesystem
membranes** declared in Vaked. Given a lowered worker config it:

1. **builds the isolation boundary** — user / mount / pid namespaces, a delegated
   cgroup-v2 subtree, and an overlay-assembled rootfs, from the config's
   membrane fields;
2. **runs the workload** — supervised `exec` of the agent process inside that
   boundary;
3. **enforces resource and write bounds** — cgroup-v2 controllers (cpu / mem /
   io / pids) for the process membrane; explicit mounts + overlay options for the
   filesystem membrane;
4. **owns the isolation-backend axis** — `native-exec | oci | wasm`; the worker's
   isolation kind is a property of the daemon, not a new top-level Vaked kind;
5. **surfaces process/file events** — the supervised exec's lifecycle and the
   kernel events it produces become testimony (agent-guardd) and audit (eventd).

sandboxd is the **enforcement** point for the capability a worker was granted; it
is not where lifecycle or canonical state lives (those stay with supervisord and
the eventd oracle, respectively — see *Relationship to the roster*).

## Isolation-backend axis (the central decision)

The roster fixes the axis:

```
sandboxd isolation backend ∈ { native-exec, oci, wasm }
```

This axis is **extensible but small** (CLAUDE.md: "small enough to implement and
remember"); every backend shares one supervision path (the supervisord worker
port), one eventing path (eventd), and one config contract (`gen/zig/<fiber>.json`).

**v0 commits to `native-exec`.** It is the backend that runs an ordinary agent
process — the common case for the operator runtime — and it needs nothing the
host does not already provide (namespaces + cgroup-v2 + overlay). `oci`, `wasm`
(#50, design already written), and the briefing's **Firecracker microVM** /
**Bubblewrap** proposals (#86) are deferred to *Open / evaluate*; they are
**additive** entries on this same axis, not contradictions, and they reuse this
document's worker port and config contract unchanged.

## native-exec mechanics (v0)

native-exec assembles the boundary in Zig directly over the host kernel
facilities (`hosts/vakedos` provides each). The sequence, per worker:

1. **namespaces** — `unshare`/`clone` a **user** namespace (rootless: the worker
   runs as an unprivileged uid that is root only inside its userns), a **mount**
   namespace (private mount propagation), and a **pid** namespace (the worker is
   pid 1 of its tree, so a kill of pid 1 reaps the whole subtree). The **network**
   namespace is owned jointly with agent-guardd — see *Open*.
2. **cgroup-v2** — join a **delegated** cgroup-v2 subtree and write the budget
   into its controllers: `memory.max`, `pids.max`, `cpu.max`, `io.max`. The bound
   is enforced by the kernel (OOM-kill / clone refusal), not estimated — the same
   "mathematical bound, not policy" stance the wasm backend takes with fuel.
3. **rootfs via overlay** — mount an `overlayfs` with a read-only base
   (`lowerdir`) and a writable layer (`upperdir` + `workdir`) on the write area
   fs-snapshotd owns; the worker sees a unified rootfs but every write lands on
   the upper layer where it can be diffed, budgeted, and captured.
4. **explicit mounts only** — bind exactly the paths the filesystem membrane
   grants (deny-by-default); nothing of the host fs is visible unless declared.
5. **drop privileges & `exec`** — drop to the unprivileged uid, apply the seccomp
   / no-new-privs posture, then `execve` the workload. The daemon supervises the
   child (reaps it, reports exit) as the worker port's run mechanism.

**Bubblewrap vs raw namespaces (open sub-choice).** #86 asks whether native-exec
is implemented *via* Bubblewrap or *via* raw namespace/cgroup syscalls in Zig.
This is a "how", not a separate backend — recorded in *Open*. v0 specifies the
*boundary* (the five steps above); the implementation mechanism is decided at the
impl-PR phase.

## Config contract

A `fiber` (with its `engine`) lowers to `gen/zig/<fiber>.json`
([0012 §5.2](../../language/0012-lowering.md)), the JSON config the Zig daemon
parses (deterministic key order = schema order; absent optionals omitted;
leading `"_generated"` header — see
[`gen/zig/mediaCompress.json`](../../../vaked/examples/lowering/gen/zig/mediaCompress.json)).
sandboxd consumes the **process + filesystem membrane** projection of that
config: the namespace set, the cgroup limits (from `budget`), the explicit
mounts, the overlay/write area, and the exec command (from `engine` /
`engine_package`).

The membrane and budget **grammar lives in the language docs**
([0008](../../language/0008-parallel-fibers-indexes-surfaces.md) for `fiber`,
[0012](../../language/0012-lowering.md) for the lowering). This document
**references, never redefines** that grammar: native-exec consumes the existing
lowering, so it introduces **no new `.vaked` field** (and therefore no
grammar-first/issue gate). The NixOS module installs `gen/zig/<fiber>.json` as the
exact file the daemon reads — same bytes, no second source of truth (0012 §4.3).

## Relationship to the roster (delineation)

- **agent-supervisord** owns the RFC 0004 lifecycle and the `vaked_fiber_worker`
  port; sandboxd is the **exec mechanism** a worker is run through, *not* a second
  lifecycle. supervisord transitions a worker `RUNNING`; the run it drives is a
  sandboxd-built boundary + supervised exec.
- **fs-snapshotd** — the filesystem membrane is **shared by boundary**: sandboxd
  *mounts* the overlay at exec; fs-snapshotd owns *diffs / write-budgets /
  artifact capture* over the upper layer. sandboxd creates the write area;
  fs-snapshotd accounts for what lands in it. (This is the one delineation to
  keep crisp — see *Open*.)
- **agent-guardd** — eBPF **observes** the process/file (and network) events a
  sandboxed exec produces: sandboxd **enforces**, guardd **testifies**. The same
  exec is an enforcement boundary to one and an evidence source to the other.
- **eventd** — the exec lifecycle (start / exit / refusal) is appended as audit
  events; sandboxd does **no** canonical hashing (the eventd oracle owns bytes).
- **mcp-brokerd** — orthogonal (the `mcp` membrane / tool calls), not the
  process/filesystem boundary.

## Security model

The process + filesystem membrane is **deny-by-default**: a worker sees only the
mounts and holds only the resources its config grants. **Rootless** via user
namespaces (root only inside the userns, unprivileged on the host); **hard
bounds** via cgroup-v2 (kernel-enforced, not advisory); **no host-fs leakage**
(explicit binds only). Sandbox grants are subject to **preceptord** authority;
during the reference phase no preceptord exists, so the stance mirrors the
supervisord design — **allow-all + log the principal**, with the deny path stubbed
but wired.

## What is deliberately NOT here

- **No new top-level Vaked kind** — the isolation backend is a property of the
  worker/engine, not a new declaration (consistent with the wasm design's
  "backend follows the engine").
- **No second lifecycle** — RFC 0004 transitions are supervisord's; sandboxd only
  starts/stops the process.
- **No fs diff/budget accounting** — that is fs-snapshotd's; sandboxd provides the
  overlay it accounts over.
- **No canonical hashing** — the eventd oracle owns bytes (the supervisord-design
  rule).
- **oci / wasm / Firecracker / Bubblewrap backends** are *Open*, not specified
  here.

## Verification posture

CI has no privileged sandbox (no userns-delegation, no cgroup write), so — like
the OTP tree (`task otp-smoke`) and the wasm backend (`task wasm-smoke`) —
runnability is a **devshell gate**, and CI stays bytes/structure.

- `task sandbox-smoke` (future): exec a trivial command in a native-exec sandbox
  and assert the boundary holds —
  - a **separate pid + mount namespace** (the child sees itself as pid 1; host
    mounts are not visible);
  - a **cgroup bound enforced** (an over-`memory.max` child is OOM-killed; a
    `pids.max` breach refuses `clone`);
  - the **overlay** is the rootfs and writes land on the upper layer;
  - **declared mounts only** — an undeclared host path is absent.
- The config-contract parse is CI-coverable now against the lowered example
  (`gen/zig/mediaCompress.json`): bytes/structure, no privilege needed.

## Plan

1. *(impl PR 1)* `daemons/sandboxd/` skeleton (Zig) + `gen/zig/<fiber>.json`
   parse; native-exec boundary as a no-op/echo runner.
2. *(impl PR 2)* native-exec for real: namespaces + cgroup-v2 delegation +
   overlay rootfs + explicit mounts + supervised exec.
3. *(with the Zig-port era)* supervisord `vaked_fiber_worker` → sandboxd port +
   eventd lifecycle events.
4. *(later)* `oci` backend (distroless Nix OCI, [0016](../../language/0016-substrate-candidates.md)).
5. *(later)* `wasm` backend per [#50](https://github.com/peterlodri-sec/vaked-base/issues/50)
   (design already written).
6. *(evaluate)* Firecracker microVM / Bubblewrap per
   [#86](https://github.com/peterlodri-sec/vaked-base/issues/86).

## Open

- **fs-snapshotd ⇄ sandboxd overlay-ownership boundary** — who creates
  `upperdir`/`workdir`, who unmounts, how the write-budget enforcement point
  relates to the overlay mount. The one delineation to lock at the impl-PR phase.
- **Backend selection** — engine-typed (per the wasm design's lean: the backend
  follows the `engine`) vs an explicit `fiber.backend` field. Grammar-first;
  deferred to its own issue if engine-typing proves insufficient.
- **WIT ↔ gen-config IDL unification** — shared open question with #50 (one IDL or
  two parallel descriptions); decided when the wasm backend's port lands.
- **native-exec implementation mechanism** — Bubblewrap vs raw namespace/cgroup
  syscalls in Zig (#86); rootless vs privileged on the host.
- **Network-namespace ownership** — sandboxd builds the netns, but the `network`
  membrane (deny-by-default egress, DNS oracle, eBPF cgroup maps) is agent-guardd's
  (roster). Who creates vs who programs the netns.
- **preceptord authority point** — where the grant check physically runs in the
  reference phase (no preceptord yet): lean allow-all + log, deny path wired.
- **Stronger-isolation backends (#86)** — is wasm sufficient for untrusted code,
  or is a Firecracker microVM backend warranted for non-wasm untrusted workloads?
