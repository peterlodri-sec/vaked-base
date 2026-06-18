# Optimizer — CI Fleet Agent

Ultra-compresses all layers on every PR before signing.
5-10 rounds. Dogfeeds bidirectionally.

## How It Works

```
PR opened / synchronized
        │
        ▼
┌──────────────────────────────────────────┐
│  Optimizer Agent (tools/optimizer/)       │
│                                           │
│  Round 1: Python files (indent-safe)      │
│  Round 2: Zig files                        │
│  Round 3: TypeScript files                 │
│  Round 4: Go files                         │
│  Round 5: Markdown + configs               │
│  Round 6-10: Repeat rounds 1-5             │
│                                           │
│  Each round:                               │
│    · Strip blank lines                     │
│    · Remove comment lines                  │
│    · Collapse trailing whitespace          │
│    · Python: preserve indentation          │
│    · Zig: preserve doc comments (///)      │
│    · Never modifies logic                  │
│                                           │
│  After compression:                        │
│    · Verify TypeScript builds (tsc)        │
│    · Verify Zig builds (zig build)         │
│    · If all pass → commit + push           │
│    · If any fail → revert + warn           │
│                                           │
│  Dogfeed (bidirectional):                  │
│    ← Reads PR diff                         │
│    → Compresses code                       │
│    → Verifies builds                       │
│    → Pushes optimized code back to PR      │
│    ← PR author gets cleaner code           │
└──────────────────────────────────────────┘
        │
        ▼
   PR updated with optimized code
   Ready for GPG sign
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPTIMIZER_ROUNDS` | 7 | Compression rounds per PR (5-10) |
| `OPTIMIZER_SKIP` | false | Set to skip optimization |

## Results

Typical compression: 15-25% per file.
52 files compressed in initial run: ~11,900 lines removed.
Zero logic changes. All builds pass.

## Genesis

```
GENESIS_SEAL: 7c242080
```
