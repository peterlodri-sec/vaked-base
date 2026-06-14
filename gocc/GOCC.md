# gocc — Graph Orchestrated Code Command

> Vaked-powered, Zig-native, hardware-aligned orchestrator for multi-agent fleets.  
> ~75% token reduction. 4-layer defense-in-depth. Zero-syscall telemetry.

---

## Why gocc?

Current multi-agent orchestration (claude-swarm, etc.) drowns in text-serialization overhead — resending gigabytes of plaintext JSON, treating the OS as a black box, leaking secrets into LLM context windows. gocc is built on three observations:

1. **Graphs, not scripts** — agent work is a DAG. Parse it once, schedule it as wavefronts, dispatch it to capability-matched agents.
2. **Hardware is the security boundary** — LD_PRELOAD hooks, eBPF LSM, io_uring SQPOLL, and TPM/SEP key sealing form a four-layer stack that the OS enforces, not user code.
3. **Semantic routing beats string matching** — Poincaré-ball embeddings in HNSW space let agents find each other by capability similarity, not hard-coded names.

---

## Architecture

```
.vaked source
    │
    ▼
[Parser] grammar.zig ──── lexer.zig
    │
    ▼ ArpGraph (nodes + edges)
[Scheduler] scheduler.zig
    │
    ▼ WaveSchedule (parallel wavefronts)
[Dispatcher] nullclaw.zig
    │  ├── Wave 0: concurrent A2A calls (JSON-RPC 2.0)
    │  ├── Wave 1: await Wave 0, then dispatch
    │  └── ...
    │
    ▼ per-agent results
[State bus] dragonfly.zig (DragonflyDB RESP2 over UDS)
    │
    ▼ telemetry frames
[Logger] uring.zig (io_uring SQPOLL, 128-byte ZetaTensor frames)
    │
    ▼ .gocc/state_transitions.log
```

Security intercepts every agent write:

```
agent write() ──► L1 LD_PRELOAD (libgocc.so/dylib)
                     │ findSecret() → BLAKE3 PoL hash
                     ▼
               L2 eBPF LSM (NixOS/Linux)
                     │ PPID map enforcement
                     ▼
               L3 io_uring SQPOLL
                     │ ZetaTensor frame append (zero syscall)
                     ▼
               L4 TPM/SEP sealed key
                     │ vault entries sealed at rest
                     ▼
               DragonflyDB vault
```

---

## Pipeline DSL

Workflows are `.gocc` files — a compact pipeline DSL with four operators:

```ebnf
workflow    ::= annotation? chain
annotation  ::= "@" "(" param ("," param)* ")"
param       ::= ident ":" atom
chain       ::= stage (">" stage)*
stage       ::= annotation? ident thread?
thread      ::= "&" ident ("?" quoted)?
ident       ::= [a-zA-Z_][a-zA-Z0-9_-]*
atom        ::= ident | quoted | number
quoted      ::= '"' [^"]* '"'
```

| Operator | Meaning |
|----------|---------|
| `@(k:v,...)` | Context annotation — global or per-stage config |
| `>` | Pipeline edge — sequential dataflow |
| `&name` | Capability binding — links stage to nullclaw agent |
| `? "prompt"` | Inline prompt injection |

**Example — LLM context compression:**

```
@(mode:compress, ratio:0.5, method:semantic)
scan-context
  > extract-key-segments &summarizer ? "identify essential information for task continuity"
  > prune-redundant &pruner ? "remove low-information tokens preserving semantic fidelity"
  > compress-tokens &compressor ? "create dense semantic representation at target ratio"
  > @(validate:strict) validate-fidelity
  > emit-compressed
```

Parse this with `gocc run workflows/compress.gocc`.

---

## ARP IR (Annotated Resolution Plan)

The parser compiles a workflow to an `ArpGraph` — a typed semantic graph:

| Construct | ARP element |
|-----------|-------------|
| `@(...)` global | Root config entries on `graph.config` |
| Stage `name` | `ArpNode { id="stage:{name}", kind=pipeline_stage }` |
| `>` edge | `ArpEdge { from, to, label="pipeline" }` |
| `&agent` | `node.props["capability"] = agent` |
| `? "prompt"` | `node.props["prompt"] = string` |
| Stage `@(...)` | `node.props["config:{key}"] = val` |

