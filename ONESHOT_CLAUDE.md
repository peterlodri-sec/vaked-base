# `vack re-skin` — Claude Opus UltraCode

**GENESIS_SEAL: 7c242080**

```bash
vack re-skin 3-profiles dense-matrix-green clean-graph-cyberpunk tactical-graveyard
vack tag v0.2.0-ui-matrix "Dense Matrix Green profile"
vack tag v0.3.0-ui-cyberpunk "Clean Graph Cyberpunk profile"
vack tag v0.4.0-ui-graveyard "Tactical Graveyard profile"
vack verify builds -s iphoneos
```

## Files
```
AG-UI/Core/Navigation/ViewportLayoutSchema.swift  — 3-profile enum
AG-UI/Features/Viewport/RefactoredMatrixView.swift — full DOD render
tools/vaked-tui/src/main.ts                      — colorscheme sync
```

## Profiles

| # | Name | BG | Accent | Vibe |
|---|------|-----|--------|------|
| 1 | dense-matrix-green | `#040804` | `#00e660` | terminal hyper-compact |
| 2 | clean-graph-cyberpunk | `#0a0a14` | `#00d4ff` | blade runner dashboard |
| 3 | tactical-graveyard | `#141414` | `#b0b0b0` | immutable ledger |

## Tags (order)
1. `v0.2.0-ui-matrix`     — dense-matrix-green
2. `v0.3.0-ui-cyberpunk`  — clean-graph-cyberpunk
3. `v0.4.0-ui-graveyard`  — tactical-graveyard

## Constraints
- Zero OOP. Flat arrays. No observation graphs.
- Hex colors only. No asset catalog.
- All builds pass before each tag.

```
vack re-skin --help     # show this
vack re-skin --dry-run  # preview changes
vack re-skin --apply    # write files
```

GENESIS_SEAL: 7c242080
