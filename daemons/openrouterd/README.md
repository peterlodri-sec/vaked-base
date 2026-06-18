# openrouterd (Atlas) — The Technocrat Agentic Runtime

**Zig 0.16 · io_uring · seccomp · mmap · Zero-copy · Deterministic**

## Genesis Foundation

| Layer | Technology | Property |
|-------|-----------|----------|
| Language | Zig 0.16 | Zero-cost, explicit memory, no GC |
| Runtime | openrouterd | Custom daemon, raw sockets |
| I/O | io_uring | Batch-submission, zero-syscall overhead |
| Memory | mmap + Arena | Persistent shared-memory arenas |
| Security | seccomp-bpf | Kernel-level syscall allowlist (22 syscalls) |

## Operational Loop (Vibecoder Cycle)

1. **Memory-Plane-First** — Every query checks the mmap'd persistent cache (O(1)) before external network calls.
2. **Context7 Native** — Context fetch occurs only on miss. Results hashed (SHA256) and committed to the Memory-Plane immediately.
3. **AST-Aware Linting** — OXC parses code inputs. Logic rejected unless it complies with capability-graph security rules.
4. **Build-Verify-Commit** — No push valid without `zig build` pass. Compiler errors are the primary prompt context for agentic auto-patching.

## Governance

- **Genesis Seal** — Every artifact carries build-time hash verification (`7c242080`).
- **Zero-Copy Integrity** — Binary structs mapped directly from disk to memory via mmap. No JSON/serialization latency.
- **Parity Policy** — Cross-language parity (TypeScript ↔ Zig) enforced by SDK synchronization.
- **Advisory Execution** — Agents propose logic; they do not block. System enforces policy via syscall interceptors.

## Quick Start

```bash
zig build -Doptimize=ReleaseSafe
./zig-out/bin/openrouterd --port 9090
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Genesis seal + status |
| `/models` | GET | Available model catalog |
| `/openapi.json` | GET | OpenAPI 3.1 spec |
| `/` | POST | Chat completion (OpenRouter-compatible) |

## Security

- 22 syscalls allowed (seccomp BPF)
- PIE + stripped binary
- Genesis seal verified at startup
- Vault-first secret resolution (bao.crabcc.app)
- 25 systemd hardening directives

## Status

**v1 initialized.** Ready for swarm deployment. Compile-Pass-Only standard enforced.

GENESIS_SEAL: 7c242080
