# openrouterd — OpenRouter Agent Daemon (Atlas)

Production agent daemon for the Vaked swarm. Zig 0.16 native.
io_uring async I/O. mimalloc. seccomp BPF. SHA256 cache.

**Supersedes the Node.js/Bun/Deno TUI for deployed agents.**

## Build

```bash
zig build -Doptimize=ReleaseSafe
# → zig-out/bin/openrouterd (strippable to ~2MB)
```

## Run

```bash
OPENROUTER_API_KEY=sk-or-v1-... ./zig-out/bin/openrouterd --port 9090
```

## Deploy (systemd)

```bash
sudo cp zig-out/bin/openrouterd /usr/local/bin/
sudo cp openrouterd.service /etc/systemd/system/
sudo mkdir -p /var/lib/openrouterd/cache
sudo systemctl enable --now openrouterd
```

## API

```bash
# POST prompt → response
curl -X POST http://localhost:9090/ \
  -d '{"prompt":"How do I use std.Build in Zig 0.16?","model":"deepseek/deepseek-v4-pro"}'

# Response
{"genesis":"7c242080","content":"const std = @import(\"std\");\n\npub fn build..."}
```

## Security

| Layer | Mechanism |
|-------|-----------|
| **Allocator** | mimalloc (static link, Linux) |
| **Syscalls** | seccomp BPF — 22 allowed, everything else SIGKILL |
| **Memory** | arena allocator, zero fragmentation |
| **Cache** | SHA256 content-addressed (ralph-loop pattern) |
| **TLS** | system CA bundle (not ssl.CERT_NONE) |
| **Privileges** | NoNewPrivileges, PrivateTmp, ProtectSystem=strict |

## Seccomp Allowlist

```
read write openat close socket connect sendto recvfrom
epoll_create1 epoll_ctl epoll_wait mmap munmap mprotect
brk exit exit_group getrandom clock_gettime futex
io_uring_setup io_uring_enter
```

## Nickname: Atlas

Carries the swarm's LLM load. Named after the Titan who holds up the sky.

## Genesis

```
GENESIS_SEAL: 7c242080
```

## Deploy

### macOS (launchd)
```bash
sudo cp zig-out/bin/openrouterd /usr/local/bin/
sudo cp com.vaked.openrouterd.plist /Library/LaunchDaemons/
sudo launchctl load /Library/LaunchDaemons/com.vaked.openrouterd.plist
```

### Linux (systemd)
```bash
sudo cp zig-out/bin/openrouterd /usr/local/bin/
sudo cp openrouterd.service /etc/systemd/system/
sudo systemctl enable --now openrouterd
```

### Binary verification
The daemon self-verifies at startup. Tampered binary → refuses to start.
```bash
VAKED_SKIP_VERIFY=1 openrouterd  # dev only
```

### Sign pipeline
```bash
./tools/openrouter-compiled/sign.sh zig-out/bin/openrouterd
# Burns SHA256 hash + genesis seal into binary
# macOS: ad-hoc codesigned
# Linux: GPG detached signature
```
