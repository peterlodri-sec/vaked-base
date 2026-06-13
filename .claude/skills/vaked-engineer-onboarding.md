# Vaked Engineer Onboarding Guide

**Target:** WP3 (Litany Wire Protocol) and WP4 (Daemon MVP) engineers joining June 24, 2026.

---

## Quick Start (Day 1)

### Environment Setup

```bash
# Clone + enter dev shell
git clone <repo> && cd vaked-base
nix flake update && nix develop

# Verify toolchains
zig --version          # Should be 0.16.0
rustc --version        # 1.75+
python3 --version      # 3.11+
```

### Repo Structure (2-minute tour)

```
vaked-base/
  vaked/                    # Language examples & grammar
    grammar/                # EBNF v0.3 (canonical spec)
    examples/               # 22 working .vaked files
    schema/                 # 8 domain types
  
  vakedc/                   # Python compiler (reference impl)
    lexer.py, parser.py, check.py, lower.py
  
  zig/vakedc/               # Zig compiler port (WP3 target later)
  
  docs/
    language/               # 0011 (type system), 0012 (lowering)
    runtime/                # Daemon designs: sandboxd, agent-supervisord, eventd
    papers/                 # vaked-language-v0.1.md (research paper)
  
  protocol/
    rfcs/                   # RFC 0001–0006 (Litany wire protocol) ← WP3 owns
  
  ROADMAP_2026-2027.md      # Sprint timelines + decision gates
```

### Key Documents (Read in This Order)

1. **CLAUDE.md** — Project conventions, git workflow, MCP servers
2. **ROADMAP_2026-2027.md** — Your sprint, blockers, dependencies
3. **vaked/grammar/vaked-v0-plus.ebnf** — Language you're working with
4. **docs/language/0011-type-system.md** — Type rules (if doing WP4)
5. **protocol/rfcs/0002-hcpbin.md** — Wire format (if doing WP3)
6. **vakedc/README.md** — Compiler architecture

---

## WP3 (Litany Wire Protocol) — Rust Engineer

### Your Scope (June 24–Oct 15, 8 sprints)

| Sprint | Week | Deliverable | Acceptance |
|--------|------|-------------|-----------|
| WP3-1 | Jun 24–Jul 8 | hcpbin serialization lib | 90%+ tests passing |
| WP3-2 | Jul 9–Jul 23 | Frame layer (RFC 0003) + codec | Interop with Python ref |
| WP3-3–8 | Jul 24–Oct 15 | Routing, error handling, integration, stress test, docs | Oct 15 ready for #113 |

### Critical Paths

- **RFC 0002 (hcpbin):** FROZEN by Jun 21 — no breaking changes after
- **eventd interface:** Lock port/schema by Jul 23 (WP4-2 end)
- **Python reference hcpbin:** Must exist by Jun 26 for oracle testing

### Getting Started

```bash
# Day 1: Read RFCs
cat protocol/rfcs/0002-hcpbin.md
cat protocol/rfcs/0003-frame-layer.md

# Day 2: Scaffold hcpbin library
cargo new --lib protocol/litany-hcpbin
cd protocol/litany-hcpbin

# Day 3: First commit (skeleton + tests)
# Example: serializer for Message enum with 5 variants
```

### Resources

- **Serialization:** serde_json, bincode (no_std compat)
- **Async:** tokio (we use flake-pinned version)
- **Testing:** differential oracle (compare to Python `bench.py`)
- **Stress test baseline:** 1K msg/sec through eventd (WP3-7 target)

### Slack/Async Workflow

- Sync with WP4 engineer on port contracts (Fridays)
- Post PRs to `#vaked-dev` before opening (async review)
- Blocker gates: escalate to owner by Wednesday if stuck

---

## WP4 (Daemon MVP) — Zig/eBPF Engineer

### Your Scope (June 24–Sep 15, 7 sprints)

| Sprint | Week | Deliverable | Acceptance |
|--------|------|-------------|-----------|
| WP4-1 | Jun 24–Jul 8 | sandboxd skeleton + nix build | `nix build .#sandboxd` succeeds |
| WP4-2 | Jul 9–Jul 23 | Isolation backend chosen | Bench: isolation cost <5% |
| WP4-3–7 | Jul 24–Sep 15 | agent-supervisord, eventd, eBPF, integration | Sep 15 MVP complete |

### Critical Paths

- **Isolation backend decision:** Jun 19 (before you start)
  - Recommendation: Start with native-exec (simplest), benchmark cost
  - Fallback: chroot if native-exec overhead unacceptable
- **agent-supervisord ↔ sandboxd port contract:** Lock by Jul 23
- **eBPF policy schema:** Lock by Aug 6

### Getting Started