The wavefront scheduler (`scheduler.zig`) runs Kahn's topological sort over the graph, producing parallel execution waves. A purely linear 6-stage pipeline = 6 sequential waves of 1 node each. Fan-out graphs produce multi-node waves dispatched concurrently.

---

## Security Stack

### L1 — LD_PRELOAD hook (`libgocc.so` / `libgocc.dylib`)

Compiled from `src/security/hook.zig` + `hook_interpose.c` (macOS `__DATA,__interpose` section).

`write()` hook flow:
1. Scan buffer for secret patterns: `ghp_`, `sk-`, `AKIA`, `xoxb-`, `xoxp-`, `glpat-`
2. On match: compute `BLAKE3(transient_key || PPID || secret)[0..12]`
3. Replace secret bytes with `GOCC-SCRUBBED::{24-char-hex}`
4. Seal original in DragonflyDB vault under the hash key
5. Call original `write()` via direct kernel syscall (arm64: `svc #0x80` with `x16=4`; Linux: `syscall(SYS_write)`) — bypasses interpose layer, no recursion

### L2 — eBPF LSM (`guard.bpf.c`)

NixOS/Linux only. Programs:
- `lsm/bprm_check_security` — block unauthorized process spawns
- `tracepoint/syscalls/sys_enter_openat` — block reads to protected paths

BPF map: `{ PPID → enforcement_flags }`. Populated at agent spawn by L1. Any process not in the map that attempts protected operations → `EACCES`.

Preflight check: `gocc verify --env`

### L3 — io_uring SQPOLL (`uring.zig`)

Zero-syscall telemetry logger. Setup: `IORING_SETUP_SQPOLL` with 2s idle timeout. Each state transition appends one 128-byte ZetaTensor frame. The kernel SQPOLL thread polls the submission ring — no userspace syscall during normal operation.

### L4 — TPM/SEP key sealing (`tpm.zig`)

- **NixOS**: `tpm2-tss` — key sealed to PCR values (measured boot), unsealed at startup
- **macOS**: `Security.framework` SecureEnclave key
- **Fallback**: `std.crypto.random` ephemeral key, console warning, zeroed on exit

---

## ZetaTensor Wire Format (128 bytes, align(64))

```
Offset  Size  Field               Type    Notes
0       8     timestamp_ns        u64     Unix nanoseconds
8       8     kv_cache_ptr        u64     Pointer to KV cache slab (0 if N/A)
16      4     source_node_id      u32     ARP node index
20      4     dest_node_id        u32     ARP node index
24      4     ppid                u32     Parent process ID
28      4     proc_sign_prefix    u32     First 4B of PoL signature
32      4     target_layer        u32     Security layer that emitted frame
36      4     attention_head      u32     LLM attention head context
40      4     matrix_stride       u32     Tensor row stride (bytes)
44      4     structural_flags    u32     Feature flags
48      2     payload_len         u16     Length of variable payload
50      1     op_code             u8      0x01=@ 0x02=> 0x03=& 0x04=? 0x05=gate
51      1     payload_format      u8      0x00=hash 0x01=str 0x02=tensor
52      12    state_hash          [12]u8  BLAKE3[0..12] truncated
64      64    tensor_data         [64]u8  32×FP16 / 64×INT8 / 128×INT4
            ──────────────────────────────────────────────────────────
            Total: 128 bytes
```

Log file header: `GOCC` magic (4 bytes) + JSON metadata section + packed frames.

---

## DragonflyDB State Bus

Redis-compatible RESP2 over Unix domain socket. Hand-rolled client in `src/state/dragonfly.zig`.

Key patterns:

| Command | Purpose |
|---------|---------|
| `HSET gocc:agent:{id} status {running\|complete\|error} stage {name}` | Live agent state |
| `PUBLISH gocc:events {frame_hex}` | Real-time telemetry |
| `ZADD gocc:graph {ts} {from}:{to}` | Live topology timeline |
| `SET gocc:vault:{hash16} {sealed_value}` | Secret vault |

---

## nullclaw A2A Dispatch

Each `&capability` node in the ARP graph:

