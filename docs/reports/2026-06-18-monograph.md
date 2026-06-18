# VAKED MONOGRAPH
**GENESIS_SEAL: 7c242080**

## Topology
OpenRouter → GCP C8(16x) → WireGuard/8443 → M3/iPhone
               ├─ CrabCC (Rust, <12ms)
               ├─ Ghost Space (dual-plane, fail-stop)
               └─ seccomp(22) BPF sandbox

## Install
### C8 Cloud: apt install clang llvm libbpf-dev && zig build-exe && bpftool && systemctl
### M3 Gate: nix develop && cargo build && ./vaked-mobile --port 8443
### iOS: cd AG-UI && xcodebuild && xcrun devicectl install

## Tools
CrabCC(Rust) · vaked-synapsed(Zig) · vaked-mobile(Rust) · openrouterd(Zig) · matrix-factory(Zig)

## FAQ
Edge blocked? :::sudo:::cabotage@pm.me:::  Jitter? 500ms debounce  Fault? Ghost Space <1ms

96 commits · 15 domains · Zero races · Zero PII · Local-first sovereign
