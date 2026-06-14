# Vaked Design System

The official design system for **[Vaked](https://github.com/peterlodri-sec/vaked-base)** — a flake-native capability-graph language for agentic, native, mesh-aware, parallel systems.

> Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.

---

## Products

| Product | Surface | Description |
|---------|---------|-------------|
| **vaked** | Language | The Vaked language — grammar (EBNF v0.3), schema, examples |
| **vakedc** | CLI | Compiler front-end: lexer → parser → LPG → type-check → lower |
| **vaked-ide** | Tauri desktop app | IDE with graph canvas, editor, AI session panel, Ghostty terminal |
| **ralph** | CI tool | Autonomous budget-capped decision loop per concept track |
| **vaked-agents** | CI | Agent fleet — PR review, spec validation |

## Sources

- **GitHub repo:** https://github.com/peterlodri-sec/vaked-base
  - `ide/vaked-ide/src/` — IDE React/TypeScript source (colors, components, layout)
  - `docs/language/` — Language design series (0001–0016)
  - `docs/context/PROJECT_CONTEXT.md` — Canonical product overview
  - `vaked/` — Language grammar and schema
  - `vakedc/` — Compiler front-end (Python, stdlib only)

*Explore the repository for deeper context. Color values, component patterns, and copy were sourced directly from `ide/vaked-ide/src/App.tsx`, `kindConfig.ts`, `vakedLanguage.ts`, and related IDE source files.*

---

## Content Fundamentals

### Tone and voice

Vaked's writing voice is **terse, technical, declarative.** The audience is systems programmers who value clarity over warmth. Copy reads like well-written code documentation — not developer marketing.

### Style rules

- **Product names are lowercase:** `vaked`, `vakedc`, `crabcc`, `ralph`, `vaked-ide`. Never capitalized in prose or UI.
- **Principles are imperative and direct:** "Compile to boring artifacts." "Make capabilities explicit." "Validate before generating." Never hedged or vague.
- **No marketing softness.** "A proposed typed, flake-native complement language for Nix" — not "revolutionizes Nix development."
- **No emoji in prose or documentation.** Emoji are used only programmatically as node-kind icons in UI code.
- **Exact technical terms over paraphrase.** "lowering pass" not "code generation step."
- **Numerals as digits.** "4 nodes · 5 edges" not "four nodes."
- **Code and paths in monospace.** Always backtick-wrapped: `vaked check`, `stream.screenrec`, `gen/RUNTIME.md`.
- **Middle dot as separator:** `declares · materializes · supervises · enforces · testifies · indexes · reveals`

### The mantra

```
Vaked declares.
Nix materializes.
OTP supervises.
Zig enforces.
eBPF testifies.
CrabCC indexes.
Surfaces reveal.
```

Also used as a single-line separator: `declares · materializes · supervises · enforces · testifies · indexes · reveals`

### Copy examples (lifted from source)

| Context | Copy |
|---------|------|
| Logo / topbar | `⚡ vaked-ide` |
| File action | `Open .vaked` · `⬇ Lower` · `Lowering…` |
| Diagnostics | `✕ 2 errors` · `⚠ 1 warning` · `✓ clean` |
| LSP status | `◉ vakedc-lsp` · `○ lsp starting…` |
| Graph stats | `4 nodes · 5 edges` |
| Hint | `⌘K to open commands` |
| Streaming cursor | `▋` |
| Error message | `file:line:col: error: E-CONFORM-MISSING-REQUIRED: field 'source' is required [index zigRefs]` |
| Suggested edit | `✎ Suggested edit` · `✓ Accept` · `✕ Reject` |

---

## Visual Foundations

### Color

Dark-first. Three surface layers, no gradients, no light mode.

**Surfaces:**

| Role | Hex | Usage |
|------|-----|-------|
| `--color-bg` | `#0d1117` | Main app canvas |
| `--color-bg-surface` | `#111827` | Raised panels, sidebars, modals |
| `--color-bg-sunken` | `#0a0d12` | Status bar, deepest embeds |
| `--color-bg-raised` | `#1a2234` | Slightly lifted elements |
| `--color-bg-overlay` | `#0b0e14` | Terminal, modal scrims |

**Borders:** `#1f2937` hairline → `#374151` default → `#4b5563` strong

**Text:** `#e2e8f0` primary → `#9ca3af` secondary → `#6b7280` muted → `#4b5563` dimmed

**Brand accents:**
- **Violet `#7c3aed`** — primary interactive (logo, buttons, active state highlight)
- **Indigo `#6366f1`** — focus rings, active tab indicator, resize handles on hover
- **Orange `#f97316`** — cursor, operator keywords, apex node in logo
- **Amber `#fbbf24`** — refinement keywords, warning states

**Status:**
- Green `#16a34a` — success, LSP ready
- Red `#ef4444` — errors
- Blue `#2563eb` — info, user messages
- Orange `#f97316` — warnings

### Typography

**Monospace first.** The entire IDE UI uses monospace — buttons, labels, diagnostics, status bar, code. System UI is reserved for chat/prose in session panels.

| Family | Token | Google Fonts sub | Usage |
|--------|-------|-----------------|-------|
| JetBrains Mono | `--font-mono` | ✓ (exact) | All UI chrome, buttons, code, editor |
| Space Grotesk | `--font-display` | ⚠ nearest match | Wordmark, display headings |
| system-ui | `--font-body` | — | Session panel prose |

⚠ **Font substitution notice:** The Vaked wordmark uses an unidentified geometric sans. Space Grotesk is the nearest Google Fonts match. Provide production `.woff2` files to replace the Google Fonts `@import` in `tokens/fonts.css`.

**Scale:** 10px (statusbar) → 11px (badges) → 12px (buttons/body) → 13px (message text) → 14px (topbar logo) → 16–32px (display)

### Backgrounds and imagery

- **No decorative gradient backgrounds.** Solid dark surfaces only.
- **No light mode.**
- **Hexagonal mesh pattern:** Repeating dot-connected hex grid in dark blue-gray, used as background texture in hero/marketing contexts.
- **Node-graph illustrations:** The central visual metaphor — glowing blue circle nodes connected by directional arrows, with one orange apex highlight node. Used in hero graphics and the logo mark.
- **Chain-link motif:** Small repeating linked-square chain — represents the hash-chained, append-only event ledger.
- **Four-pointed star:** Small sparkle mark in the bottom-right corner of brand images.

### Animation and motion

Minimal. Only functional transitions:

| Token | Value | Usage |
|-------|-------|-------|
| `--transition-fast` | `100ms ease` | Hover states, opacity |
| `--transition-base` | `150ms ease` | Panel changes, color shifts |
| `--transition-slow` | `200ms ease` | Modal entrance |

No entrance animations, no infinite loops, no bounces, no spring physics.

### Hover and press states

- **Buttons:** `opacity: 0.75` on hover
- **Resize handles:** background `#1f2937` → `#6366f1` on hover (fast)
- **Sidebar tabs:** active = `2px solid #6366f1` bottom border + `#a5b4fc` text
- **Schema rows:** background `#1f2937` on hover
- **Command palette items:** background `#1f2937` on hover / active

### Cards and containers

- Background `#111827` (one level above base)
- `1px solid #1f2937` hairline border
- **No drop shadows** — flat design throughout
- Border radius `8px` (`--radius-xl`)
- Optional `#0b0e14` header bar with `1px` bottom border

### Corner radii

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | 3px | kbd hints |
| `--radius-md` | 4px | badges, tags |
| `--radius-lg` | 5px | buttons |
| `--radius-xl` | 8px | cards, inputs, modals |
| `--radius-2xl` | 12px | chat bubbles |

Chat bubbles use **asymmetric** radius: user `12/12/2/12`, agent `12/12/12/2`.

### Node kind colors

Each Vaked declaration kind has a unique background color for graph nodes and badges.
Key kinds:

| Kind | Color |
|------|-------|
| `runtime` | Violet `#7c3aed` |
| `fiber` | Orange `#ea580c` |
| `index` | Teal `#0d9488` |
| `stream` | Blue `#2563eb` |
| `surface` | Green `#16a34a` |
| `mesh` | Red `#dc2626` |
| `workflow` | Amber `#ca8a04` |
| `parallel` | Yellow `#d97706` |
| `capability` | Pink `#db2777` |
| `memory` | Indigo `#4f46e5` |

Full mapping in `tokens/kinds.css`. Runtime component is `KindBadge`.

---

## Iconography

No icon library is used. Three systems:

### 1. Emoji as node-kind icons (programmatic, UI code only)
⚡ runtime · 📚 index · 📂 catalog · 〰 stream · 🔧 fiber · 🖥 surface · 🕸 mesh · 🔀 workflow · ⧖ parallel · 📋 schema · 🔑 capability · 🧠 memory · 💾 device · 🎬 mediaPipeline · 💰 budget · 🔌 mcp · 🔎 ebpf · ⚙ service · 🔐 secret · 🚪 ingress · 📦 container · 🔩 engine · 📊 observability · ◇ external

### 2. Unicode symbols as UI affordances
| Symbol | Usage |
|--------|-------|
| `◉` `○` | LSP active / inactive dot |
| `✕` | Close, dismiss, error |
| `⚠` | Warning |
| `✓` | Success, accept |
| `▋` | Streaming cursor |
| `◧` | Toggle sidebar |
| `▦` | Toggle terminal |
| `▸` | Run / play |
| `✎` | Edit / suggest |
| `⌘K` | Command palette trigger |
| `⬇` | Lower (compile) |
| `→` | Route / arrow (in graph labels) |

### 3. Logo mark
The "vaked" mark — a node-graph shaped like a "W" with an orange apex node and blue satellite nodes connected by arrows. Available as:
- `assets/logo-mark.png` — mark only (square)
- `assets/logo-wordmark.png` — mark + "vaked" wordmark (landscape)

---

## File Index

```
styles.css                              global entry point (imports only)
tokens/
  fonts.css                             @import from Google Fonts (substitutes)
  colors.css                            all color custom properties (231 total tokens)
  typography.css                        font families, sizes, weights, leading
  spacing.css                           spacing scale, radii, z-index, transitions
  syntax.css                            Vaked syntax highlight token colors
  kinds.css                             node kind color custom properties
assets/
  logo-wordmark.png                     "vaked" mark + wordmark on dark bg
  logo-mark.png                         logo mark only (square)
  hero-wide.png                         wide hero with logo + DAG illustration
  hero-graph.png                        hero with pipeline flow visualization
guidelines/
  colors-base.card.html                 base surface and border swatches
  colors-accent.card.html               violet + orange + amber + indigo accents
  colors-status.card.html               success / error / warning / info trios
  colors-text.card.html                 4-level text hierarchy
  colors-kinds.card.html                all node kind color chips
  type-display.card.html                Space Grotesk display + wordmark specimens
  type-mono.card.html                   JetBrains Mono code specimens + UI chips
  type-scale.card.html                  10px–32px type scale
  spacing-scale.card.html               spacing token visualization
  spacing-radii.card.html               border radius tokens
  syntax-tokens.card.html               Vaked syntax highlight color legend
  brand-logo.card.html                  logo mark + wordmark assets
  brand-imagery.card.html               hero illustrations
  brand-motion.card.html                transition tokens + hover demos
components/
  core/
    Button.jsx / .d.ts / .prompt.md     ghost·primary·danger·success; sm/md
    Badge.jsx / .d.ts / .prompt.md      inline status/label chips
    KindBadge.jsx / .d.ts / .prompt.md  node kind colored badge
    Input.jsx / .d.ts / .prompt.md      dark monospace text input
    Card.jsx / .d.ts / .prompt.md       surface container card
    core.card.html                      component showcase
  feedback/
    DiagnosticRow.jsx / .d.ts / .prompt.md   vakedc error/warning/info rows
    Toast.jsx / .d.ts / .prompt.md           ephemeral notification
    feedback.card.html                        feedback showcase
  navigation/
    Tabs.jsx / .d.ts / .prompt.md       underline tab bar
    navigation.card.html                navigation showcase
ui_kits/
  ide/
    index.html                          vaked-ide full UI recreation (interactive)
templates/
  vaked-doc/
    index.html                          technical documentation page
    ds-base.js                          design system loader script
readme.md                               this file
SKILL.md                                Claude Code agent skill definition
```

---

## Quick start

Link the design system in any HTML file:

```html
<link rel="stylesheet" href="path/to/styles.css">
<script src="path/to/_ds_bundle.js"></script>

<script type="text/babel">
const { Button, KindBadge, Badge } = window.VakedDesignSystem_ca2818;

function MyUI() {
  return (
    <div style={{ background: 'var(--color-bg)', padding: 16 }}>
      <KindBadge kind="fiber" label="mediaCompress" />
      <Button variant="lower">⬇ Lower</Button>
      <Badge variant="success">✓ clean</Badge>
    </div>
  );
}
</script>
```