```bash
# Day 1: Read daemon designs
cat docs/runtime/sandboxd-design.md
cat docs/runtime/agent-supervisord-design.md
cat docs/runtime/eventd-design.md

# Day 2: Verify Zig + eBPF toolchain
zig build --help
which clang  # eBPF needs clang backend

# Day 3: Scaffold sandboxd package
mkdir -p daemons/sandboxd/src
cat > daemons/sandboxd/build.zig << 'EOF'
const std = @import("std");
pub fn build(b: *std.Build) void {
    // Standard Zig build scaffold
}
EOF

nix build .#sandboxd  # Should produce flake output
```

### Resources

- **Zig:** stdlib only (no external deps), v0.16 frozen in flake.nix
- **eBPF:** libbpf (Nix-packaged), compile to .o, load at runtime
- **OTP:** Erlang/OTP via devshell, study Supervisor tree pattern
- **Testing:** vakedos bare-metal (EPYC 4345P), integration golden-path test

### eBPF Policy Example

```c
// daemons/ebpf/vaked_policy.bpf.c
#include "vmlinux.h"
#include <bpf/bpf_helpers.h>

// Ringbuf: event capture
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 256 * 1024);
} events SEC(".maps");

// Capability enforcement hook
SEC("tracepoint/syscalls/sys_enter_open")
int enforce_fs_capability(struct trace_event_raw_sys_enter *ctx) {
    // Check if caller principal has fs.repo_ro
    // If not, log violation and return -EACCES
}
```

### Slack/Async Workflow

- Sync with WP3 engineer on eventd interface (Fridays)
- Post PRs for `nix build .#sandboxd` validation (daily)
- eBPF compilation issues: ask in `#vaked-zig` channel
- Blocker gates: escalate by Wednesday if stuck

---

## Shared Conventions

### Git Workflow

```bash
# Work on task branch (never main or master)
git checkout -b waker/WP3-hcpbin-serialization  # or waker/WP4-sandboxd-nix

# Commit early, often; reference sprint + issue
git commit -m "feat(WP3-1): hcpbin serialization with serde_json

- Message enum: 5 variants (init, grant, route, error, ack)
- Test: differential oracle vs. Python bench.py
- Determinism: byte-identical across runs

Ref: #113 WP3-1"

# Push, then POST to #vaked-dev for async review
git push -u origin waker/WP3-hcpbin-serialization
# Post: "Ready for review: hcpbin serialization lib. diff: <link>"
```

### PR Reviews

- Self-assign reviewers from WP3/WP4 + owner
- Blocker gates (e.g., RFC 0002 freeze) must be reviewed before merge
- Determinism tests must pass (if applicable)

### Documentation

- Keep inline code comments minimal (well-named functions document themselves)
- Document **why**, not what: "RFC 0002 §3.2 requires big-endian for frame size"
- Commit design decisions to `docs/decisions/` (ralph-loop decision log)

---

## Onboarding Checklist (Week 1)

- [ ] Clone repo, `nix develop`, verify toolchains
- [ ] Read CLAUDE.md, ROADMAP_2026-2027.md, your sprint docs
- [ ] Read relevant RFCs (WP3) or daemon designs (WP4)
- [ ] Set up git workflow + Slack/async channels
- [ ] Create first skeleton commit (hcpbin lib or sandboxd nix)
- [ ] Attend Friday sync with cross-WP engineer
- [ ] Post first PR for review (by day 5)

---

## FAQ

### Q: What if RFC 0002 changes after freeze?
A: Post to `#vaked-dev`, escalate to owner. Changes require full team consensus.

### Q: Do I need to understand the full vaked language?
A: No. WP3 focuses on hcpbin format (RFC 0002). WP4 focuses on daemon architecture. Read the relevant docs + examples; skip language theory unless blocking your work.

### Q: What's the test strategy?
A: WP3 uses oracle testing (compare to Python ref). WP4 uses golden-path (vakedos integration test). Both use determinism checks.

### Q: Can I work async-first?
A: Yes. Sync meetings are Fridays + blocker escalation (Wed). PRs are reviewed async; post links to Slack.

### Q: What if I hit a blocker on the critical path?
A: Post to `#vaked-dev` by Wednesday (before Friday sync). Owner will unblock or cascade decision.

---

## References

- **Project:** https://github.com/peterlodri-sec/vaked-base
- **Language spec:** vaked/grammar/vaked-v0-plus.ebnf
- **Type system:** docs/language/0011-type-system.md
- **RFCs:** protocol/rfcs/0001–0006
- **Roadmap:** ROADMAP_2026-2027.md
- **Compiler:** vakedc/README.md

---

**Welcome to Vaked! 🚀**

Questions? Escalate via #vaked-dev or Friday sync.
