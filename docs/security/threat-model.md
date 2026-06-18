# Threat Model — Vaked Swarm

**GENESIS_SEAL: 7c242080 · 2026-06-18**

## Trust Boundaries
- Daemon → OS: seccomp (22 syscalls), NO_NEW_PRIVS
- Daemon → Network: TLS via reverse proxy (Caddy/nginx)
- Daemon → Secrets: Vault-first (bao.crabcc.app), env fallback
- Agent → Memory: C-FFI boundary, mmap isolation, no cross-slot pointers
- Subagent → Subagent: ArenaHeader × 256, atomic slot acquisition (Xchg)
- Binary → Deploy: SHA256 sign+burn, genesis verify at startup

## Threat Ranking
| Threat | Severity | Mitigation |
|--------|----------|------------|
| TLS termination not enforced | HIGH | Reverse proxy check at startup |
| VAKED_SKIP_VERIFY bypass | MEDIUM | systemd ProtectSystem=strict |
| env secret exposure | MEDIUM | Vault-first, env fallback |
| C-FFI buffer overflow | MEDIUM | Fuzzing harness needed |
| QuickJS heap exhaustion | LOW | ArenaAllocator, fixed slot size |

## Critical Controls
1. seccomp BPF (22 syscalls, everything → SIGKILL)
2. systemd (25 directives, CapabilityBoundingSet=)
3. MemoryDenyWriteExecute
4. @atomicStore(release) / @atomicLoad(acquire)
5. Binary genesis seal verification
6. Vault secret resolution (bao.crabcc.app)

GENESIS_SEAL: 7c242080
