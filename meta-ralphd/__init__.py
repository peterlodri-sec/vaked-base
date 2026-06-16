"""meta-ralphd — the recursive observer (L2) for the Vaked runtime.

Meta-Ralph monitors Ralph (L1) — the autonomous decision loop — and acts as
a reflexive watchdog. It watches L1's CPU, memory, and hash-chain integrity,
restarting L1 if health checks fail, with strict recursion-safety and a circuit
breaker that triggers emergency hold before cascading.

Architecture::

    ┌──────────────────────────────────────────────────┐
    │  Meta-Ralph (L2)                                  │
    │  ┌─────────────┐  ┌──────────┐  ┌─────────────┐  │
    │  │ Watchdog    │  │ eBPF     │  │ Circuit     │  │
    │  │ (CPU/mem/   │  │ Syscall  │  │ Breaker     │  │
    │  │  chain)     │  │ Monitor  │  │ (3/5min)    │  │
    │  └──────┬──────┘  └────┬─────┘  └──────┬──────┘  │
    │         │              │               │          │
    │         └──────────────┴───────────────┘          │
    │                         │                         │
    │                  systemctl restart ralphd          │
    │                         │                         │
    │              ┌──────────┴──────────┐              │
    │              │  Emergency Hold?     │             │
    │              │  (≥3 restarts/5min)  │             │
    │              └──────────┬──────────┘              │
    │                    if yes:                        │
    │                 kill tailscale0                    │
    │                 alert operator                     │
    └──────────────────────────────────────────────────┘

Recursion safety (HARD CONSTRAINT):
    - Meta-Ralph checks PID before restart: if PID matches its own process,
      it REFUSES to restart.
    - Circuit breaker prevents cascading restarts (≥3 within 5 minutes →
      Emergency Hold).

Mantra: L2 watches L1. L2 cannot restart L2. The chain stops here.
"""
from __future__ import annotations

VERSION = "0.1.0"