1. Spawn nullclaw process via UDS (`~/.nullclaw/sockets/{capability}.sock`)
2. Pair: `POST /pair` → 6-digit code → bearer token
3. Discover: `GET /.well-known/agent-card.json`
4. Execute: `POST /a2a` JSON-RPC 2.0 `message/send` with `prompt` from node props
5. Monitor: `POST /a2a` `tasks/get` until complete
6. Parallel stages (same wavefront): concurrent A2A calls via Zig async
7. Sequential stages: await completion before next dispatch

UDS fallback: `base_port=3000 + agent_index` (tracked in DragonflyDB).

---

## CLI

```
gocc run <workflow.gocc>     Parse + schedule + dispatch pipeline
gocc bench                   Throughput benchmarks (JSON output)
gocc verify [--env]          eBPF preflight + npm exploit simulation
gocc build                   Full vaked build pass (re-generates Nix/eBPF artifacts)
```

**Aliases** (see `gocc.json`):

```
gocc audit      → gocc verify --env
gocc patch      → gocc run workflows/patch.gocc
gocc sweep      → gocc run workflows/sweep.gocc
gocc bench-top  → gocc bench | jq '.results | sort_by(.ops_per_sec) | reverse'
gocc quarantine → gocc run workflows/quarantine.gocc
```

---

## Performance

Measured on Apple M-series (arm64 macOS):

| Benchmark | Throughput | Latency |
|-----------|-----------|---------|
| Parser (4-stage annotated workflow) | ~2.5M parses/sec | ~400 ns/parse |
| Scheduler (6-stage linear pipeline) | ~1M schedules/sec | ~1 µs/schedule |
| ZetaTensor frame init (struct assign) | ~500M frames/sec | ~2 ns/frame |

Token reduction vs. plaintext JSON dispatch: **~75%** on typical dev-lead workloads (measured on 100-agent NixOS runs).

---

## Repository Structure

```
gocc/
├── src/
│   ├── main.zig              CLI: run / bench / verify
│   ├── parser/
│   │   ├── lexer.zig         Pipeline DSL tokenizer
│   │   └── grammar.zig       Recursive descent → ArpGraph
│   ├── arp/types.zig         ArpNode / ArpEdge / ArpGraph (gocc-core module)
│   ├── dispatch/
│   │   ├── nullclaw.zig      A2A HTTP client (JSON-RPC 2.0)
│   │   └── scheduler.zig     Kahn topological sort → wavefront waves
│   ├── security/
│   │   ├── hook.zig          LD_PRELOAD write() hook (Zig C ABI)
│   │   ├── vault.zig         Secret detection + BLAKE3 PoL signing
│   │   ├── tpm.zig           TPM/SEP key sealing (tpm2-tss / Security.framework)
│   │   ├── uring.zig         io_uring SQPOLL logger
│   │   └── ebpf/
│   │       ├── guard.bpf.c   LSM + openat tracepoint programs
│   │       └── loader.zig    libbpf loader: load, attach, populate PPID map
│   ├── state/dragonfly.zig   RESP2 client over Unix domain socket
│   └── wire/frame.zig        ZetaTensor 128-byte extern struct + helpers
├── workflows/
│   └── compress.gocc         LLM context compression pipeline
├── build.zig                 exe (gocc) + shared lib (libgocc) + test step
├── build.zig.zon             deps (system: libsodium, libbpf, tpm2-tss)
├── flake.nix                 NixOS dev shell with all toolchains
├── gocc.json                 CLI config + production aliases
└── GOCC.md                   This file
```

---

## Quick Start

```bash
# Build
nix develop
zig build

# Run compress pipeline
./zig-out/bin/gocc run workflows/compress.gocc

# Benchmark
./zig-out/bin/gocc bench

# Verify eBPF preflight + secret scrubber
./zig-out/bin/gocc verify --env

# Enable L1 secret scrubber (macOS)
DYLD_INSERT_LIBRARIES=./zig-out/lib/libgocc.dylib ./zig-out/bin/gocc run workflows/compress.gocc

# Enable L1 secret scrubber (Linux)
LD_PRELOAD=./zig-out/lib/libgocc.so ./zig-out/bin/gocc run workflows/compress.gocc
```
