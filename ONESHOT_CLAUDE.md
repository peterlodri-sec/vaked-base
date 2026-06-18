# ONESHOT — Claude Opus UltraCode: Re-skin UI + Push Versions

**GENESIS_SEAL: 7c242080 · Branch: feat/dyad-ui · Target: main**

You are Claude Opus 4.5 UltraCode. This is a high-density, zero-waste execution prompt. Read once. Execute. No questions.

---

## Objective

1. Re-skin the AG-UI SwiftUI app (3 layout profiles, data-oriented, no OOP)
2. Update the TUI colorscheme to match the new skin
3. Push 3 version tags (v0.2.0, v0.3.0, v0.4.0)
4. All builds must pass before each tag

---

## Architecture (read from repo)

```
cd vaked-base && cat EPOCH_0_MANIFESTO.md | head -30
```

Stack: Zig 0.16 · Swift 6 · TypeScript · Go  
Core: `[Daemon] ── [QuickJS] ──(ptr)──> [mmap MemoryPlane]`

---

## UI Spec — 3 Layout Profiles

### 1. Dense Matrix Green (default)
- Background: `#040804` (dark green-black)
- Accent: `#00e660` (terminal green)
- Font: SF Mono, 11px
- Layout: table rows, minimal padding, right-aligned metrics
- Mood: hyper-compact terminal, "the matrix"

### 2. Clean Graph Cyberpunk
- Background: `#0a0a14` (deep indigo-black)
- Accent: `#00d4ff` (cyan)
- Font: SF Mono, 12px
- Layout: card grid, rounded corners, subtle glow borders
- Mood: data center dashboard, "blade runner"

### 3. Tactical Graveyard
- Background: `#141414` (charcoal)
- Accent: `#b0b0b0` (silver)
- Font: SF Mono, 10px
- Layout: minimal, ledger-style, monochrome
- Mood: immutable record, "the graveyard"

---

## Files to modify

### AG-UI (SwiftUI)
```
AG-UI/Core/Navigation/ViewportLayoutSchema.swift  — enum + engine (exists)
AG-UI/Features/Viewport/RefactoredMatrixView.swift — create full 3-profile view
```

### TUI (TypeScript)
```
tools/vaked-tui/src/main.ts  — update colorscheme to match profiles
```

---

## Version tags

```bash
git tag -s v0.2.0-ui-matrix -m "Dense Matrix Green profile"
git tag -s v0.3.0-ui-cyberpunk -m "Clean Graph Cyberpunk profile"
git tag -s v0.4.0-ui-graveyard -m "Tactical Graveyard profile"
git push origin --tags
```

---

## Verification

```bash
cd AG-UI && xcodebuild -scheme AG-UI -configuration Release -sdk iphoneos build
cd tools/vaked-tui && npm run build
echo "GENESIS_SEAL: 7c242080"
```

---

## Constraints

- Zero OOP in SwiftUI views (data-oriented: flat arrays, no observation graphs)
- Every view must render with 0 layout object instantiation overhead
- Colors are raw hex literals, not asset catalog references
- All builds pass before each tag

---

`GENESIS_SEAL: 7c242080 · cabotage@pm.me · Push when green.`
