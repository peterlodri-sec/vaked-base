# MIGRATION_LOG — Python → Zig Big Bang

Genesis Seal: `7c242080`  
Start: 2026-06-18  
Goal: Zero Python in production. Pure native Zig mesh.

## Phase Audit

| Python file | Lines | Status |
|-------------|-------|--------|
| gateway/gw.py | 101 | ▢ |
| tools/monologue/generate.py | 98 | ▢ |
| tools/dogfeed/build.py | 109 | ▢ |
| tools/inbox/bridge.py | 163 | ▢ |
| tools/librarian/align.py | 179 | ▢ |
| tools/librarian/ralph-audit.py | 187 | ▢ |
| synapsed/*.py | ~1800 | ▢ (critical path) |
| genesisd/*.py | ~280 | ▢ |
| meta-ralphd/*.py | ~340 | ▢ |

## Existing Zig foundation

| File | Purpose |
|------|---------|
| vakedz/ | Language front-end (parser, checker, lowerer) |
| daemons/sandboxd/ | Sandbox daemon |
| vaked-fm/pulse-gen.zig | Telemetry → audio signal converter |

## Migration order (by impact)

1. **Gateway** (101L) — simplest, highest visibility, reference pattern
2. **Monologue** (98L) — stateless, pure generation
3. **Dogfeed** (109L) — file parsing, HTML generation
4. **Librarian/Ralph** (366L) — governance, build gate
5. **Inbox** (163L) — MCP protocol, curl wrapper
6. **Synapsed** (~1800L) — P2P gossip, Merkle tree, Sentinel

## Policy

- Zero glue: no cffi, pyo3, or C bindings to Python
- Genesis Archive unchanged: same Oculus ledger, same graveyard
- Shadow verification: Zig output compared to Python output
- Rolling deploy: one node at a time, verify → remove Python
