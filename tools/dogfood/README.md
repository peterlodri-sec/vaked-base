# dogfood — local proposer/judge verification kernel

A zero-cloud-cost, fully-local dev/test kernel for the Vaked dogfood loop. A
**proposer** (opencode driven by a self-hosted Ollama model) proposes a code
transition; the **judge** (this kernel) deterministically gates, records, and
replay-verifies it on the real `eventd` append-only hash chain.

> Claude/opencode may propose. The kernel decides.

This is the local approximation of Vaked's runtime: capability scoping, immutable
audit, and effect honesty enforced in *userspace on macOS* — no Linux kernel
features. The real enforcement boundary (eBPF/seccomp, L2) lives elsewhere; this
proves the *principles* (POLA, replay-stability, declared≈observed) on the M1.

## The four gates

A transition is accepted only when **all** pass; otherwise the working tree is
rolled back to its pre-proposal state and nothing is recorded.

| Gate | Question | Rejects |
|------|----------|---------|
| **Capability** (`capability.py`) | Is every changed path under a granted scope? | `used(p) ⊑ granted(p)` violation — the open `E-CAP-USE` use-check |
| **Declared vs actual** (`kernel.py`) | Did the proposer change exactly what it claimed? | a lying / sloppy proposal |
| **Observed** (M3, `observe_frida.py`) | Are Frida-observed writes a subset of declared? | undeclared real effects |
| **Replay-stability** (`kernel.py`) | Does `base + recorded post-images` reconstruct the recorded `state_hash_after`? | incomplete capture, blob corruption, post-record drift |

## Layout

```
tools/dogfood/
  kernel.py        the judge: gate → record → replay-verify; CLI
  capability.py    POLA path-scope gate
  transition.py    content-addressed tree hashing + post-image blob store
  wal.py           thin wrapper over the real eventd EventLog (the WAL)
  proposer.py      stub_propose (tests/demo) + opencode_propose (local Ollama)
  scope_from_vaked.py  lower the kernel's write-scope FROM a Vaked POLA graph
  observe_frida.py L1 advisory observer — runs in a Linux container (M3)
  test_kernel.py   stdlib test runner (no pytest)
  sandbox/         demo target dir
.dogfood/          runtime state (gitignored): wal/ (eventd chain) + blobs/
```

## Use

```bash
# accept an in-scope edit (stub proposer)
printf 'hello\n' > /tmp/new.txt
python3 tools/dogfood/kernel.py propose --scope tools/dogfood/sandbox \
  --intent "demo edit" --proposer stub \
  --edit tools/dogfood/sandbox/demo.txt=/tmp/new.txt

# real proposer: opencode + local Ollama (configure opencode for Ollama first)
DOGFOOD_OPENCODE_MODEL=qwen2.5-coder:7b \
python3 tools/dogfood/kernel.py propose --scope tools/dogfood/sandbox \
  --intent "add a docstring to demo" --proposer opencode

python3 tools/dogfood/kernel.py verify    # boot tamper-check + replay summary
python3 tools/dogfood/kernel.py log       # list recorded transitions

python3 tools/dogfood/test_kernel.py      # 16 tests, stdlib only
```

### Scope lowered from a Vaked POLA graph

Instead of hand-passing `--scope`, derive it from a Vaked capability declaration
so the declaration and the enforcement cannot drift:

```bash
# 1. parse the kernel's POLA declaration into the LPG (vakedc OR vakedz)
python3 -m vakedc parse vaked/examples/dogfood-kernel.vaked      # → .vaked/graph.json
# 2. the kernel scopes itself to what the graph grants the principal
python3 tools/dogfood/kernel.py propose --from-vaked .vaked/graph.json \
  --principal proposer --intent "..." --proposer opencode
```

`scope_from_vaked.py` reads the parsed LPG artifact (engine-agnostic — works with
the `vakedc` Python or `vakedz` Zig front-end), returns a principal's `writeScope`
only if its `fs` grant is write-capable (`repo_rw`/`host_rw`); a read-only
principal (`fs.repo_ro`) gets nothing. The kernel then enforces exactly that.

## Design notes

- **No AIL/ARP parser.** Transition records are neutral JSON (eventd-style), not
  AIL-0 frames — the ARP IR is a separate workstream. A seam exists to adopt it.
- **WAL = eventd**, the canonical daemon, not a third inline hash chain.
- **Capability = git path-scope** locally; the kernel boundary that runs on M1.
- **Post-images, not diffs.** A transition is captured as the exact bytes of
  changed in-scope files (content-addressed blobs), so replay is a pure, total
  function — no `git apply` fuzz/whitespace nondeterminism.
- **Change detection** uses a before/after snapshot delta over the git file
  universe (`git ls-files --cached --others --exclude-standard`), so a dirty
  worktree's pre-existing changes never count as the proposal's effect.

See `docs/dogfood/` for the local-Ollama setup, the kernel design, and the
L1/Frida evidence layer.
