# Vaked Swarm — P2P mesh documentation

The Vaked swarm is a global, self-healing P2P mesh spanning 3 continents
(EU, NA, APAC). It uses the Synapse gossip protocol for state synchronization,
Sentinel for trust-based reputation, Mnemosyne for ancestry compaction, and
the Wise Node for governance-driven strategic synthesis.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  L0  vaked-genesis  :4433  Bootstrap anchor                    │
│  L2  meta-ralphd           Recursive observer / circuit breaker │
│  S   synapsed       :4434  P2P gossip (Merkle delta sync)     │
│      synapsed-udp   :4435  P2P gossip (UDP, fast-path)        │
│  L3  sentinel              Trust scoring + truth-ping          │
│  G   gateway        :8081  WebSocket + REST + Constellation    │
│      caddy          :8083  Caddy reverse proxy                 │
│  M   mnemosyne             24h ancestry compactor              │
│  W   wise-node             Engram strategist + governance      │
└─────────────────────────────────────────────────────────────────┘
```

## Node map

| Node | Location | Tailscale | Status |
|------|----------|-----------|--------|
| genesis.vaked.dev | Helsinki, FI | 100.105.72.88 | active |
| edge-node-02 | Falkenstein, DE | 100.66.205.85 | active |
| edge-nbg1-01 | Nuremberg, DE | 167.233.148.20 | bootstrapping |
| edge-us-west-01 | Hillsboro, US | 5.78.122.125 | pending auth |
| edge-sin-01 | Singapore | 5.223.79.65 | pending auth |

## Convergence

| Path | RTT | Batching |
|------|-----|----------|
| Helsinki ↔ Falkenstein | 136ms | off |
| Helsinki ↔ Nuremberg | 125ms | off |
| Helsinki ↔ Hillsboro | 1751ms | on (Adaptive Batching) |
| Helsinki ↔ Singapore | 1729ms | on (Adaptive Batching) |
