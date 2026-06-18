# vaked-cli

Unified swarm management tool. One binary, one mental model.

## Install

```bash
chmod +x tools/vaked-cli
alias vk='python3 tools/vaked-cli'
```

## Commands

### deploy

```bash
vaked-cli deploy website              # Deploy all 11 static files to /var/www
vaked-cli deploy file docs/website/donate.html  # Deploy single file
vaked-cli deploy route /new newdir    # Add route + build + deploy + test
```

### build

```bash
vaked-cli build gw        # Build gateway (Zig 0.16 ReleaseFast)
vaked-cli build chat      # Build chat gateway
vaked-cli build monologue # Build monologue generator
```

### run

```bash
vaked-cli run script.py         # Execute Python on dev-cx53 (file-based, no quoting)
vaked-cli run --shell 'uptime'  # Execute shell command on dev-cx53
echo "print('hi')" | vaked-cli run -  # Pipe Python from stdin
```

### status

```bash
vaked-cli status  # Services, endpoints, ledger, graveyard
```

### inspect

```bash
vaked-cli routes     # List all 17 gateway routes
vaked-cli test /nav  # Test if a route returns 200
vaked-cli ledger 10  # Show last 10 ledger entries
```

## Architecture

- **Async throughout** — all network operations use `asyncio`
- **Signal-safe** — SIGINT/SIGTERM handlers for graceful exit
- **Strict typing** — `@dataclass(slots=True)` for memory efficiency
- **File-based transport** — no inline shell quoting (scp → execute)
- **Zig 0.16 patterns** — uses Linux raw syscalls, ArenaAllocator, ArrayListUnmanaged

## Constants

- **Genesis Seal:** `7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf`
- **Ultimate Hash:** `81aa1c0bd9e11fef`
- **Target:** `dev-cx53` (configurable via `VAKED_TARGET` env var)

## Dependencies

None. Python 3.12+ stdlib only. Matches Vaked's zero-dependency philosophy.
